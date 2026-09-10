"""Servicio de vehículos contra la base real, con RLS activo."""

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
from app.modules.vehiculos import service
from app.modules.vehiculos.schemas import VehiculoCrear, VehiculoEditar
from app.shared.paginacion import ParametrosPagina

pytestmark = pytest.mark.integration

PAGINA = ParametrosPagina(limite=50, desplazamiento=0)


def _usuario(taller_id: UUID, rol: Rol = Rol.ASESOR_SERVICIO) -> UsuarioAutenticado:
    return UsuarioAutenticado(id=uuid4(), taller_id=taller_id, rol=rol)


@dataclass
class Escenario:
    """Dos talleres, cada uno con un cliente propio."""

    taller_a: UUID
    taller_b: UUID
    cliente_a: UUID
    cliente_b: UUID


@pytest_asyncio.fixture
async def escenario() -> AsyncIterator[Escenario]:
    sfx = uuid4().hex[:8]
    async with sesion_servicio() as s:
        filas = await s.execute(
            text("""
                insert into public.talleres (nombre, slug, prefijo_orden)
                values ('Veh A ' || :sfx, 'veh-a-' || :sfx, 'VHA'),
                       ('Veh B ' || :sfx, 'veh-b-' || :sfx, 'VHB')
                returning id
            """),
            {"sfx": sfx},
        )
        a, b = (r[0] for r in filas.fetchall())

    async with sesion_rls(_usuario(a)) as s:
        cliente_a = (await srv_clientes.crear(s, ClienteCrear(nombre="Dueño A"), _usuario(a))).id
    async with sesion_rls(_usuario(b)) as s:
        cliente_b = (await srv_clientes.crear(s, ClienteCrear(nombre="Dueño B"), _usuario(b))).id

    yield Escenario(taller_a=a, taller_b=b, cliente_a=cliente_a, cliente_b=cliente_b)

    async with sesion_servicio() as s:
        await s.execute(text("delete from public.talleres where id = any(:ids)"), {"ids": [a, b]})


def _datos(cliente_id: UUID, **extra: object) -> VehiculoCrear:
    base = {"cliente_id": cliente_id, "placa": "AB123CD", "marca": "Toyota", "modelo": "Corolla"}
    return VehiculoCrear(**{**base, **extra})  # type: ignore[arg-type]


# -----------------------------------------------------------------------------
# Alta
# -----------------------------------------------------------------------------


async def test_crear_toma_el_taller_del_token(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        v = await service.crear(s, _datos(escenario.cliente_a, anio=2018), u)

    assert v.taller_id == escenario.taller_a
    assert v.placa == "AB123CD"
    assert v.activo is True


async def test_no_se_puede_colgar_de_un_cliente_de_otro_taller(escenario: Escenario) -> None:
    """La FK apunta a la fila, no al tenant. Lo cierra mch_vehiculos_guard."""
    u = _usuario(escenario.taller_a)

    async with sesion_rls(u) as s:
        with pytest.raises(ErrorValidacion):
            await service.crear(s, _datos(escenario.cliente_b), u)


async def test_placa_repetida_da_conflicto(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)

    async with sesion_rls(u) as s:
        await service.crear(s, _datos(escenario.cliente_a), u)

    async with sesion_rls(u) as s:
        with pytest.raises(ErrorConflicto) as excinfo:
            await service.crear(s, _datos(escenario.cliente_a, modelo="Yaris"), u)

    assert "placa" in str(excinfo.value).lower()


async def test_la_placa_choca_sin_importar_las_mayusculas(escenario: Escenario) -> None:
    """El índice es sobre upper(placa); la normalización del esquema lo respeta."""
    u = _usuario(escenario.taller_a)

    async with sesion_rls(u) as s:
        await service.crear(s, _datos(escenario.cliente_a, placa="AB123CD"), u)

    async with sesion_rls(u) as s:
        with pytest.raises(ErrorConflicto):
            await service.crear(s, _datos(escenario.cliente_a, placa="ab 123 cd"), u)


async def test_misma_placa_en_talleres_distintos_es_valida(escenario: Escenario) -> None:
    ua, ub = _usuario(escenario.taller_a), _usuario(escenario.taller_b)

    async with sesion_rls(ua) as s:
        await service.crear(s, _datos(escenario.cliente_a), ua)

    async with sesion_rls(ub) as s:
        v = await service.crear(s, _datos(escenario.cliente_b), ub)

    assert v.taller_id == escenario.taller_b


async def test_vin_repetido_da_conflicto(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    vin = "9BWZZZ377VT004251"

    async with sesion_rls(u) as s:
        await service.crear(s, _datos(escenario.cliente_a, vin=vin), u)

    async with sesion_rls(u) as s:
        with pytest.raises(ErrorConflicto) as excinfo:
            await service.crear(s, _datos(escenario.cliente_a, placa="XY456ZW", vin=vin), u)

    assert "vin" in str(excinfo.value).lower()


# -----------------------------------------------------------------------------
# Aislamiento entre talleres
# -----------------------------------------------------------------------------


async def test_no_ve_vehiculos_de_otro_taller(escenario: Escenario) -> None:
    ua, ub = _usuario(escenario.taller_a), _usuario(escenario.taller_b)

    async with sesion_rls(ub) as s:
        ajeno_id = (await service.crear(s, _datos(escenario.cliente_b), ub)).id

    async with sesion_rls(ua) as s:
        _, total = await service.listar(s, pagina=PAGINA)
    assert total == 0

    async with sesion_rls(ua) as s:
        with pytest.raises(ErrorNoEncontrado):
            await service.obtener(s, ajeno_id)


# -----------------------------------------------------------------------------
# Consulta
# -----------------------------------------------------------------------------


async def test_listar_incluye_el_nombre_del_propietario(escenario: Escenario) -> None:
    """Evita que la interfaz pida cada cliente por separado para pintar la tabla."""
    u = _usuario(escenario.taller_a)

    async with sesion_rls(u) as s:
        await service.crear(s, _datos(escenario.cliente_a), u)

    async with sesion_rls(u) as s:
        items, _ = await service.listar(s, pagina=PAGINA)

    assert items[0].cliente.nombre == "Dueño A"


async def test_filtrar_por_cliente(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)

    async with sesion_rls(u) as s:
        otro = (await srv_clientes.crear(s, ClienteCrear(nombre="Otro dueño"), u)).id
        await service.crear(s, _datos(escenario.cliente_a, placa="AB123CD"), u)
        await service.crear(s, _datos(otro, placa="XY456ZW"), u)

    async with sesion_rls(u) as s:
        _, total = await service.listar(s, cliente_id=escenario.cliente_a, pagina=PAGINA)

    assert total == 1


async def test_busqueda_por_trozo_de_placa(escenario: Escenario) -> None:
    """El motivo del índice de trigramas: buscar por el medio de la placa."""
    u = _usuario(escenario.taller_a)

    async with sesion_rls(u) as s:
        await service.crear(s, _datos(escenario.cliente_a, placa="AB123CD"), u)
        await service.crear(
            s, _datos(escenario.cliente_a, placa="XY456ZW", marca="Chevrolet", modelo="Aveo"), u
        )

    async with sesion_rls(u) as s:
        items, total = await service.listar(s, busqueda="123", pagina=PAGINA)

    assert total == 1
    assert items[0].placa == "AB123CD"


async def test_busqueda_por_marca(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)

    async with sesion_rls(u) as s:
        await service.crear(s, _datos(escenario.cliente_a), u)

    async with sesion_rls(u) as s:
        _, total = await service.listar(s, busqueda="toyo", pagina=PAGINA)

    assert total == 1


# -----------------------------------------------------------------------------
# Permisos por rol
# -----------------------------------------------------------------------------


async def test_tecnico_no_puede_dar_de_alta(escenario: Escenario) -> None:
    tecnico = _usuario(escenario.taller_a, Rol.TECNICO)

    async with sesion_rls(tecnico) as s:
        with pytest.raises(DBAPIError):
            await service.crear(s, _datos(escenario.cliente_a), tecnico)


async def test_tecnico_si_puede_registrar_kilometraje(escenario: Escenario) -> None:
    """Es lo que hace al recibir el vehículo, así que la política se lo permite."""
    u = _usuario(escenario.taller_a)

    async with sesion_rls(u) as s:
        vehiculo_id = (await service.crear(s, _datos(escenario.cliente_a), u)).id

    async with sesion_rls(_usuario(escenario.taller_a, Rol.TECNICO)) as s:
        v = await service.actualizar(s, vehiculo_id, VehiculoEditar(kilometraje_ultimo=87400))

    assert v.kilometraje_ultimo == 87400


# -----------------------------------------------------------------------------
# Edición y borrado
# -----------------------------------------------------------------------------


async def test_patch_parcial_no_borra_lo_demas(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)

    async with sesion_rls(u) as s:
        vehiculo_id = (
            await service.crear(s, _datos(escenario.cliente_a, anio=2018, color="Plata"), u)
        ).id

    async with sesion_rls(u) as s:
        v = await service.actualizar(s, vehiculo_id, VehiculoEditar(kilometraje_ultimo=90000))

    assert v.anio == 2018
    assert v.color == "Plata"


async def test_no_se_borra_un_vehiculo_con_ordenes(escenario: Escenario) -> None:
    """La FK desde ordenes_servicio es RESTRICT: borrarlo perdería el historial."""
    admin = _usuario(escenario.taller_a, Rol.ADMIN_TALLER)

    async with sesion_rls(admin) as s:
        vehiculo_id = (await service.crear(s, _datos(escenario.cliente_a), admin)).id
        await s.execute(
            text("""
                insert into public.ordenes_servicio
                       (taller_id, cliente_id, vehiculo_id, motivo_ingreso)
                values (:t, :c, :v, 'Ruido al frenar')
            """),
            {"t": escenario.taller_a, "c": escenario.cliente_a, "v": vehiculo_id},
        )

    async with sesion_rls(admin) as s:
        with pytest.raises(ErrorConflicto) as excinfo:
            await service.eliminar(s, vehiculo_id)

    assert "desactívalo" in str(excinfo.value).lower()


async def test_borrar_vehiculo_sin_historial(escenario: Escenario) -> None:
    admin = _usuario(escenario.taller_a, Rol.ADMIN_TALLER)

    async with sesion_rls(admin) as s:
        vehiculo_id = (await service.crear(s, _datos(escenario.cliente_a), admin)).id

    async with sesion_rls(admin) as s:
        await service.eliminar(s, vehiculo_id)

    async with sesion_rls(admin) as s:
        _, total = await service.listar(s, solo_activos=False, pagina=PAGINA)

    assert total == 0
