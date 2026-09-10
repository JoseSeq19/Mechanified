"""Órdenes de servicio contra la base real, con RLS activo.

Además de lo habitual (aislamiento, permisos), estas pruebas verifican que la
máquina de estados de Python y la de Postgres siguen coincidiendo: el camino
feliz se recorre con los roles reales, así que si una de las dos cambia sin la
otra, falla aquí.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.database import sesion_rls, sesion_servicio
from app.core.exceptions import ErrorNoEncontrado, ErrorPermiso, ErrorValidacion
from app.core.roles import Rol
from app.core.security import UsuarioAutenticado
from app.modules.clientes import service as srv_clientes
from app.modules.clientes.schemas import ClienteCrear
from app.modules.ordenes import service
from app.modules.ordenes.estados import EstadoOrden as E
from app.modules.ordenes.schemas import CambioEstado, OrdenCrear, OrdenEditar
from app.modules.vehiculos import service as srv_vehiculos
from app.modules.vehiculos.schemas import VehiculoCrear
from app.shared.paginacion import ParametrosPagina

pytestmark = pytest.mark.integration

PAGINA = ParametrosPagina(limite=50, desplazamiento=0)


def _usuario(taller_id: UUID, rol: Rol = Rol.ASESOR_SERVICIO) -> UsuarioAutenticado:
    return UsuarioAutenticado(id=uuid4(), taller_id=taller_id, rol=rol)


@dataclass
class Taller:
    id: UUID
    cliente_id: UUID
    vehiculo_id: UUID


@dataclass
class Escenario:
    a: Taller
    b: Taller


async def _montar_taller(taller_id: UUID, placa: str, nombre: str) -> Taller:
    u = _usuario(taller_id)
    async with sesion_rls(u) as s:
        cliente = await srv_clientes.crear(s, ClienteCrear(nombre=nombre), u)
        vehiculo = await srv_vehiculos.crear(
            s,
            VehiculoCrear(cliente_id=cliente.id, placa=placa, marca="Toyota", modelo="Corolla"),
            u,
        )
        return Taller(id=taller_id, cliente_id=cliente.id, vehiculo_id=vehiculo.id)


@pytest_asyncio.fixture
async def escenario() -> AsyncIterator[Escenario]:
    sfx = uuid4().hex[:8]
    async with sesion_servicio() as s:
        filas = await s.execute(
            text("""
                insert into public.talleres (nombre, slug, prefijo_orden)
                values ('Ord A ' || :sfx, 'ord-a-' || :sfx, 'ODA'),
                       ('Ord B ' || :sfx, 'ord-b-' || :sfx, 'ODB')
                returning id
            """),
            {"sfx": sfx},
        )
        ta, tb = (r[0] for r in filas.fetchall())

    yield Escenario(
        a=await _montar_taller(ta, "AB123CD", "Dueño A"),
        b=await _montar_taller(tb, "XY456ZW", "Dueño B"),
    )

    async with sesion_servicio() as s:
        await s.execute(text("delete from public.talleres where id = any(:ids)"), {"ids": [ta, tb]})


def _alta(t: Taller, **extra: object) -> OrdenCrear:
    base = {
        "cliente_id": t.cliente_id,
        "vehiculo_id": t.vehiculo_id,
        "motivo_ingreso": "Chillido metálico al frenar en bajada",
    }
    return OrdenCrear(**{**base, **extra})  # type: ignore[arg-type]


async def _crear(t: Taller) -> UUID:
    u = _usuario(t.id)
    async with sesion_rls(u) as s:
        return (await service.crear(s, _alta(t), u)).id


async def _mover(
    t: Taller, orden_id: UUID, estado: E, rol: Rol, comentario: str | None = None
) -> None:
    u = _usuario(t.id, rol)
    async with sesion_rls(u) as s:
        await service.cambiar_estado(
            s, orden_id, CambioEstado(estado=estado, comentario=comentario), u
        )


# -----------------------------------------------------------------------------
# Alta
# -----------------------------------------------------------------------------


async def test_la_orden_nace_recibida_y_con_folio(escenario: Escenario) -> None:
    """El folio lo asigna un trigger tomando el correlativo del taller."""
    u = _usuario(escenario.a.id)
    async with sesion_rls(u) as s:
        orden = await service.crear(s, _alta(escenario.a), u)

    assert orden.estado is E.RECIBIDO
    assert orden.folio.startswith("ODA-")
    assert orden.taller_id == escenario.a.id


async def test_los_folios_son_correlativos_por_taller(escenario: Escenario) -> None:
    u = _usuario(escenario.a.id)
    folios = []
    for _ in range(3):
        async with sesion_rls(u) as s:
            folios.append((await service.crear(s, _alta(escenario.a), u)).folio)

    assert folios == sorted(folios), "deben salir en orden ascendente"
    assert len(set(folios)) == 3, "no puede haber folios repetidos"


async def test_no_se_abre_con_un_vehiculo_de_otro_cliente(escenario: Escenario) -> None:
    """El vehículo tiene que ser del cliente indicado. Lo cierra mch_ordenes_guard."""
    u = _usuario(escenario.a.id)

    async with sesion_rls(u) as s:
        otro = await srv_clientes.crear(s, ClienteCrear(nombre="Ajeno"), u)
        with pytest.raises(ErrorValidacion):
            await service.crear(s, _alta(escenario.a, cliente_id=otro.id), u)


async def test_no_se_abre_con_un_cliente_de_otro_taller(escenario: Escenario) -> None:
    u = _usuario(escenario.a.id)

    async with sesion_rls(u) as s:
        with pytest.raises(ErrorValidacion):
            await service.crear(s, _alta(escenario.a, cliente_id=escenario.b.cliente_id), u)


async def test_no_se_asigna_un_tecnico_inexistente(escenario: Escenario) -> None:
    """Sin esta comprobación saldría un error de llave foránea ilegible."""
    u = _usuario(escenario.a.id)

    async with sesion_rls(u) as s:
        with pytest.raises(ErrorValidacion, match="técnico"):
            await service.crear(s, _alta(escenario.a, tecnico_id=uuid4()), u)


# -----------------------------------------------------------------------------
# El flujo, con los roles reales
# -----------------------------------------------------------------------------


async def test_camino_feliz_completo(escenario: Escenario) -> None:
    """Recorre el flujo entero con el rol que corresponde a cada paso.

    Si la máquina de estados de Python y la de Postgres se separan, esto falla.
    """
    t = escenario.a
    orden_id = await _crear(t)

    asesor, tecnico = Rol.ASESOR_SERVICIO, Rol.TECNICO
    for estado, rol in [
        (E.EN_DIAGNOSTICO, asesor),
        (E.PRESUPUESTO_PENDIENTE, tecnico),
        (E.APROBADO, asesor),
        (E.EN_REPARACION, tecnico),
        (E.CONTROL_CALIDAD, tecnico),
        (E.LISTO_PARA_ENTREGA, asesor),
        (E.ENTREGADO, asesor),
    ]:
        await _mover(t, orden_id, estado, rol)

    async with sesion_rls(_usuario(t.id)) as s:
        orden = await service.obtener(s, orden_id)

    assert orden.estado is E.ENTREGADO
    assert orden.fecha_entrega is not None, "entregar debe sellar la fecha"


async def test_transicion_invalida_se_rechaza(escenario: Escenario) -> None:
    orden_id = await _crear(escenario.a)
    u = _usuario(escenario.a.id, Rol.ADMIN_TALLER)

    async with sesion_rls(u) as s:
        with pytest.raises(ErrorValidacion):
            await service.cambiar_estado(s, orden_id, CambioEstado(estado=E.ENTREGADO), u)


async def test_el_rol_equivocado_no_mueve_la_orden(escenario: Escenario) -> None:
    orden_id = await _crear(escenario.a)
    tecnico = _usuario(escenario.a.id, Rol.TECNICO)

    async with sesion_rls(tecnico) as s:
        with pytest.raises(ErrorPermiso):
            await service.cambiar_estado(
                s, orden_id, CambioEstado(estado=E.EN_DIAGNOSTICO), tecnico
            )


async def test_cancelar_guarda_el_motivo(escenario: Escenario) -> None:
    orden_id = await _crear(escenario.a)
    await _mover(
        escenario.a,
        orden_id,
        E.CANCELADO,
        Rol.ASESOR_SERVICIO,
        "El cliente se fue al concesionario",
    )

    async with sesion_rls(_usuario(escenario.a.id)) as s:
        orden = await service.obtener(s, orden_id)

    assert orden.estado is E.CANCELADO
    assert orden.motivo_cancelacion == "El cliente se fue al concesionario"


async def test_una_orden_entregada_ya_no_se_mueve(escenario: Escenario) -> None:
    t = escenario.a
    orden_id = await _crear(t)
    asesor, tecnico = Rol.ASESOR_SERVICIO, Rol.TECNICO
    for estado, rol in [
        (E.EN_DIAGNOSTICO, asesor),
        (E.PRESUPUESTO_PENDIENTE, tecnico),
        (E.APROBADO, asesor),
        (E.EN_REPARACION, tecnico),
        (E.CONTROL_CALIDAD, tecnico),
        (E.LISTO_PARA_ENTREGA, asesor),
        (E.ENTREGADO, asesor),
    ]:
        await _mover(t, orden_id, estado, rol)

    admin = _usuario(t.id, Rol.ADMIN_TALLER)
    async with sesion_rls(admin) as s:
        with pytest.raises(ErrorValidacion, match="ya no admite"):
            await service.cambiar_estado(s, orden_id, CambioEstado(estado=E.EN_REPARACION), admin)


# -----------------------------------------------------------------------------
# Bitácora
# -----------------------------------------------------------------------------


async def test_la_bitacora_registra_cada_paso(escenario: Escenario) -> None:
    t = escenario.a
    orden_id = await _crear(t)
    await _mover(t, orden_id, E.EN_DIAGNOSTICO, Rol.ASESOR_SERVICIO, "Entra a revisión")

    async with sesion_rls(_usuario(t.id)) as s:
        eventos = await service.historial(s, orden_id)

    assert len(eventos) == 2, "el alta también deja evento"
    assert eventos[0].estado_anterior is None
    assert eventos[0].estado_nuevo is E.RECIBIDO
    assert eventos[1].estado_anterior is E.RECIBIDO
    assert eventos[1].estado_nuevo is E.EN_DIAGNOSTICO


async def test_el_comentario_llega_a_la_bitacora(escenario: Escenario) -> None:
    """Viaja al trigger por un ajuste local de transacción (migración 000400).

    La aplicación no puede escribir en `orden_eventos`: es append-only.
    """
    t = escenario.a
    orden_id = await _crear(t)
    await _mover(
        t, orden_id, E.EN_DIAGNOSTICO, Rol.ASESOR_SERVICIO, "Cliente reporta ruido en frío"
    )

    async with sesion_rls(_usuario(t.id)) as s:
        eventos = await service.historial(s, orden_id)

    assert eventos[-1].comentario == "Cliente reporta ruido en frío"


async def test_el_comentario_no_se_filtra_al_siguiente_evento(escenario: Escenario) -> None:
    """El ajuste es local a la transacción, así que muere con ella."""
    t = escenario.a
    orden_id = await _crear(t)
    await _mover(t, orden_id, E.EN_DIAGNOSTICO, Rol.ASESOR_SERVICIO, "Con comentario")
    await _mover(t, orden_id, E.PRESUPUESTO_PENDIENTE, Rol.TECNICO)

    async with sesion_rls(_usuario(t.id)) as s:
        eventos = await service.historial(s, orden_id)

    assert eventos[-1].comentario is None


# -----------------------------------------------------------------------------
# Consulta
# -----------------------------------------------------------------------------


async def test_el_listado_esconde_las_cerradas(escenario: Escenario) -> None:
    t = escenario.a
    abierta = await _crear(t)
    cerrada = await _crear(t)
    await _mover(t, cerrada, E.CANCELADO, Rol.ASESOR_SERVICIO, "Duplicada")

    async with sesion_rls(_usuario(t.id)) as s:
        items, total = await service.listar(s, pagina=PAGINA)
        _, con_cerradas = await service.listar(s, incluir_cerradas=True, pagina=PAGINA)

    assert total == 1
    assert items[0].id == abierta
    assert con_cerradas == 2


async def test_filtrar_por_estado(escenario: Escenario) -> None:
    t = escenario.a
    orden_id = await _crear(t)
    await _crear(t)
    await _mover(t, orden_id, E.EN_DIAGNOSTICO, Rol.ASESOR_SERVICIO)

    async with sesion_rls(_usuario(t.id)) as s:
        _, en_diagnostico = await service.listar(s, estados=[E.EN_DIAGNOSTICO], pagina=PAGINA)

    assert en_diagnostico == 1


async def test_busqueda_por_folio_placa_y_cliente(escenario: Escenario) -> None:
    t = escenario.a
    async with sesion_rls(_usuario(t.id)) as s:
        folio = (await service.crear(s, _alta(t), _usuario(t.id))).folio

    sufijo = folio.split("-")[1].lstrip("0") or "0"
    for termino in (folio, "123", "Dueño"):
        async with sesion_rls(_usuario(t.id)) as s:
            _, total = await service.listar(s, busqueda=termino, pagina=PAGINA)
        assert total >= 1, f"la búsqueda por {termino!r} no encontró nada"
    assert sufijo  # el folio lleva número


async def test_tablero_cuenta_por_estado(escenario: Escenario) -> None:
    t = escenario.a
    o1 = await _crear(t)
    await _crear(t)
    await _mover(t, o1, E.EN_DIAGNOSTICO, Rol.ASESOR_SERVICIO)

    async with sesion_rls(_usuario(t.id)) as s:
        conteo = await service.resumen_tablero(s)

    assert conteo[E.RECIBIDO] == 1
    assert conteo[E.EN_DIAGNOSTICO] == 1
    assert conteo[E.ENTREGADO] == 0


# -----------------------------------------------------------------------------
# Aislamiento
# -----------------------------------------------------------------------------


async def test_no_ve_ordenes_de_otro_taller(escenario: Escenario) -> None:
    ajena = await _crear(escenario.b)

    async with sesion_rls(_usuario(escenario.a.id)) as s:
        _, total = await service.listar(s, incluir_cerradas=True, pagina=PAGINA)
    assert total == 0

    async with sesion_rls(_usuario(escenario.a.id)) as s:
        with pytest.raises(ErrorNoEncontrado):
            await service.obtener(s, ajena)


async def test_no_puede_mover_una_orden_ajena(escenario: Escenario) -> None:
    ajena = await _crear(escenario.b)
    u = _usuario(escenario.a.id, Rol.ADMIN_TALLER)

    async with sesion_rls(u) as s:
        with pytest.raises(ErrorNoEncontrado):
            await service.cambiar_estado(s, ajena, CambioEstado(estado=E.EN_DIAGNOSTICO), u)


# -----------------------------------------------------------------------------
# Edición
# -----------------------------------------------------------------------------


async def test_patch_parcial_no_toca_el_estado(escenario: Escenario) -> None:
    t = escenario.a
    orden_id = await _crear(t)
    await _mover(t, orden_id, E.EN_DIAGNOSTICO, Rol.ASESOR_SERVICIO)

    async with sesion_rls(_usuario(t.id)) as s:
        orden = await service.actualizar(
            s, orden_id, OrdenEditar(notas_internas="Requiere grúa para salir")
        )

    assert orden.estado is E.EN_DIAGNOSTICO
    assert orden.notas_internas == "Requiere grúa para salir"
