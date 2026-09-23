"""La cola de avisos al cliente y el worker que la vacía.

Dos cosas se defienden aquí, y son de naturaleza distinta.

La primera es de seguridad: `authenticated` tiene privilegio de tabla sobre
`notificaciones`, así que cualquiera con sesión puede intentar insertar filas
saltándose la API. Si la política dejara elegir destinatario y contenido, la cola
sería un relé de correo abierto con el remitente del producto. Varias pruebas
escriben SQL a pelo, a propósito, para comprobar que Postgres lo impide.

La segunda es de comportamiento del worker: que lo que falla de forma pasajera se
reintente, que lo que no tiene arreglo no se reintente, y que la fila refleje lo
que de verdad pasó.

Sobre el reloj: estas pruebas apartan sus filas al futuro y llaman a
`procesar_lote` con un `ahora` explícito. Es lo que las hace deterministas aunque
haya un servidor de desarrollo levantado, con su worker embebido vaciando esta
misma cola.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database import sesion_rls, sesion_servicio
from app.core.exceptions import ErrorConflicto, ErrorValidacion
from app.core.roles import Rol
from app.core.security import UsuarioAutenticado
from app.modules.clientes import service as srv_clientes
from app.modules.clientes.schemas import ClienteCrear
from app.modules.diagnosticos import service as srv_diag
from app.modules.diagnosticos.schemas import ManoObraCrear
from app.modules.notificaciones import service
from app.modules.notificaciones.mensajeria import ErrorEnvio
from app.modules.notificaciones.plantillas import Correo
from app.modules.notificaciones.worker import MAX_INTENTOS, procesar_lote
from app.modules.ordenes import service as srv_ordenes
from app.modules.ordenes.estados import EstadoOrden as E
from app.modules.ordenes.schemas import CambioEstado, OrdenCrear
from app.modules.presupuestos import service as srv_presupuestos
from app.modules.presupuestos.schemas import PresupuestoEmitir
from app.modules.vehiculos import service as srv_vehiculos
from app.modules.vehiculos.schemas import VehiculoCrear

pytestmark = pytest.mark.integration


def _usuario(taller_id: UUID, rol: Rol = Rol.ADMIN_TALLER) -> UsuarioAutenticado:
    return UsuarioAutenticado(id=uuid4(), taller_id=taller_id, rol=rol)


# -----------------------------------------------------------------------------
# Transportes de mentira
# -----------------------------------------------------------------------------


class Buzon:
    """Se queda con lo que le den, para poder mirarlo."""

    def __init__(self) -> None:
        self.enviados: list[tuple[str, Correo, str, str | None]] = []

    async def enviar(
        self,
        *,
        destinatario: str,
        correo: Correo,
        nombre_remitente: str,
        responder_a: str | None = None,
    ) -> None:
        self.enviados.append((destinatario, correo, nombre_remitente, responder_a))


class Caido:
    """Un servidor de correo que no acepta nada."""

    def __init__(self, *, permanente: bool = False) -> None:
        self.permanente = permanente
        self.intentos = 0

    async def enviar(self, **_: object) -> None:
        self.intentos += 1
        raise ErrorEnvio("451 servidor no disponible", permanente=self.permanente)


# -----------------------------------------------------------------------------
# Escenario
# -----------------------------------------------------------------------------


@dataclass
class Escenario:
    taller: UUID
    cliente: UUID
    orden: UUID
    correo: str
    correo_taller: str
    nombre_taller: str


@pytest_asyncio.fixture
async def escenario() -> AsyncIterator[Escenario]:
    sfx = uuid4().hex[:8]
    correo = f"duenio.{sfx}@example.com"
    nombre_taller = f"Avisos {sfx}"

    async with sesion_servicio() as s:
        taller = (
            await s.execute(
                text("""
                    insert into public.talleres
                           (nombre, slug, prefijo_orden, tarifa_hora_default, telefono,
                            email, direccion)
                    values (:nombre, 'avisos-' || :sfx, 'AVS', 25, '+58 212 555 0177',
                            'taller@example.com', 'Calle 7 con Av. 4')
                    returning id
                """),
                {"sfx": sfx, "nombre": nombre_taller},
            )
        ).scalar_one()

    u = _usuario(taller)
    async with sesion_rls(u) as s:
        cliente = await srv_clientes.crear(s, ClienteCrear(nombre="Renzo Acevedo", email=correo), u)
        vehiculo = await srv_vehiculos.crear(
            s,
            VehiculoCrear(
                cliente_id=cliente.id, placa="AV321XY", marca="Chevrolet", modelo="Aveo", anio=2016
            ),
            u,
        )
        orden = await srv_ordenes.crear(
            s,
            OrdenCrear(
                cliente_id=cliente.id,
                vehiculo_id=vehiculo.id,
                motivo_ingreso="Ruido en la suspensión delantera",
            ),
            u,
        )
        await srv_diag.crear_mano_obra(
            s,
            orden.id,
            ManoObraCrear(descripcion="Cambio de amortiguadores", horas=Decimal("3")),
            u,
        )

    yield Escenario(
        taller=taller,
        cliente=cliente.id,
        orden=orden.id,
        correo=correo,
        correo_taller="taller@example.com",
        nombre_taller=nombre_taller,
    )

    async with sesion_servicio() as s:
        await s.execute(text("delete from public.talleres where id = :t"), {"t": taller})


# -----------------------------------------------------------------------------
# Utilidades
# -----------------------------------------------------------------------------


async def _enviar_presupuesto(e: Escenario) -> UUID:
    """Emite y envía un presupuesto, que es lo que encola el primer aviso."""
    u = _usuario(e.taller, Rol.ASESOR_SERVICIO)
    async with sesion_rls(u) as s:
        presupuesto = await srv_presupuestos.emitir(s, e.orden, PresupuestoEmitir(), u)
        await srv_presupuestos.enviar(s, presupuesto.id)
        return presupuesto.id


async def _apartar(taller: UUID) -> datetime:
    """Deja los avisos del taller listos para que los procese solo esta prueba.

    Devuelve el "ahora" que hay que pasarle a `procesar_lote`.

    Hace dos cosas, y la segunda importa más de lo que parece. Los programa para
    mañana, con lo que el worker que pueda estar corriendo de verdad —el que
    lleva embebido la API en desarrollo— nunca llegará a ellos, porque él mira el
    reloj del sistema. Y los devuelve al estado inicial, porque entre el momento
    en que el servicio encoló la fila y este UPDATE hay un hueco de milisegundos
    en el que ese otro worker pudo habérsela llevado ya: sin el reinicio, la
    prueba empezaría a veces desde una fila enviada o fallida, y fallaría sin que
    hubiera nada roto.
    """
    manana = datetime.now(UTC) + timedelta(days=1)
    async with sesion_servicio() as s:
        await s.execute(
            text("""
                update public.notificaciones
                   set programada_para = :manana,
                       estado = 'pendiente',
                       intentos = 0,
                       ultimo_error = null,
                       enviada_en = null
                 where taller_id = :t
            """),
            {"t": taller, "manana": manana},
        )
    return manana + timedelta(minutes=1)


async def _filas(taller: UUID) -> list[dict[str, object]]:
    async with sesion_servicio() as s:
        filas = await s.execute(
            text("""
                select id, plantilla, destinatario, estado, intentos, ultimo_error,
                       enviada_en, programada_para, datos
                  from public.notificaciones
                 where taller_id = :t
                 order by creado_en
            """),
            {"t": taller},
        )
        return [dict(f._mapping) for f in filas.fetchall()]


async def _token_presupuesto(presupuesto_id: UUID) -> str:
    async with sesion_servicio() as s:
        return (
            await s.execute(
                text("select token_publico from public.presupuestos where id = :p"),
                {"p": presupuesto_id},
            )
        ).scalar_one()


# -----------------------------------------------------------------------------
# Qué encola cada hecho del taller
# -----------------------------------------------------------------------------


async def test_enviar_el_presupuesto_encola_su_correo(escenario: Escenario) -> None:
    presupuesto = await _enviar_presupuesto(escenario)

    filas = await _filas(escenario.taller)
    assert len(filas) == 1
    assert filas[0]["plantilla"] == "presupuesto_enviado"
    assert filas[0]["destinatario"] == escenario.correo
    # La fila guarda una referencia, no el texto: el correo se redacta al enviarlo.
    assert filas[0]["datos"] == {"presupuesto_id": str(presupuesto)}


async def test_un_cliente_sin_correo_no_impide_enviar_el_presupuesto(
    escenario: Escenario,
) -> None:
    """Mucha gente deja solo un teléfono. El enlace se comparte a mano y ya."""
    u = _usuario(escenario.taller)
    async with sesion_rls(u) as s:
        await s.execute(
            text("update public.clientes set email = null where id = :c"),
            {"c": escenario.cliente},
        )

    await _enviar_presupuesto(escenario)

    assert await _filas(escenario.taller) == []


async def test_el_tecnico_avisa_de_que_el_vehiculo_esta_listo(escenario: Escenario) -> None:
    """El aviso más útil para el cliente lo dispara quien termina el trabajo.

    La política original solo dejaba encolar a administración y asesoría, así que
    este correo era justo el que no podía salir. Ver la migración 20260914000100.
    """
    admin = _usuario(escenario.taller)
    for estado in (E.EN_DIAGNOSTICO, E.PRESUPUESTO_PENDIENTE, E.APROBADO, E.EN_REPARACION):
        async with sesion_rls(admin) as s:
            await srv_ordenes.cambiar_estado(s, escenario.orden, CambioEstado(estado=estado), admin)

    tecnico = _usuario(escenario.taller, Rol.TECNICO)
    for estado in (E.CONTROL_CALIDAD, E.LISTO_PARA_ENTREGA):
        async with sesion_rls(tecnico) as s:
            await srv_ordenes.cambiar_estado(
                s, escenario.orden, CambioEstado(estado=estado), tecnico
            )

    filas = await _filas(escenario.taller)
    assert [f["plantilla"] for f in filas] == ["vehiculo_listo"]
    assert filas[0]["destinatario"] == escenario.correo


# -----------------------------------------------------------------------------
# Lo que Postgres impide, se pase o no por la API
# -----------------------------------------------------------------------------


async def test_no_se_puede_escribir_a_una_direccion_ajena_a_la_orden(
    escenario: Escenario,
) -> None:
    """El destinatario no se elige: es el cliente de esa orden.

    Sin esta regla, cualquiera con sesión podría usar el remitente del producto
    para mandarle lo que quisiera a quien quisiera.
    """
    u = _usuario(escenario.taller, Rol.ASESOR_SERVICIO)

    with pytest.raises(DBAPIError) as excinfo:
        async with sesion_rls(u) as s:
            await s.execute(
                text("""
                    insert into public.notificaciones
                           (taller_id, orden_id, destinatario, plantilla)
                    values (:t, :o, 'victima@example.com', 'presupuesto_enviado')
                """),
                {"t": escenario.taller, "o": escenario.orden},
            )

    assert "42501" in str(excinfo.value) or "row-level security" in str(excinfo.value).lower()


async def test_no_se_puede_encolar_una_plantilla_inventada(escenario: Escenario) -> None:
    """El worker solo sabe redactar tres avisos; la base solo acepta esos tres."""
    u = _usuario(escenario.taller, Rol.ASESOR_SERVICIO)

    with pytest.raises(DBAPIError) as excinfo:
        async with sesion_rls(u) as s:
            await s.execute(
                text("""
                    insert into public.notificaciones
                           (taller_id, orden_id, destinatario, plantilla)
                    values (:t, :o, :correo, 'promocion_verano')
                """),
                {"t": escenario.taller, "o": escenario.orden, "correo": escenario.correo},
            )

    fallo = str(excinfo.value)
    assert "23514" in fallo or "notificaciones_plantilla_conocida" in fallo


async def test_una_sesion_no_puede_marcar_un_aviso_como_enviado(escenario: Escenario) -> None:
    """El avance de la cola es del worker. Si no, el historial se podría maquillar."""
    await _enviar_presupuesto(escenario)
    # Apartada al futuro para que el worker que pueda estar corriendo de verdad
    # no la envíe mientras la prueba comprueba que sigue pendiente.
    await _apartar(escenario.taller)

    u = _usuario(escenario.taller, Rol.ASESOR_SERVICIO)
    async with sesion_rls(u) as s:
        resultado = await s.execute(
            text("update public.notificaciones set estado = 'enviada' where taller_id = :t"),
            {"t": escenario.taller},
        )

    assert resultado.rowcount == 0, "no hay política de UPDATE: la fila es intocable"
    assert (await _filas(escenario.taller))[0]["estado"] == "pendiente"


async def test_otro_taller_no_ve_esta_cola(escenario: Escenario) -> None:
    await _enviar_presupuesto(escenario)

    sfx = uuid4().hex[:8]
    async with sesion_servicio() as s:
        ajeno = (
            await s.execute(
                text("""
                    insert into public.talleres (nombre, slug, prefijo_orden)
                    values ('Ajeno ' || :sfx, 'ajeno-avs-' || :sfx, 'AJA')
                    returning id
                """),
                {"sfx": sfx},
            )
        ).scalar_one()

    try:
        async with sesion_rls(_usuario(ajeno)) as s:
            visibles = (
                (await s.execute(text("select id from public.notificaciones"))).scalars().all()
            )
        assert visibles == []
    finally:
        async with sesion_servicio() as s:
            await s.execute(text("delete from public.talleres where id = :t"), {"t": ajeno})


async def test_el_tecnico_no_ve_la_cola(escenario: Escenario) -> None:
    """Puede provocar un aviso, pero no leer a qué dirección se mandó."""
    await _enviar_presupuesto(escenario)

    async with sesion_rls(_usuario(escenario.taller, Rol.TECNICO)) as s:
        visibles = (await s.execute(text("select id from public.notificaciones"))).scalars().all()

    assert visibles == []


# -----------------------------------------------------------------------------
# El worker
# -----------------------------------------------------------------------------


async def test_el_worker_envia_y_deja_constancia(escenario: Escenario) -> None:
    presupuesto = await _enviar_presupuesto(escenario)
    token = await _token_presupuesto(presupuesto)
    ahora = await _apartar(escenario.taller)
    buzon = Buzon()

    resumen = await procesar_lote(buzon, ahora=ahora, solo_taller=escenario.taller)

    assert (resumen.enviadas, resumen.reintentos, resumen.fallidas) == (1, 0, 0)

    destinatario, correo, remitente, responder_a = buzon.enviados[0]
    assert destinatario == escenario.correo
    # El cliente ve el nombre del taller, y si responde le contesta al taller.
    assert remitente == escenario.nombre_taller
    assert responder_a == escenario.correo_taller
    assert token in correo.texto, "el enlace se arma al enviar, con el token real"
    assert "AV321XY" in correo.texto

    fila = (await _filas(escenario.taller))[0]
    assert fila["estado"] == "enviada"
    assert fila["enviada_en"] is not None
    assert fila["ultimo_error"] is None


async def test_un_fallo_pasajero_deja_la_fila_para_mas_tarde(escenario: Escenario) -> None:
    await _enviar_presupuesto(escenario)
    ahora = await _apartar(escenario.taller)

    resumen = await procesar_lote(Caido(), ahora=ahora, solo_taller=escenario.taller)

    assert (resumen.enviadas, resumen.reintentos, resumen.fallidas) == (0, 1, 0)

    fila = (await _filas(escenario.taller))[0]
    assert fila["estado"] == "pendiente", "un servidor caído se reintenta"
    assert fila["intentos"] == 1
    assert "451" in str(fila["ultimo_error"])
    assert fila["programada_para"] > ahora, "y no de inmediato"


async def test_tras_el_ultimo_intento_se_da_por_perdida(escenario: Escenario) -> None:
    """Insistir para siempre no entrega el correo y quema la reputación del remitente."""
    await _enviar_presupuesto(escenario)
    ahora = await _apartar(escenario.taller)

    async with sesion_servicio() as s:
        await s.execute(
            text("update public.notificaciones set intentos = :i where taller_id = :t"),
            {"t": escenario.taller, "i": MAX_INTENTOS - 1},
        )

    resumen = await procesar_lote(Caido(), ahora=ahora, solo_taller=escenario.taller)

    assert (resumen.enviadas, resumen.reintentos, resumen.fallidas) == (0, 0, 1)
    assert (await _filas(escenario.taller))[0]["estado"] == "fallida"


async def test_una_referencia_rota_no_se_reintenta(escenario: Escenario) -> None:
    """Reintentar no va a hacer aparecer un presupuesto que no existe."""
    u = _usuario(escenario.taller, Rol.ASESOR_SERVICIO)
    async with sesion_rls(u) as s:
        await s.execute(
            text("""
                insert into public.notificaciones
                       (taller_id, orden_id, destinatario, plantilla, datos)
                values (:t, :o, :correo, 'presupuesto_enviado',
                        jsonb_build_object('presupuesto_id', cast(:fantasma as text)))
            """),
            {
                "t": escenario.taller,
                "o": escenario.orden,
                "correo": escenario.correo,
                "fantasma": str(uuid4()),
            },
        )

    ahora = await _apartar(escenario.taller)
    buzon = Buzon()

    resumen = await procesar_lote(buzon, ahora=ahora, solo_taller=escenario.taller)

    assert (resumen.enviadas, resumen.fallidas) == (0, 1)
    assert buzon.enviados == [], "ni se intentó: no había nada que redactar"
    fila = (await _filas(escenario.taller))[0]
    assert fila["estado"] == "fallida"
    assert fila["intentos"] == 1


async def test_la_encuesta_se_marca_enviada_cuando_sale_el_correo(escenario: Escenario) -> None:
    """Hasta que el correo no sale, la ficha no debe decir que el cliente la tiene."""
    u = _usuario(escenario.taller)
    for estado in (
        E.EN_DIAGNOSTICO,
        E.PRESUPUESTO_PENDIENTE,
        E.APROBADO,
        E.EN_REPARACION,
        E.CONTROL_CALIDAD,
        E.LISTO_PARA_ENTREGA,
        E.ENTREGADO,
    ):
        async with sesion_rls(u) as s:
            await srv_ordenes.cambiar_estado(s, escenario.orden, CambioEstado(estado=estado), u)

    ahora = await _apartar(escenario.taller)

    async with sesion_servicio() as s:
        antes = (
            await s.execute(
                text("select enviada_en from public.encuestas where orden_id = :o"),
                {"o": escenario.orden},
            )
        ).scalar_one()
    assert antes is None

    await procesar_lote(Buzon(), ahora=ahora, solo_taller=escenario.taller)

    async with sesion_servicio() as s:
        despues = (
            await s.execute(
                text("select enviada_en from public.encuestas where orden_id = :o"),
                {"o": escenario.orden},
            )
        ).scalar_one()
    assert despues is not None


# -----------------------------------------------------------------------------
# Lo que puede hacer el taller con la cola
# -----------------------------------------------------------------------------


async def test_reintentar_encola_una_copia(escenario: Escenario) -> None:
    await _enviar_presupuesto(escenario)
    ahora = await _apartar(escenario.taller)
    await procesar_lote(Caido(permanente=True), ahora=ahora, solo_taller=escenario.taller)

    fallida = (await _filas(escenario.taller))[0]
    assert fallida["estado"] == "fallida"

    u = _usuario(escenario.taller, Rol.ASESOR_SERVICIO)
    async with sesion_rls(u) as s:
        destinatario = await service.reintentar(s, fallida["id"])  # type: ignore[arg-type]

    assert destinatario == escenario.correo
    filas = await _filas(escenario.taller)
    assert len(filas) == 2, "la fila fallida se conserva: es el historial de lo que pasó"
    assert filas[1]["datos"] == fallida["datos"]


async def test_no_se_reintenta_lo_que_no_ha_fallado(escenario: Escenario) -> None:
    await _enviar_presupuesto(escenario)
    pendiente = (await _filas(escenario.taller))[0]

    u = _usuario(escenario.taller, Rol.ASESOR_SERVICIO)
    async with sesion_rls(u) as s:
        with pytest.raises(ErrorConflicto, match=r"(?i)nada que reintentar"):
            await service.reintentar(s, pendiente["id"])  # type: ignore[arg-type]


async def test_reintentar_sin_correo_del_cliente_lo_dice(escenario: Escenario) -> None:
    """El mensaje tiene que llevar a la ficha del cliente, que es donde se arregla."""
    await _enviar_presupuesto(escenario)
    ahora = await _apartar(escenario.taller)
    await procesar_lote(Caido(permanente=True), ahora=ahora, solo_taller=escenario.taller)
    fallida = (await _filas(escenario.taller))[0]

    u = _usuario(escenario.taller, Rol.ASESOR_SERVICIO)
    async with sesion_rls(u) as s:
        await s.execute(
            text("update public.clientes set email = null where id = :c"),
            {"c": escenario.cliente},
        )
        with pytest.raises(ErrorValidacion, match=r"(?i)no tiene correo"):
            await service.reintentar(s, fallida["id"])  # type: ignore[arg-type]


async def test_la_vista_previa_es_el_correo_que_saldra(escenario: Escenario) -> None:
    """Se redacta con el mismo código que usa el worker: no es una aproximación."""
    presupuesto = await _enviar_presupuesto(escenario)
    token = await _token_presupuesto(presupuesto)
    fila = (await _filas(escenario.taller))[0]

    u = _usuario(escenario.taller, Rol.ASESOR_SERVICIO)
    async with sesion_rls(u) as s:
        n, correo = await service.vista_previa(s, fila["id"])  # type: ignore[arg-type]

    assert n.destinatario == escenario.correo
    assert escenario.nombre_taller in correo.html
    assert token in correo.html
    assert "AV321XY" in correo.texto
