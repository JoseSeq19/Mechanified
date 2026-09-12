"""Catálogo de repuestos y piezas de una orden, contra la base real."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database import sesion_rls, sesion_servicio
from app.core.exceptions import ErrorConflicto, ErrorNoEncontrado, ErrorValidacion
from app.core.roles import Rol
from app.core.security import UsuarioAutenticado
from app.modules.clientes import service as srv_clientes
from app.modules.clientes.schemas import ClienteCrear
from app.modules.ordenes import service as srv_ordenes
from app.modules.ordenes.estados import EstadoOrden as E
from app.modules.ordenes.schemas import CambioEstado, OrdenCrear
from app.modules.repuestos import service
from app.modules.repuestos.models import EstadoItemRepuesto
from app.modules.repuestos.schemas import ItemCrear, ItemEditar, RepuestoCrear, RepuestoEditar
from app.modules.vehiculos import service as srv_vehiculos
from app.modules.vehiculos.schemas import VehiculoCrear
from app.shared.paginacion import ParametrosPagina

pytestmark = pytest.mark.integration

PAGINA = ParametrosPagina(limite=50, desplazamiento=0)


def _usuario(taller_id: UUID, rol: Rol = Rol.ENCARGADO_REPUESTOS) -> UsuarioAutenticado:
    return UsuarioAutenticado(id=uuid4(), taller_id=taller_id, rol=rol)


@dataclass
class Escenario:
    taller_a: UUID
    taller_b: UUID
    orden_a: UUID
    orden_b: UUID


async def _montar_orden(taller_id: UUID, placa: str) -> UUID:
    u = _usuario(taller_id, Rol.ASESOR_SERVICIO)
    async with sesion_rls(u) as s:
        cliente = await srv_clientes.crear(s, ClienteCrear(nombre="Dueño"), u)
        vehiculo = await srv_vehiculos.crear(
            s,
            VehiculoCrear(cliente_id=cliente.id, placa=placa, marca="Toyota", modelo="Corolla"),
            u,
        )
        orden = await srv_ordenes.crear(
            s,
            OrdenCrear(
                cliente_id=cliente.id,
                vehiculo_id=vehiculo.id,
                motivo_ingreso="Chillido metálico al frenar",
            ),
            u,
        )
        return orden.id


@pytest_asyncio.fixture
async def escenario() -> AsyncIterator[Escenario]:
    sfx = uuid4().hex[:8]
    async with sesion_servicio() as s:
        filas = await s.execute(
            text("""
                insert into public.talleres (nombre, slug, prefijo_orden)
                values ('Rp A ' || :sfx, 'rp-a-' || :sfx, 'RPA'),
                       ('Rp B ' || :sfx, 'rp-b-' || :sfx, 'RPB')
                returning id
            """),
            {"sfx": sfx},
        )
        ta, tb = (r[0] for r in filas.fetchall())

    yield Escenario(
        taller_a=ta,
        taller_b=tb,
        orden_a=await _montar_orden(ta, "AB123CD"),
        orden_b=await _montar_orden(tb, "XY456ZW"),
    )

    async with sesion_servicio() as s:
        await s.execute(text("delete from public.talleres where id = any(:ids)"), {"ids": [ta, tb]})


def _pieza(**extra: object) -> RepuestoCrear:
    base = {
        "sku": "FRE-PAS-001",
        "nombre": "Juego de pastillas de freno delanteras",
        "categoria": "Frenos",
        "costo": Decimal("22.00"),
        "precio_venta": Decimal("38.00"),
    }
    return RepuestoCrear(**{**base, **extra})  # type: ignore[arg-type]


# -----------------------------------------------------------------------------
# Catálogo
# -----------------------------------------------------------------------------


async def test_alta_en_el_catalogo(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        r = await service.crear_repuesto(s, _pieza(), u)

    assert r.sku == "FRE-PAS-001"
    assert r.precio_venta == Decimal("38.00")
    assert r.activo is True


async def test_el_sku_se_normaliza_a_mayusculas(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        r = await service.crear_repuesto(s, _pieza(sku="  fre-pas-001  "), u)

    assert r.sku == "FRE-PAS-001"


async def test_sku_repetido_da_conflicto(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        await service.crear_repuesto(s, _pieza(), u)

    async with sesion_rls(u) as s:
        with pytest.raises(ErrorConflicto, match="FRE-PAS-001"):
            await service.crear_repuesto(s, _pieza(nombre="Otra cosa"), u)


async def test_el_mismo_sku_vale_en_talleres_distintos(escenario: Escenario) -> None:
    async with sesion_rls(_usuario(escenario.taller_a)) as s:
        await service.crear_repuesto(s, _pieza(), _usuario(escenario.taller_a))

    ub = _usuario(escenario.taller_b)
    async with sesion_rls(ub) as s:
        r = await service.crear_repuesto(s, _pieza(), ub)

    assert r.taller_id == escenario.taller_b


async def test_busqueda_por_trozo_de_sku(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        await service.crear_repuesto(s, _pieza(), u)
        await service.crear_repuesto(
            s,
            _pieza(sku="MOT-ACE-010", nombre="Aceite sintético 5W-30", categoria="Lubricantes"),
            u,
        )

    async with sesion_rls(u) as s:
        items, total = await service.listar_catalogo(s, busqueda="PAS", pagina=PAGINA)

    assert total == 1
    assert items[0].sku == "FRE-PAS-001"


async def test_filtrar_lo_que_hay_que_reponer(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        await service.crear_repuesto(s, _pieza(stock=Decimal("2"), stock_minimo=Decimal("4")), u)
        await service.crear_repuesto(
            s,
            _pieza(
                sku="MOT-ACE-010", nombre="Aceite", stock=Decimal("20"), stock_minimo=Decimal("5")
            ),
            u,
        )

    async with sesion_rls(u) as s:
        items, total = await service.listar_catalogo(s, solo_bajo_minimo=True, pagina=PAGINA)

    assert total == 1
    assert items[0].bajo_minimo is True


async def test_el_tecnico_no_edita_el_catalogo(escenario: Escenario) -> None:
    """Lo rechaza RLS: el catálogo es de repuestos y administración."""
    tecnico = _usuario(escenario.taller_a, Rol.TECNICO)
    async with sesion_rls(tecnico) as s:
        with pytest.raises(DBAPIError):
            await service.crear_repuesto(s, _pieza(), tecnico)


async def test_no_ve_el_catalogo_de_otro_taller(escenario: Escenario) -> None:
    ub = _usuario(escenario.taller_b)
    async with sesion_rls(ub) as s:
        ajeno = await service.crear_repuesto(s, _pieza(), ub)
        ajeno_id = ajeno.id

    async with sesion_rls(_usuario(escenario.taller_a)) as s:
        with pytest.raises(ErrorNoEncontrado):
            await service.obtener_repuesto(s, ajeno_id)


# -----------------------------------------------------------------------------
# Piezas de una orden
# -----------------------------------------------------------------------------


async def test_cargar_del_catalogo_copia_nombre_y_precio(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        r = await service.crear_repuesto(s, _pieza(), u)
        item = await service.agregar_item(
            s, escenario.orden_a, ItemCrear(repuesto_id=r.id, cantidad=Decimal("2")), u
        )

    assert item.descripcion == "Juego de pastillas de freno delanteras"
    assert item.precio_unitario == Decimal("38.00")
    assert item.subtotal == Decimal("76.00")
    assert item.estado is EstadoItemRepuesto.SOLICITADO


async def test_pieza_fuera_de_catalogo(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        item = await service.agregar_item(
            s,
            escenario.orden_a,
            ItemCrear(
                descripcion="Manguera a la medida",
                cantidad=Decimal("1"),
                precio_unitario=Decimal("15.50"),
            ),
            u,
        )

    assert item.repuesto_id is None
    assert item.subtotal == Decimal("15.50")


def test_sin_catalogo_hacen_falta_descripcion_y_precio() -> None:
    """Se rechaza en el esquema, antes de tocar la base."""
    with pytest.raises(ValidationError, match="fuera de catálogo"):
        ItemCrear(cantidad=Decimal("1"))


async def test_el_precio_se_puede_ajustar_al_cargar(escenario: Escenario) -> None:
    """A veces se negocia el precio de una pieza concreta."""
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        r = await service.crear_repuesto(s, _pieza(), u)
        item = await service.agregar_item(
            s,
            escenario.orden_a,
            ItemCrear(repuesto_id=r.id, cantidad=Decimal("1"), precio_unitario=Decimal("30.00")),
            u,
        )

    assert item.precio_unitario == Decimal("30.00")


async def test_el_precio_queda_congelado(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        r = await service.crear_repuesto(s, _pieza(), u)
        repuesto_id = r.id
        item = await service.agregar_item(
            s, escenario.orden_a, ItemCrear(repuesto_id=repuesto_id, cantidad=Decimal("1")), u
        )
        item_id = item.id

    async with sesion_rls(u) as s:
        await service.actualizar_repuesto(
            s, repuesto_id, RepuestoEditar(precio_venta=Decimal("55.00"))
        )

    async with sesion_rls(u) as s:
        vieja = await service.obtener_item(s, item_id)

    assert vieja.precio_unitario == Decimal("38.00")


async def test_las_piezas_suman_al_total_de_la_orden(escenario: Escenario) -> None:
    """Lo hace el trigger mch_recalcular_totales_orden."""
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        r = await service.crear_repuesto(s, _pieza(), u)
        await service.agregar_item(
            s, escenario.orden_a, ItemCrear(repuesto_id=r.id, cantidad=Decimal("2")), u
        )

    async with sesion_rls(u) as s:
        orden = await srv_ordenes.obtener(s, escenario.orden_a)

    assert orden.total_repuestos == Decimal("76.00")
    assert orden.total == Decimal("76.00")


async def test_el_resumen_cuenta_las_pendientes(escenario: Escenario) -> None:
    """Las que aún no llegaron son las que frenan la reparación."""
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        r = await service.crear_repuesto(s, _pieza(), u)
        pendiente = await service.agregar_item(
            s, escenario.orden_a, ItemCrear(repuesto_id=r.id, cantidad=Decimal("1")), u
        )
        llegada = await service.agregar_item(
            s,
            escenario.orden_a,
            ItemCrear(
                descripcion="Filtro de aceite",
                cantidad=Decimal("1"),
                precio_unitario=Decimal("9.50"),
                estado=EstadoItemRepuesto.INSTALADO,
            ),
            u,
        )
        assert pendiente.id != llegada.id

    async with sesion_rls(u) as s:
        total, pendientes = await service.resumen_items(s, escenario.orden_a)

    assert total == Decimal("47.50")
    assert pendientes == 1


async def test_cambiar_el_estado_de_una_pieza(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        r = await service.crear_repuesto(s, _pieza(), u)
        item_id = (
            await service.agregar_item(
                s, escenario.orden_a, ItemCrear(repuesto_id=r.id, cantidad=Decimal("1")), u
            )
        ).id

    async with sesion_rls(u) as s:
        item = await service.actualizar_item(
            s, item_id, ItemEditar(estado=EstadoItemRepuesto.RECIBIDO)
        )

    assert item.estado is EstadoItemRepuesto.RECIBIDO


async def test_quitar_una_pieza_baja_el_total(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        r = await service.crear_repuesto(s, _pieza(), u)
        item_id = (
            await service.agregar_item(
                s, escenario.orden_a, ItemCrear(repuesto_id=r.id, cantidad=Decimal("2")), u
            )
        ).id

    async with sesion_rls(u) as s:
        await service.eliminar_item(s, item_id)

    async with sesion_rls(u) as s:
        orden = await srv_ordenes.obtener(s, escenario.orden_a)

    assert orden.total_repuestos == Decimal("0.00")


async def test_borrar_del_catalogo_no_rompe_la_orden(escenario: Escenario) -> None:
    """La FK es `on delete set null`: la línea conserva su copia."""
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        r = await service.crear_repuesto(s, _pieza(), u)
        repuesto_id = r.id
        item_id = (
            await service.agregar_item(
                s, escenario.orden_a, ItemCrear(repuesto_id=repuesto_id, cantidad=Decimal("1")), u
            )
        ).id

    async with sesion_rls(u) as s:
        await service.eliminar_repuesto(s, repuesto_id)

    async with sesion_rls(u) as s:
        item = await service.obtener_item(s, item_id)

    assert item.repuesto_id is None
    assert item.descripcion == "Juego de pastillas de freno delanteras"
    assert item.precio_unitario == Decimal("38.00")


async def test_no_se_carga_una_pieza_de_otro_catalogo(escenario: Escenario) -> None:
    ub = _usuario(escenario.taller_b)
    async with sesion_rls(ub) as s:
        ajeno = await service.crear_repuesto(s, _pieza(), ub)
        ajeno_id = ajeno.id

    ua = _usuario(escenario.taller_a)
    async with sesion_rls(ua) as s:
        with pytest.raises(ErrorValidacion, match="catálogo"):
            await service.agregar_item(
                s, escenario.orden_a, ItemCrear(repuesto_id=ajeno_id, cantidad=Decimal("1")), ua
            )


async def test_no_se_cargan_piezas_a_una_orden_cerrada(escenario: Escenario) -> None:
    asesor = _usuario(escenario.taller_a, Rol.ASESOR_SERVICIO)
    async with sesion_rls(asesor) as s:
        await srv_ordenes.cambiar_estado(
            s, escenario.orden_a, CambioEstado(estado=E.CANCELADO, comentario="Prueba"), asesor
        )

    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        with pytest.raises(ErrorValidacion, match="ya no admite"):
            await service.agregar_item(
                s,
                escenario.orden_a,
                ItemCrear(
                    descripcion="Tarde", cantidad=Decimal("1"), precio_unitario=Decimal("10")
                ),
                u,
            )
