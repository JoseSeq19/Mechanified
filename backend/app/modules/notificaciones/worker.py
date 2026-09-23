"""El proceso que vacía la cola de avisos.

Cómo se reparte el trabajo, que es lo único delicado de este archivo:

    UPDATE ... WHERE id IN (
        SELECT id ... FOR UPDATE SKIP LOCKED
    )

Reclamar es un UPDATE que empuja `programada_para` hacia adelante. Eso hace dos
cosas a la vez: marca la fila como tomada y le pone un arrendamiento. Si el
proceso muere a mitad del envío —se reinicia el servidor, se corta la luz— nadie
tiene que limpiar nada: al vencer el plazo la fila vuelve a estar disponible
sola. Y `SKIP LOCKED` permite que dos workers corran a la vez sin mandar el
mismo correo dos veces, que es lo que pasaría con un simple `SELECT ... WHERE
estado = 'pendiente'`.

El envío ocurre **fuera** de toda transacción: la reclamación se confirma antes
de hablar con el servidor de correo. Mantener abierta una transacción durante un
SMTP lento es la forma clásica de agotar el pool de conexiones.

Corre con el rol de servicio, que omite RLS. Es uno de sus tres usos legítimos:
la cola es de todos los talleres y aquí no hay usuario cuya identidad evaluar.
"""

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import sesion_servicio
from app.modules.notificaciones import service
from app.modules.notificaciones.mensajeria import ErrorEnvio, Mensajero
from app.modules.notificaciones.models import Notificacion, PlantillaCorreo
from app.modules.notificaciones.plantillas import renderizar

_log = logging.getLogger(__name__)

#: Tras el quinto intento se da por fallida. A esas alturas el problema no es
#: pasajero, y seguir reintentando solo perjudica la reputación del remitente.
MAX_INTENTOS = 5

#: Espera antes del siguiente intento. Creciente: un servidor saturado agradece
#: que no se le insista cada minuto, y un corte de red rara vez dura una hora.
_ESPERAS = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
)

#: Cuánto se reserva una fila mientras se envía.
ARRENDAMIENTO = timedelta(minutes=10)


def espera_tras_intento(intento: int) -> timedelta:
    """Cuánto esperar después del intento número `intento` (1 = el primero)."""
    return _ESPERAS[min(max(intento, 1), len(_ESPERAS)) - 1]


@dataclass
class Resumen:
    """Qué pasó con el lote. Se registra en el log de cada ciclo."""

    enviadas: int = 0
    reintentos: int = 0
    fallidas: int = 0

    @property
    def total(self) -> int:
        return self.enviadas + self.reintentos + self.fallidas


_RECLAMAR = text("""
    update public.notificaciones
       set intentos = intentos + 1,
           programada_para = :hasta
     where id in (
           select id
             from public.notificaciones
            where estado = 'pendiente'
              and programada_para <= :ahora
              -- `cast(... as uuid)` y no `:solo_taller::uuid`: con la sintaxis
              -- de dos puntos, el parámetro no se reconoce y la consulta ni
              -- siquiera llega a ser SQL válido.
              and (cast(:solo_taller as uuid) is null
                   or taller_id = cast(:solo_taller as uuid))
            order by programada_para
            limit :limite
            for update skip locked)
    returning id
""")


async def _reclamar(limite: int, ahora: datetime, solo_taller: UUID | None) -> list[UUID]:
    async with sesion_servicio() as s:
        filas = await s.execute(
            _RECLAMAR,
            {
                "ahora": ahora,
                "hasta": ahora + ARRENDAMIENTO,
                "limite": limite,
                "solo_taller": solo_taller,
            },
        )
        return [f[0] for f in filas.fetchall()]


async def procesar_lote(
    mensajero: Mensajero,
    *,
    limite: int = 20,
    ahora: datetime | None = None,
    solo_taller: UUID | None = None,
) -> Resumen:
    """Toma un puñado de avisos pendientes y los envía.

    `ahora` y `solo_taller` existen para las pruebas: permiten trabajar sobre
    filas programadas a futuro y acotadas a un taller, sin competir con el worker
    que esté corriendo de verdad contra la misma base.
    """
    momento = ahora or datetime.now(UTC)
    resumen = Resumen()

    for notificacion_id in await _reclamar(limite, momento, solo_taller):
        desenlace = await _procesar_una(mensajero, notificacion_id, momento)
        setattr(resumen, desenlace, getattr(resumen, desenlace) + 1)

    if resumen.total:
        _log.info(
            "Cola de avisos: %s enviadas, %s a reintentar, %s fallidas",
            resumen.enviadas,
            resumen.reintentos,
            resumen.fallidas,
        )
    return resumen


async def _procesar_una(mensajero: Mensajero, notificacion_id: UUID, ahora: datetime) -> str:
    """Redacta, envía y anota el desenlace. Devuelve el campo de `Resumen`."""
    async with sesion_servicio() as s:
        n = await s.get(Notificacion, notificacion_id)
        if n is None:
            # La orden pudo borrarse entre la reclamación y ahora.
            return "fallidas"

        plantilla = PlantillaCorreo(n.plantilla)
        destinatario, intentos, datos = n.destinatario, n.intentos, dict(n.datos)

        try:
            ctx = await service.construir_contexto(s, n)
        except ValueError as exc:
            await _anotar_fallo(
                s, notificacion_id, str(exc), definitivo=True, intento=intentos, ahora=ahora
            )
            _log.warning("Aviso %s descartado: %s", notificacion_id, exc)
            return "fallidas"

        correo = renderizar(plantilla, ctx)

    # Fuera de la transacción: el correo puede tardar, y la conexión no debe
    # quedarse retenida esperándolo.
    try:
        await mensajero.enviar(
            destinatario=destinatario,
            correo=correo,
            nombre_remitente=ctx.taller_nombre,
            responder_a=ctx.taller_email,
        )
    except ErrorEnvio as exc:
        definitivo = exc.permanente or intentos >= MAX_INTENTOS
        async with sesion_servicio() as s:
            await _anotar_fallo(
                s, notificacion_id, str(exc), definitivo=definitivo, intento=intentos, ahora=ahora
            )
        _log.warning("Aviso %s no salió (intento %s): %s", notificacion_id, intentos, exc)
        return "fallidas" if definitivo else "reintentos"
    except Exception as exc:
        # Un fallo raro (un bug nuestro) no puede dejar la cola atascada.
        definitivo = intentos >= MAX_INTENTOS
        async with sesion_servicio() as s:
            await _anotar_fallo(
                s, notificacion_id, repr(exc), definitivo=definitivo, intento=intentos, ahora=ahora
            )
        _log.exception("Fallo inesperado enviando el aviso %s", notificacion_id)
        return "fallidas" if definitivo else "reintentos"

    async with sesion_servicio() as s:
        await s.execute(
            text("""
                update public.notificaciones
                   set estado = 'enviada', enviada_en = now(), ultimo_error = null
                 where id = :id
            """),
            {"id": notificacion_id},
        )
        # La encuesta se considera enviada cuando el correo salió, no cuando se
        # encoló: si el envío falla, la ficha no debe decir que el cliente la tiene.
        if plantilla is PlantillaCorreo.ENCUESTA_SATISFACCION and datos.get("encuesta_id"):
            await s.execute(
                text("update public.encuestas set enviada_en = now() where id = :id"),
                {"id": datos["encuesta_id"]},
            )

    return "enviadas"


async def _anotar_fallo(
    sesion: AsyncSession,
    notificacion_id: UUID,
    error: str,
    *,
    definitivo: bool,
    intento: int,
    ahora: datetime,
) -> None:
    """Deja la fila lista para el siguiente intento, o la da por perdida."""
    await sesion.execute(
        text("""
            update public.notificaciones
               set estado = case when :definitivo then 'fallida'::public.estado_notificacion
                                 else 'pendiente'::public.estado_notificacion end,
                   programada_para = :proximo,
                   ultimo_error = :error
             where id = :id
        """),
        {
            "id": notificacion_id,
            "definitivo": definitivo,
            "error": error[:1000],
            "proximo": ahora + espera_tras_intento(intento),
        },
    )


async def bucle(
    mensajero: Mensajero,
    *,
    intervalo_seg: int = 10,
    limite: int = 20,
    detener: asyncio.Event | None = None,
) -> None:
    """Procesa la cola cada `intervalo_seg` hasta que se pida parar.

    Ningún error interrumpe el ciclo: si el lote entero falla se registra y se
    vuelve a intentar en el siguiente. Un worker que se muere al primer tropiezo
    deja la cola creciendo sin que nadie se entere.
    """
    señal = detener or asyncio.Event()
    _log.info("Worker de notificaciones en marcha (cada %ss)", intervalo_seg)

    while not señal.is_set():
        try:
            await procesar_lote(mensajero, limite=limite)
        except Exception:
            _log.exception("El ciclo del worker falló entero")

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(señal.wait(), timeout=intervalo_seg)

    _log.info("Worker de notificaciones detenido")
