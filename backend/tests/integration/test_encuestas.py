"""Encuestas de satisfacción: nacen solas al entregar y las responde el cliente.

Lo que defienden estas pruebas:

  - Que la encuesta no dependa de que alguien se acuerde de crearla. Si nace de
    la entrega, existe siempre; si naciera de un botón, existiría a veces.
  - Que responder desde el enlace funcione sin cuenta y una sola vez.
  - Que las cifras que verá el taller salgan de lo que de verdad contestaron.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database import sesion_rls, sesion_servicio
from app.core.exceptions import ErrorConflicto, ErrorNoEncontrado, ErrorValidacion
from app.core.roles import Rol
from app.core.security import UsuarioAutenticado
from app.modules.clientes import service as srv_clientes
from app.modules.clientes.schemas import ClienteCrear
from app.modules.encuestas import service
from app.modules.encuestas.schemas import RespuestaCliente
from app.modules.ordenes import service as srv_ordenes
from app.modules.ordenes.estados import EstadoOrden as E
from app.modules.ordenes.schemas import CambioEstado, OrdenCrear
from app.modules.vehiculos import service as srv_vehiculos
from app.modules.vehiculos.schemas import VehiculoCrear
from app.shared.paginacion import ParametrosPagina

pytestmark = pytest.mark.integration

#: El camino completo del taller, de la recepción a la entrega.
HASTA_ENTREGA = (
    E.EN_DIAGNOSTICO,
    E.PRESUPUESTO_PENDIENTE,
    E.APROBADO,
    E.EN_REPARACION,
    E.CONTROL_CALIDAD,
    E.LISTO_PARA_ENTREGA,
    E.ENTREGADO,
)


def _usuario(taller_id: UUID, rol: Rol = Rol.ADMIN_TALLER) -> UsuarioAutenticado:
    return UsuarioAutenticado(id=uuid4(), taller_id=taller_id, rol=rol)


@dataclass
class Escenario:
    taller: UUID
    cliente: UUID
    vehiculo: UUID
    orden: UUID
    correo: str


@pytest_asyncio.fixture
async def escenario() -> AsyncIterator[Escenario]:
    sfx = uuid4().hex[:8]
    correo = f"duenio.{sfx}@example.com"

    async with sesion_servicio() as s:
        taller = (
            await s.execute(
                text("""
                    insert into public.talleres
                           (nombre, slug, prefijo_orden, telefono, email, direccion)
                    values ('Enc ' || :sfx, 'enc-' || :sfx, 'ENC',
                            '+58 212 555 0199', 'contacto@example.com', 'Av. Principal 45')
                    returning id
                """),
                {"sfx": sfx},
            )
        ).scalar_one()

    u = _usuario(taller)
    async with sesion_rls(u) as s:
        cliente = await srv_clientes.crear(
            s, ClienteCrear(nombre="Marisol Quintero", email=correo), u
        )
        vehiculo = await srv_vehiculos.crear(
            s,
            VehiculoCrear(
                cliente_id=cliente.id, placa="EN123CD", marca="Mazda", modelo="3", anio=2020
            ),
            u,
        )
        orden = await srv_ordenes.crear(
            s,
            OrdenCrear(
                cliente_id=cliente.id,
                vehiculo_id=vehiculo.id,
                motivo_ingreso="Revisión de 40.000 km",
            ),
            u,
        )

    yield Escenario(
        taller=taller,
        cliente=cliente.id,
        vehiculo=vehiculo.id,
        orden=orden.id,
        correo=correo,
    )

    async with sesion_servicio() as s:
        await s.execute(text("delete from public.talleres where id = :t"), {"t": taller})


async def _entregar(taller: UUID, orden_id: UUID) -> None:
    """Lleva la orden por todo el flujo hasta que el cliente se lleva el coche."""
    u = _usuario(taller)
    for estado in HASTA_ENTREGA:
        async with sesion_rls(u) as s:
            await srv_ordenes.cambiar_estado(s, orden_id, CambioEstado(estado=estado), u)


async def _otra_orden(e: Escenario, placa: str, correo: str | None) -> UUID:
    """Otra orden del mismo taller, con su propio cliente."""
    u = _usuario(e.taller)
    async with sesion_rls(u) as s:
        cliente = await srv_clientes.crear(
            s, ClienteCrear(nombre=f"Cliente {placa}", email=correo), u
        )
        vehiculo = await srv_vehiculos.crear(
            s,
            VehiculoCrear(cliente_id=cliente.id, placa=placa, marca="Kia", modelo="Rio"),
            u,
        )
        orden = await srv_ordenes.crear(
            s,
            OrdenCrear(
                cliente_id=cliente.id, vehiculo_id=vehiculo.id, motivo_ingreso="Cambio de aceite"
            ),
            u,
        )
    return orden.id


async def _avisos(taller: UUID, orden_id: UUID) -> list[tuple[str, str]]:
    """Qué se encoló para esa orden y a quién, leído sin RLS para verlo todo.

    A propósito no se mira el estado: si hay un servidor de desarrollo
    levantado, su worker embebido está vaciando esta misma cola mientras corre
    la prueba, y una fila puede pasar a `enviada` en cualquier momento. El
    estado se prueba donde se controla el reloj: `test_notificaciones`.
    """
    async with sesion_servicio() as s:
        filas = await s.execute(
            text("""
                select plantilla, destinatario
                  from public.notificaciones
                 where taller_id = :t and orden_id = :o
                 order by creado_en
            """),
            {"t": taller, "o": orden_id},
        )
        return [(f[0], f[1]) for f in filas.fetchall()]


# -----------------------------------------------------------------------------
# Nace con la entrega
# -----------------------------------------------------------------------------


async def test_entregar_crea_la_encuesta_y_encola_su_correo(escenario: Escenario) -> None:
    await _entregar(escenario.taller, escenario.orden)

    u = _usuario(escenario.taller)
    async with sesion_rls(u) as s:
        encuesta = await service.obtener_de_orden(s, escenario.orden)

    assert encuesta is not None
    assert not encuesta.respondida
    assert len(encuesta.token_publico) >= 32, "el enlace necesita un token opaco"

    avisos = await _avisos(escenario.taller, escenario.orden)
    assert ("encuesta_satisfaccion", escenario.correo) in avisos


async def test_antes_de_entregar_no_hay_encuesta(escenario: Escenario) -> None:
    """Preguntar por el servicio antes de devolver el vehículo no tiene sentido."""
    u = _usuario(escenario.taller)
    async with sesion_rls(u) as s:
        assert await service.obtener_de_orden(s, escenario.orden) is None

    async with sesion_rls(u) as s:
        with pytest.raises(ErrorValidacion, match=r"(?i)ya tiene su"):
            await service.enviar(s, escenario.orden)


async def test_un_cliente_sin_correo_tiene_encuesta_igual(escenario: Escenario) -> None:
    """Quien solo dejó un teléfono también puede opinar: el enlace se comparte a mano."""
    orden = await _otra_orden(escenario, "EN456ZW", correo=None)
    await _entregar(escenario.taller, orden)

    u = _usuario(escenario.taller)
    async with sesion_rls(u) as s:
        encuesta = await service.obtener_de_orden(s, orden)

    assert encuesta is not None
    assert await _avisos(escenario.taller, orden) == [], "sin correo no hay nada que encolar"


async def test_reenviar_no_duplica_la_cola(escenario: Escenario) -> None:
    """Dos clics seguidos en "reenviar" no son dos correos para el cliente.

    Las dos llamadas van en la misma transacción: lo que se cuenta es entonces
    lo que decidió el servicio, sin que el worker pueda haberse llevado una fila
    por el camino.
    """
    await _entregar(escenario.taller, escenario.orden)

    u = _usuario(escenario.taller, Rol.ASESOR_SERVICIO)
    async with sesion_rls(u) as s:
        for _ in range(2):
            _, destinatario = await service.enviar(s, escenario.orden)
            assert destinatario == escenario.correo

        pendientes = await s.scalar(
            text("""
                select count(*) from public.notificaciones
                 where orden_id = :o
                   and plantilla = 'encuesta_satisfaccion'
                   and estado = 'pendiente'
            """),
            {"o": escenario.orden},
        )

    assert pendientes == 1


# -----------------------------------------------------------------------------
# El cliente responde desde el enlace
# -----------------------------------------------------------------------------


async def _token(escenario: Escenario, orden_id: UUID | None = None) -> str:
    u = _usuario(escenario.taller)
    async with sesion_rls(u) as s:
        encuesta = await service.obtener_de_orden(s, orden_id or escenario.orden)
    assert encuesta is not None
    return encuesta.token_publico


async def test_responder_sin_cuenta_sella_la_fecha(escenario: Escenario) -> None:
    await _entregar(escenario.taller, escenario.orden)
    token = await _token(escenario)

    encuesta, orden, vehiculo, taller = await service.obtener_por_token(token)
    assert not encuesta.respondida
    assert orden.folio.startswith("ENC-")
    assert vehiculo.placa == "EN123CD"
    assert taller.nombre.startswith("Enc ")

    encuesta, *_ = await service.responder_por_token(
        token,
        RespuestaCliente(
            puntaje_atencion=5,
            puntaje_tiempo=4,
            puntaje_calidad=5,
            recomendaria=9,
            comentario="  Todo muy claro, gracias  ",
        ),
    )

    assert encuesta.respondida, "la fecha la sella el trigger al llegar la primera nota"
    assert encuesta.puntaje_atencion == 5
    assert encuesta.recomendaria == 9
    assert encuesta.comentario == "Todo muy claro, gracias"


async def test_no_se_responde_dos_veces(escenario: Escenario) -> None:
    """Si no, quien quisiera podría mover la media del taller a base de recargar."""
    await _entregar(escenario.taller, escenario.orden)
    token = await _token(escenario)
    respuesta = RespuestaCliente(
        puntaje_atencion=4, puntaje_tiempo=4, puntaje_calidad=4, recomendaria=8
    )

    await service.responder_por_token(token, respuesta)

    with pytest.raises(ErrorConflicto, match=r"(?i)ya respondiste"):
        await service.responder_por_token(token, respuesta)


async def test_no_se_reenvia_una_encuesta_ya_respondida(escenario: Escenario) -> None:
    await _entregar(escenario.taller, escenario.orden)
    await service.responder_por_token(
        await _token(escenario),
        RespuestaCliente(puntaje_atencion=3, puntaje_tiempo=3, puntaje_calidad=3, recomendaria=7),
    )

    u = _usuario(escenario.taller, Rol.ASESOR_SERVICIO)
    async with sesion_rls(u) as s:
        with pytest.raises(ErrorConflicto, match=r"(?i)ya respondió"):
            await service.enviar(s, escenario.orden)


async def test_un_token_inventado_no_abre_nada() -> None:
    with pytest.raises(ErrorNoEncontrado):
        await service.obtener_por_token("a" * 64)


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("puntaje_atencion", 0), ("puntaje_calidad", 6), ("recomendaria", 11)],
)
def test_las_notas_fuera_de_escala_se_rechazan(campo: str, valor: int) -> None:
    """La escala la fija el esquema antes de tocar la base, que la repite en un CHECK."""
    base = {
        "puntaje_atencion": 4,
        "puntaje_tiempo": 4,
        "puntaje_calidad": 4,
        "recomendaria": 8,
    }
    with pytest.raises(ValueError):
        RespuestaCliente(**{**base, campo: valor})


# -----------------------------------------------------------------------------
# Lo que ve el taller
# -----------------------------------------------------------------------------


async def test_el_resumen_promedia_solo_lo_contestado(escenario: Escenario) -> None:
    otra = await _otra_orden(escenario, "EN789QP", correo=f"otro.{uuid4().hex[:6]}@example.com")
    await _entregar(escenario.taller, escenario.orden)
    await _entregar(escenario.taller, otra)

    # Un promotor y un detractor: el NPS se anula, la media no.
    await service.responder_por_token(
        await _token(escenario),
        RespuestaCliente(puntaje_atencion=5, puntaje_tiempo=5, puntaje_calidad=5, recomendaria=10),
    )
    await service.responder_por_token(
        await _token(escenario, otra),
        RespuestaCliente(puntaje_atencion=3, puntaje_tiempo=1, puntaje_calidad=3, recomendaria=4),
    )

    u = _usuario(escenario.taller)
    async with sesion_rls(u) as s:
        resumen = await service.resumen(s)
        filas, total = await service.listar(s, solo_respondidas=True, pagina=ParametrosPagina())

    assert resumen.enviadas == 2
    assert resumen.respondidas == 2
    assert resumen.tasa_respuesta == 100.0
    assert resumen.promedio_atencion == 4.0
    assert resumen.promedio_tiempo == 3.0
    assert resumen.nps == 0
    assert (resumen.promotores, resumen.pasivos, resumen.detractores) == (1, 0, 1)

    assert total == 2
    folios = {o.folio for _, o, _, _ in filas}
    assert len(folios) == 2, "el listado trae la orden de cada encuesta"


async def test_sin_respuestas_el_indicador_queda_en_blanco(escenario: Escenario) -> None:
    """Un NPS de 0 sin datos se leería como "regular", y no es eso."""
    await _entregar(escenario.taller, escenario.orden)

    u = _usuario(escenario.taller)
    async with sesion_rls(u) as s:
        resumen = await service.resumen(s)

    assert resumen.enviadas == 1
    assert resumen.respondidas == 0
    assert resumen.tasa_respuesta == 0.0
    assert resumen.nps is None
    assert resumen.promedio_calidad is None


# -----------------------------------------------------------------------------
# Aislamiento y permisos
# -----------------------------------------------------------------------------


async def test_otro_taller_no_ve_ni_toca_estas_encuestas(escenario: Escenario) -> None:
    await _entregar(escenario.taller, escenario.orden)

    sfx = uuid4().hex[:8]
    async with sesion_servicio() as s:
        ajeno = (
            await s.execute(
                text("""
                    insert into public.talleres (nombre, slug, prefijo_orden)
                    values ('Ajeno ' || :sfx, 'ajeno-' || :sfx, 'AJE')
                    returning id
                """),
                {"sfx": sfx},
            )
        ).scalar_one()

    try:
        u = _usuario(ajeno)
        async with sesion_rls(u) as s:
            visibles = (await s.execute(text("select id from public.encuestas"))).scalars().all()
        assert visibles == []

        # Y tampoco puede crear una encuesta sobre una orden que no es suya.
        with pytest.raises(DBAPIError):
            async with sesion_rls(u) as s:
                await s.execute(
                    text("insert into public.encuestas (taller_id, orden_id) values (:t, :o)"),
                    {"t": ajeno, "o": escenario.orden},
                )
    finally:
        async with sesion_servicio() as s:
            await s.execute(text("delete from public.talleres where id = :t"), {"t": ajeno})


async def test_el_tecnico_no_crea_encuestas(escenario: Escenario) -> None:
    """Es del mostrador: quien entrega el vehículo es quien pregunta qué tal fue.

    La barrera real es la política RLS, así que se prueba escribiendo directo
    contra la base, sin pasar por el servicio.
    """
    await _entregar(escenario.taller, escenario.orden)
    otra = await _otra_orden(escenario, "EN999AA", correo=None)

    with pytest.raises(DBAPIError) as excinfo:
        async with sesion_rls(_usuario(escenario.taller, Rol.TECNICO)) as s:
            await s.execute(
                text("insert into public.encuestas (taller_id, orden_id) values (:t, :o)"),
                {"t": escenario.taller, "o": otra},
            )

    assert "42501" in str(excinfo.value) or "row-level security" in str(excinfo.value).lower()
