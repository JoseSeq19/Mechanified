"""Checklist configurable y control de calidad, contra la base real.

Lo que defienden estas pruebas: que un vehículo no sale como "listo" con un
punto obligatorio sin revisar —ni por la API ni saltándosela—, y que cerrar la
inspección mueve la orden al sitio correcto.
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
from app.modules.calidad import service
from app.modules.calidad.models import ResultadoCheck, ResultadoControl
from app.modules.calidad.schemas import (
    CerrarControl,
    ControlIniciar,
    PlantillaCrear,
    PuntoCrear,
    PuntoEditar,
    RespuestaEditar,
)
from app.modules.clientes import service as srv_clientes
from app.modules.clientes.schemas import ClienteCrear
from app.modules.ordenes import service as srv_ordenes
from app.modules.ordenes.estados import EstadoOrden as E
from app.modules.ordenes.schemas import CambioEstado, OrdenCrear
from app.modules.vehiculos import service as srv_vehiculos
from app.modules.vehiculos.schemas import VehiculoCrear

pytestmark = pytest.mark.integration


def _usuario(taller_id: UUID, rol: Rol = Rol.TECNICO) -> UsuarioAutenticado:
    return UsuarioAutenticado(id=uuid4(), taller_id=taller_id, rol=rol)


@dataclass
class Escenario:
    taller: UUID
    cliente: UUID
    vehiculo: UUID
    orden: UUID
    plantilla: UUID


async def _nueva_orden(taller: UUID, cliente: UUID, vehiculo: UUID) -> UUID:
    asesor = _usuario(taller, Rol.ASESOR_SERVICIO)
    async with sesion_rls(asesor) as s:
        orden = await srv_ordenes.crear(
            s,
            OrdenCrear(cliente_id=cliente, vehiculo_id=vehiculo, motivo_ingreso="Revisión"),
            asesor,
        )
        return orden.id


async def _llevar_a_calidad(taller: UUID, orden: UUID) -> None:
    """Recorre el flujo real hasta control_calidad, con el rol de cada paso."""
    asesor, tecnico = Rol.ASESOR_SERVICIO, Rol.TECNICO
    for estado, rol in [
        (E.EN_DIAGNOSTICO, asesor),
        (E.PRESUPUESTO_PENDIENTE, tecnico),
        (E.APROBADO, asesor),
        (E.EN_REPARACION, tecnico),
        (E.CONTROL_CALIDAD, tecnico),
    ]:
        u = _usuario(taller, rol)
        async with sesion_rls(u) as s:
            await srv_ordenes.cambiar_estado(s, orden, CambioEstado(estado=estado), u)


@pytest_asyncio.fixture
async def escenario() -> AsyncIterator[Escenario]:
    sfx = uuid4().hex[:8]
    async with sesion_servicio() as s:
        taller = (
            await s.execute(
                text("""
                    insert into public.talleres (nombre, slug, prefijo_orden)
                    values ('Qc ' || :sfx, 'qc-' || :sfx, 'QCA')
                    returning id
                """),
                {"sfx": sfx},
            )
        ).scalar_one()

    asesor = _usuario(taller, Rol.ASESOR_SERVICIO)
    async with sesion_rls(asesor) as s:
        cliente = await srv_clientes.crear(s, ClienteCrear(nombre="Carmen Odreman"), asesor)
        vehiculo = await srv_vehiculos.crear(
            s,
            VehiculoCrear(cliente_id=cliente.id, placa="XY456ZW", marca="Chevrolet", modelo="Aveo"),
            asesor,
        )
        cliente_id, vehiculo_id = cliente.id, vehiculo.id

    admin = _usuario(taller, Rol.ADMIN_TALLER)
    async with sesion_rls(admin) as s:
        plantilla = await service.crear_plantilla(
            s,
            PlantillaCrear(
                nombre="Revisión previa a entrega",
                puntos=[
                    PuntoCrear(descripcion="La falla reportada ya no se reproduce"),
                    PuntoCrear(descripcion="Sin testigos encendidos en el tablero"),
                    PuntoCrear(descripcion="Interior limpio", obligatorio=False),
                ],
            ),
            admin,
        )
        plantilla_id = plantilla.id

    orden = await _nueva_orden(taller, cliente_id, vehiculo_id)
    await _llevar_a_calidad(taller, orden)

    yield Escenario(
        taller=taller,
        cliente=cliente_id,
        vehiculo=vehiculo_id,
        orden=orden,
        plantilla=plantilla_id,
    )

    async with sesion_servicio() as s:
        await s.execute(text("delete from public.talleres where id = :t"), {"t": taller})


async def _iniciar(e: Escenario, orden: UUID | None = None):
    u = _usuario(e.taller)
    async with sesion_rls(u) as s:
        return await service.iniciar_control(
            s, orden or e.orden, ControlIniciar(plantilla_id=e.plantilla), u
        )


async def _marcar(e: Escenario, respuesta_id: UUID, resultado: ResultadoCheck) -> None:
    u = _usuario(e.taller)
    async with sesion_rls(u) as s:
        await service.actualizar_respuesta(s, respuesta_id, RespuestaEditar(resultado=resultado))


async def _cerrar(e: Escenario, control_id: UUID, aprobado: bool, obs: str | None = None):
    u = _usuario(e.taller)
    async with sesion_rls(u) as s:
        return await service.cerrar_control(
            s, control_id, CerrarControl(aprobado=aprobado, observaciones=obs), u
        )


async def _estado_orden(e: Escenario, orden: UUID | None = None) -> E:
    async with sesion_rls(_usuario(e.taller)) as s:
        return (await srv_ordenes.obtener(s, orden or e.orden)).estado


# -----------------------------------------------------------------------------
# Plantillas
# -----------------------------------------------------------------------------


async def test_la_plantilla_se_crea_con_sus_puntos_en_orden(escenario: Escenario) -> None:
    async with sesion_rls(_usuario(escenario.taller)) as s:
        p = await service.obtener_plantilla(s, escenario.plantilla)

    assert [x.orden_visual for x in p.puntos] == [1, 2, 3]
    assert [x.obligatorio for x in p.puntos] == [True, True, False]


async def test_nombre_de_plantilla_repetido_da_conflicto(escenario: Escenario) -> None:
    admin = _usuario(escenario.taller, Rol.ADMIN_TALLER)
    async with sesion_rls(admin) as s:
        with pytest.raises(ErrorConflicto, match="(?i)revisión previa"):
            await service.crear_plantilla(
                s, PlantillaCrear(nombre="revisión previa a entrega"), admin
            )


async def test_el_tecnico_no_define_plantillas(escenario: Escenario) -> None:
    """Lo rechaza RLS: el criterio de calidad es cosa de administración."""
    tecnico = _usuario(escenario.taller)
    async with sesion_rls(tecnico) as s:
        with pytest.raises(DBAPIError):
            await service.crear_plantilla(s, PlantillaCrear(nombre="La mía"), tecnico)


# -----------------------------------------------------------------------------
# Iniciar
# -----------------------------------------------------------------------------


async def test_iniciar_copia_los_puntos(escenario: Escenario) -> None:
    c = await _iniciar(escenario)

    assert c.resultado == ResultadoControl.PENDIENTE.value
    assert len(c.respuestas) == 3
    assert all(r.resultado is ResultadoCheck.NO_APLICA for r in c.respuestas)
    assert len(service.pendientes(c)) == 2, "los dos obligatorios empiezan sin conformidad"


async def test_no_se_abren_dos_controles_a_la_vez(escenario: Escenario) -> None:
    await _iniciar(escenario)

    with pytest.raises(ErrorConflicto, match="en curso"):
        await _iniciar(escenario)


async def test_una_plantilla_vacia_no_sirve(escenario: Escenario) -> None:
    admin = _usuario(escenario.taller, Rol.ADMIN_TALLER)
    async with sesion_rls(admin) as s:
        vacia = await service.crear_plantilla(s, PlantillaCrear(nombre="Vacía"), admin)
        vacia_id = vacia.id

    u = _usuario(escenario.taller)
    async with sesion_rls(u) as s:
        with pytest.raises(ErrorValidacion, match="no tiene puntos"):
            await service.iniciar_control(
                s, escenario.orden, ControlIniciar(plantilla_id=vacia_id), u
            )


async def test_editar_la_plantilla_no_reescribe_una_inspeccion(escenario: Escenario) -> None:
    c = await _iniciar(escenario)
    punto = c.respuestas[0].item_id
    original = c.respuestas[0].descripcion

    admin = _usuario(escenario.taller, Rol.ADMIN_TALLER)
    async with sesion_rls(admin) as s:
        await service.actualizar_punto(s, punto, PuntoEditar(descripcion="Texto nuevo del punto"))

    async with sesion_rls(_usuario(escenario.taller)) as s:
        sigue = await service.obtener_control(s, c.id)

    assert sigue.respuestas[0].descripcion == original


# -----------------------------------------------------------------------------
# Aprobar
# -----------------------------------------------------------------------------


async def test_no_se_aprueba_con_obligatorios_sin_conformidad(escenario: Escenario) -> None:
    c = await _iniciar(escenario)
    await _marcar(escenario, c.respuestas[0].id, ResultadoCheck.OK)

    with pytest.raises(ErrorValidacion, match="1 punto obligatorio") as excinfo:
        await _cerrar(escenario, c.id, aprobado=True)

    assert excinfo.value.detalles["pendientes"] == ["Sin testigos encendidos en el tablero"]
    assert await _estado_orden(escenario) is E.CONTROL_CALIDAD


async def test_la_base_tambien_lo_impide(escenario: Escenario) -> None:
    """Saltándose el servicio, mch_controles_calidad_cierre sigue ahí."""
    c = await _iniciar(escenario)

    async with sesion_rls(_usuario(escenario.taller)) as s:
        with pytest.raises(DBAPIError) as excinfo:
            await s.execute(
                text("update public.controles_calidad set resultado = 'aprobado' where id = :id"),
                {"id": c.id},
            )

    assert "obligatorios" in str(excinfo.value)


async def test_no_aplica_en_un_obligatorio_tambien_bloquea(escenario: Escenario) -> None:
    """Si un punto puede no aplicar, no debería ser obligatorio en la plantilla."""
    c = await _iniciar(escenario)
    await _marcar(escenario, c.respuestas[0].id, ResultadoCheck.OK)
    await _marcar(escenario, c.respuestas[1].id, ResultadoCheck.NO_APLICA)

    with pytest.raises(ErrorValidacion, match="sin conformidad"):
        await _cerrar(escenario, c.id, aprobado=True)


async def test_aprobar_deja_la_orden_lista_para_entrega(escenario: Escenario) -> None:
    c = await _iniciar(escenario)
    for r in c.respuestas[:2]:
        await _marcar(escenario, r.id, ResultadoCheck.OK)
    # El opcional se queda sin marcar: no bloquea.

    cerrado = await _cerrar(escenario, c.id, aprobado=True)

    assert cerrado.resultado == ResultadoControl.APROBADO.value
    assert cerrado.cerrado_en is not None
    assert await _estado_orden(escenario) is E.LISTO_PARA_ENTREGA


async def test_un_control_cerrado_ya_no_se_toca(escenario: Escenario) -> None:
    c = await _iniciar(escenario)
    for r in c.respuestas[:2]:
        await _marcar(escenario, r.id, ResultadoCheck.OK)
    await _cerrar(escenario, c.id, aprobado=True)

    with pytest.raises(ErrorConflicto, match="no admite cambios"):
        await _marcar(escenario, c.respuestas[2].id, ResultadoCheck.OK)


# -----------------------------------------------------------------------------
# Rechazar
# -----------------------------------------------------------------------------


async def test_rechazar_exige_observaciones(escenario: Escenario) -> None:
    c = await _iniciar(escenario)

    with pytest.raises(ErrorValidacion, match="observaciones"):
        await _cerrar(escenario, c.id, aprobado=False)


async def test_rechazar_devuelve_la_orden_a_reparacion(escenario: Escenario) -> None:
    c = await _iniciar(escenario)

    await _cerrar(escenario, c.id, aprobado=False, obs="Sigue el ruido en la rueda delantera")

    assert await _estado_orden(escenario) is E.EN_REPARACION

    async with sesion_rls(_usuario(escenario.taller)) as s:
        eventos = await srv_ordenes.historial(s, escenario.orden)
    assert "Sigue el ruido en la rueda delantera" in (eventos[-1].comentario or "")


async def test_tras_rechazar_se_puede_volver_a_inspeccionar(escenario: Escenario) -> None:
    c = await _iniciar(escenario)
    await _cerrar(escenario, c.id, aprobado=False, obs="Falta ajustar frenos")

    tecnico = _usuario(escenario.taller)
    async with sesion_rls(tecnico) as s:
        await srv_ordenes.cambiar_estado(
            s, escenario.orden, CambioEstado(estado=E.CONTROL_CALIDAD), tecnico
        )

    segundo = await _iniciar(escenario)
    assert segundo.id != c.id


# -----------------------------------------------------------------------------
# Límites
# -----------------------------------------------------------------------------


async def test_si_la_orden_no_esta_en_calidad_no_se_mueve(escenario: Escenario) -> None:
    """Llenar el checklist antes de tiempo no fuerza el estado de la orden."""
    otra = await _nueva_orden(escenario.taller, escenario.cliente, escenario.vehiculo)
    c = await _iniciar(escenario, orden=otra)
    for r in c.respuestas[:2]:
        await _marcar(escenario, r.id, ResultadoCheck.OK)

    await _cerrar(escenario, c.id, aprobado=True)

    assert await _estado_orden(escenario, otra) is E.RECIBIDO


async def test_no_se_inspecciona_una_orden_cerrada(escenario: Escenario) -> None:
    otra = await _nueva_orden(escenario.taller, escenario.cliente, escenario.vehiculo)
    asesor = _usuario(escenario.taller, Rol.ASESOR_SERVICIO)
    async with sesion_rls(asesor) as s:
        await srv_ordenes.cambiar_estado(
            s, otra, CambioEstado(estado=E.CANCELADO, comentario="Prueba"), asesor
        )

    with pytest.raises(ErrorValidacion, match="ya no se inspecciona"):
        await _iniciar(escenario, orden=otra)


async def test_no_ve_controles_de_otro_taller(escenario: Escenario) -> None:
    c = await _iniciar(escenario)

    async with sesion_rls(_usuario(uuid4())) as s:
        with pytest.raises(ErrorNoEncontrado):
            await service.obtener_control(s, c.id)
