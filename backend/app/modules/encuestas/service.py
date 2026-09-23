"""Lógica de las encuestas de satisfacción.

La encuesta nace sola: cuando la orden pasa a `entregado`, el módulo de órdenes
llama aquí y se crea la fila con su enlace, más el correo en cola. Nadie tiene
que acordarse de mandarla, que es justo lo que pasa cuando esto es una tarea
manual del asesor.

Igual que en presupuestos, el cliente responde **sin cuenta**, desde un enlace
con un token opaco. Ese camino no pasa por RLS —no hay sesión que evaluar— así
que usa el rol de servicio. Las funciones que lo hacen están agrupadas al final,
separadas del resto, para que se vea de un vistazo cuáles son.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import sesion_servicio
from app.core.exceptions import ErrorConflicto, ErrorNoEncontrado, ErrorValidacion, extraer_sqlstate
from app.modules.clientes.models import Cliente
from app.modules.encuestas.models import Encuesta
from app.modules.encuestas.schemas import RespuestaCliente, ResumenEncuestas
from app.modules.notificaciones import service as srv_notificaciones
from app.modules.notificaciones.models import PlantillaCorreo
from app.modules.ordenes.estados import EstadoOrden
from app.modules.ordenes.models import OrdenServicio
from app.modules.talleres.models import Taller
from app.modules.vehiculos.models import Vehiculo
from app.shared.enlaces import enlace_encuesta
from app.shared.paginacion import ParametrosPagina

#: Filas del listado: la encuesta más lo justo para saber de qué servicio habla.
type FilaEncuesta = tuple[Encuesta, OrdenServicio, Vehiculo, Cliente]


def calcular_nps(promotores: int, detractores: int, respuestas: int) -> int | None:
    """Promotores menos detractores, en porcentaje sobre quienes contestaron.

    Función pura y aparte porque es la única cuenta del módulo que se puede
    equivocar en silencio: un signo cambiado sigue devolviendo un número
    creíble. Los pasivos (7 y 8) no suman ni restan; cuentan en el total, que es
    lo que hace que un montón de tibios baje el resultado.
    """
    if respuestas <= 0:
        return None
    return round((promotores - detractores) * 100 / respuestas)


# -----------------------------------------------------------------------------
# Con sesión y RLS
# -----------------------------------------------------------------------------


async def _orden(sesion: AsyncSession, orden_id: UUID) -> OrdenServicio:
    orden = await sesion.scalar(select(OrdenServicio).where(OrdenServicio.id == orden_id))
    if orden is None:
        raise ErrorNoEncontrado(f"No existe la orden {orden_id}.")
    return orden


async def obtener_de_orden(sesion: AsyncSession, orden_id: UUID) -> Encuesta | None:
    """La encuesta de la orden, o None si todavía no se entregó el vehículo."""
    await _orden(sesion, orden_id)  # 404 si es de otro taller
    return await sesion.scalar(
        select(Encuesta)
        .where(Encuesta.orden_id == orden_id)
        .execution_options(populate_existing=True)
    )


async def crear_al_entregar(sesion: AsyncSession, orden: OrdenServicio) -> Encuesta:
    """Crea la encuesta de una orden recién entregada y encola su correo.

    Lo llama `ordenes.service.cambiar_estado`, dentro de la misma transacción: si
    la entrega no llega a guardarse, no queda una encuesta huérfana pidiéndole
    opinión a alguien que todavía no ha recogido el vehículo.
    """
    existente = await sesion.scalar(select(Encuesta).where(Encuesta.orden_id == orden.id))
    if existente is not None:
        return existente

    encuesta = Encuesta(taller_id=orden.taller_id, orden_id=orden.id)
    sesion.add(encuesta)
    await _guardar(sesion)

    encuesta = await _releer(sesion, encuesta.id)
    await srv_notificaciones.encolar(
        sesion,
        orden,
        PlantillaCorreo.ENCUESTA_SATISFACCION,
        {"encuesta_id": str(encuesta.id)},
    )
    return encuesta


async def enviar(sesion: AsyncSession, orden_id: UUID) -> tuple[Encuesta, str | None]:
    """Manda —o vuelve a mandar— la encuesta de una orden entregada.

    Devuelve a quién se le encoló el correo, o None si el cliente no tiene
    dirección registrada. En ese caso la encuesta existe igual y su enlace se
    puede compartir a mano: es lo que se hace con quien solo dejó un teléfono.
    """
    orden = await _orden(sesion, orden_id)
    if orden.estado is not EstadoOrden.ENTREGADO:
        raise ErrorValidacion(
            f"La orden {orden.folio} está {orden.estado.etiqueta.lower()}. "
            "La encuesta se manda cuando el cliente ya tiene su vehículo.",
            {"estado": orden.estado.value},
        )

    encuesta = await crear_al_entregar(sesion, orden)
    if encuesta.respondida:
        respondida_en = encuesta.respondida_en
        raise ErrorConflicto(
            "El cliente ya respondió esta encuesta.",
            {"respondida_en": respondida_en.isoformat() if respondida_en else None},
        )

    destinatario = await srv_notificaciones.encolar(
        sesion, orden, PlantillaCorreo.ENCUESTA_SATISFACCION, {"encuesta_id": str(encuesta.id)}
    )
    return encuesta, destinatario


def _consulta_listado(solo_respondidas: bool) -> Select:
    stmt = (
        select(Encuesta, OrdenServicio, Vehiculo, Cliente)
        .join(OrdenServicio, OrdenServicio.id == Encuesta.orden_id)
        .join(Vehiculo, Vehiculo.id == OrdenServicio.vehiculo_id)
        .join(Cliente, Cliente.id == OrdenServicio.cliente_id)
    )
    if solo_respondidas:
        stmt = stmt.where(Encuesta.respondida_en.is_not(None))
    return stmt


async def listar(
    sesion: AsyncSession, *, solo_respondidas: bool = False, pagina: ParametrosPagina
) -> tuple[list[FilaEncuesta], int]:
    base = _consulta_listado(solo_respondidas)

    total = await sesion.scalar(select(func.count()).select_from(base.subquery())) or 0

    filas = await sesion.execute(
        base
        # Primero lo contestado y lo más reciente: una encuesta sin responder de
        # hace dos meses ya no dice nada que no diga la tasa de respuesta.
        .order_by(Encuesta.respondida_en.desc().nullslast(), Encuesta.creado_en.desc())
        .limit(pagina.limite)
        .offset(pagina.desplazamiento)
    )
    return [(e, o, v, c) for e, o, v, c in filas.all()], total


async def resumen(sesion: AsyncSession, *, desde: datetime | None = None) -> ResumenEncuestas:
    """Las cifras de arriba del listado, en una sola consulta.

    Una consulta por indicador serían siete viajes a la base para pintar cinco
    números que siempre se miran juntos.

    `desde` acota a las encuestas creadas después de esa fecha; lo usa el panel
    del taller, que mira un periodo. Sin él, el resumen es de toda la vida del
    taller, que es lo que tiene sentido en el listado.
    """
    consulta = select(
        func.count(),
        func.count(Encuesta.respondida_en),
        func.avg(Encuesta.puntaje_atencion),
        func.avg(Encuesta.puntaje_tiempo),
        func.avg(Encuesta.puntaje_calidad),
        func.count().filter(Encuesta.recomendaria >= 9),
        func.count().filter(Encuesta.recomendaria.between(7, 8)),
        func.count().filter(Encuesta.recomendaria <= 6),
    ).select_from(Encuesta)
    if desde is not None:
        consulta = consulta.where(Encuesta.creado_en >= desde)

    fila = (await sesion.execute(consulta)).one()

    enviadas, respondidas, atencion, tiempo, calidad, promotores, pasivos, detractores = fila
    con_nota = promotores + pasivos + detractores

    def _medio(valor: Decimal | float | None) -> float | None:
        return round(float(valor), 2) if valor is not None else None

    return ResumenEncuestas(
        enviadas=enviadas,
        respondidas=respondidas,
        tasa_respuesta=round(respondidas * 100 / enviadas, 1) if enviadas else 0.0,
        promedio_atencion=_medio(atencion),
        promedio_tiempo=_medio(tiempo),
        promedio_calidad=_medio(calidad),
        nps=calcular_nps(promotores, detractores, con_nota),
        promotores=promotores,
        pasivos=pasivos,
        detractores=detractores,
    )


# -----------------------------------------------------------------------------
# El camino público: sin sesión, resuelto por token
#
# PELIGRO: estas dos funciones usan el rol de servicio, que omite RLS. Es
# legítimo porque no hay usuario cuya identidad evaluar —quien abre el enlace es
# un cliente sin cuenta— y el token es la autorización. Por eso filtran siempre
# por `token_publico` y nunca aceptan un identificador de fila.
# -----------------------------------------------------------------------------


async def obtener_por_token(token: str) -> tuple[Encuesta, OrdenServicio, Vehiculo, Taller]:
    async with sesion_servicio() as s:
        return await _cargar_por_token(s, token)


async def responder_por_token(
    token: str, respuesta: RespuestaCliente
) -> tuple[Encuesta, OrdenServicio, Vehiculo, Taller]:
    async with sesion_servicio() as s:
        encuesta, orden, vehiculo, taller = await _cargar_por_token(s, token)

        if encuesta.respondida:
            raise ErrorConflicto(
                "Ya respondiste esta encuesta. ¡Gracias por tomarte el tiempo!",
                {"respondida_en": encuesta.respondida_en.isoformat()},  # type: ignore[union-attr]
            )

        for campo, valor in respuesta.model_dump().items():
            setattr(encuesta, campo, valor)

        # `respondida_en` lo sella el trigger mch_encuestas_respuesta, así que la
        # fila se relee: si no, la respuesta que se devuelve diría que no está
        # respondida justo después de responderla.
        await _guardar(s)
        await s.refresh(encuesta)

        s.expunge_all()
        return encuesta, orden, vehiculo, taller


async def _cargar_por_token(
    sesion: AsyncSession, token: str
) -> tuple[Encuesta, OrdenServicio, Vehiculo, Taller]:
    encuesta = await sesion.scalar(select(Encuesta).where(Encuesta.token_publico == token))
    if encuesta is None:
        raise ErrorNoEncontrado("Este enlace no corresponde a ninguna encuesta.")

    orden = await sesion.get(OrdenServicio, encuesta.orden_id)
    vehiculo = await sesion.get(Vehiculo, orden.vehiculo_id) if orden else None
    taller = await sesion.get(Taller, encuesta.taller_id)
    if orden is None or vehiculo is None or taller is None:
        raise ErrorNoEncontrado("Este enlace ya no es válido.")

    return encuesta, orden, vehiculo, taller


# -----------------------------------------------------------------------------


def enlace(encuesta: Encuesta) -> str:
    return enlace_encuesta(encuesta.token_publico)


async def _releer(sesion: AsyncSession, encuesta_id: UUID) -> Encuesta:
    encuesta = await sesion.scalar(
        select(Encuesta).where(Encuesta.id == encuesta_id).execution_options(populate_existing=True)
    )
    if encuesta is None:  # pragma: no cover - acaba de insertarse
        raise ErrorNoEncontrado("La encuesta desapareció al crearla.")
    return encuesta


async def _guardar(sesion: AsyncSession) -> None:
    try:
        await sesion.flush()
    except (IntegrityError, DBAPIError) as exc:
        codigo = extraer_sqlstate(exc)
        if codigo == "23514":
            # Texto ya redactado por los CHECK de la tabla (notas fuera de rango).
            raise ErrorValidacion(str(exc).strip().splitlines()[0]) from exc
        if codigo == "23505":
            raise ErrorConflicto("Esa orden ya tiene una encuesta.") from exc
        if codigo == "23503":
            raise ErrorValidacion("La orden de la encuesta no existe en tu taller.") from exc
        raise
