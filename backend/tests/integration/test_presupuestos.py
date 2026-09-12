"""Presupuestos: versionado, congelado y aprobación del cliente por enlace.

Lo que estas pruebas defienden es que el documento que vio el cliente no se
pueda reescribir después, y que aprobar desde el enlace —sin cuenta, sin rol—
mueva la orden de verdad.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.database import sesion_rls, sesion_servicio
from app.core.exceptions import ErrorConflicto, ErrorNoEncontrado, ErrorValidacion
from app.core.roles import Rol
from app.core.security import UsuarioAutenticado
from app.modules.clientes import service as srv_clientes
from app.modules.clientes.schemas import ClienteCrear
from app.modules.diagnosticos import service as srv_diag
from app.modules.diagnosticos.schemas import ManoObraCrear
from app.modules.ordenes import service as srv_ordenes
from app.modules.ordenes.estados import EstadoOrden as E
from app.modules.ordenes.schemas import CambioEstado, OrdenCrear
from app.modules.presupuestos import service
from app.modules.presupuestos.models import EstadoPresupuesto
from app.modules.presupuestos.schemas import (
    PresupuestoEditar,
    PresupuestoEmitir,
    RespuestaCliente,
)
from app.modules.repuestos import service as srv_rep
from app.modules.repuestos.schemas import ItemCrear
from app.modules.vehiculos import service as srv_vehiculos
from app.modules.vehiculos.schemas import VehiculoCrear

pytestmark = pytest.mark.integration

TARIFA = Decimal("20.00")
IVA = Decimal("16.00")


def _usuario(taller_id: UUID, rol: Rol = Rol.ASESOR_SERVICIO) -> UsuarioAutenticado:
    return UsuarioAutenticado(id=uuid4(), taller_id=taller_id, rol=rol)


@dataclass
class Escenario:
    taller: UUID
    orden: UUID


@pytest_asyncio.fixture
async def escenario() -> AsyncIterator[Escenario]:
    sfx = uuid4().hex[:8]
    async with sesion_servicio() as s:
        taller = (
            await s.execute(
                text("""
                    insert into public.talleres
                           (nombre, slug, prefijo_orden, tarifa_hora_default,
                            impuesto_pct, telefono)
                    values ('Pr ' || :sfx, 'pr-' || :sfx, 'PRE', :tar, :iva, '+58 212 555 0100')
                    returning id
                """),
                {"sfx": sfx, "tar": TARIFA, "iva": IVA},
            )
        ).scalar_one()

    u = _usuario(taller)
    async with sesion_rls(u) as s:
        cliente = await srv_clientes.crear(s, ClienteCrear(nombre="Andrés Villamizar"), u)
        vehiculo = await srv_vehiculos.crear(
            s,
            VehiculoCrear(
                cliente_id=cliente.id, placa="AB123CD", marca="Toyota", modelo="Corolla", anio=2018
            ),
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
        # 2 h × 20 = 40 de mano de obra, 38 de repuestos → 78 antes de impuesto.
        await srv_diag.crear_mano_obra(
            s, orden.id, ManoObraCrear(descripcion="Cambio de pastillas", horas=Decimal("2")), u
        )
        await srv_rep.agregar_item(
            s,
            orden.id,
            ItemCrear(
                descripcion="Juego de pastillas",
                cantidad=Decimal("1"),
                precio_unitario=Decimal("38"),
            ),
            u,
        )

    yield Escenario(taller=taller, orden=orden.id)

    async with sesion_servicio() as s:
        await s.execute(text("delete from public.talleres where id = :t"), {"t": taller})


async def _emitir(e: Escenario, **extra: object):
    u = _usuario(e.taller)
    async with sesion_rls(u) as s:
        return await service.emitir(s, e.orden, PresupuestoEmitir(**extra), u)  # type: ignore[arg-type]


async def _enviar(e: Escenario, presupuesto_id: UUID):
    u = _usuario(e.taller)
    async with sesion_rls(u) as s:
        return await service.enviar(s, presupuesto_id)


# -----------------------------------------------------------------------------
# Emitir
# -----------------------------------------------------------------------------


async def test_emitir_copia_las_lineas_de_la_orden(escenario: Escenario) -> None:
    p = await _emitir(escenario)

    assert p.version == 1
    assert p.estado is EstadoPresupuesto.BORRADOR
    assert len(p.items) == 2
    assert p.subtotal_mano_obra == Decimal("40.00")
    assert p.subtotal_repuestos == Decimal("38.00")


async def test_el_impuesto_sale_del_taller_y_el_total_lo_calcula_postgres(
    escenario: Escenario,
) -> None:
    p = await _emitir(escenario)

    assert p.impuesto_pct == IVA
    assert p.impuesto_monto == Decimal("12.48"), "78.00 × 16%"
    assert p.total == Decimal("90.48")


async def test_un_impuesto_cero_explicito_se_respeta(escenario: Escenario) -> None:
    """Exento no es lo mismo que "no lo indicaron"."""
    p = await _emitir(escenario, impuesto_pct=Decimal("0"))

    assert p.impuesto_pct == Decimal("0.00")
    assert p.total == Decimal("78.00")


async def test_el_descuento_baja_la_base_imponible(escenario: Escenario) -> None:
    p = await _emitir(escenario, descuento=Decimal("8"))

    assert p.impuesto_monto == Decimal("11.20"), "70.00 × 16%"
    assert p.total == Decimal("81.20")


async def test_no_se_cotiza_una_orden_sin_nada_cargado(escenario: Escenario) -> None:
    """Un presupuesto en blanco no es un documento, es un error de captura."""
    u = _usuario(escenario.taller)
    async with sesion_rls(u) as s:
        cliente = await srv_clientes.crear(s, ClienteCrear(nombre="Neida Colmenares"), u)
        vehiculo = await srv_vehiculos.crear(
            s,
            VehiculoCrear(cliente_id=cliente.id, placa="ZZ999ZZ", marca="Kia", modelo="Rio"),
            u,
        )
        vacia = await srv_ordenes.crear(
            s,
            OrdenCrear(
                cliente_id=cliente.id,
                vehiculo_id=vehiculo.id,
                motivo_ingreso="Revisión general",
            ),
            u,
        )
        vacia_id = vacia.id

    async with sesion_rls(u) as s:
        with pytest.raises(ErrorValidacion, match="nada que cotizar"):
            await service.emitir(s, vacia_id, PresupuestoEmitir(), u)


async def test_las_versiones_son_correlativas(escenario: Escenario) -> None:
    primera = await _emitir(escenario)
    segunda = await _emitir(escenario)

    assert [primera.version, segunda.version] == [1, 2]


# -----------------------------------------------------------------------------
# Congelado
# -----------------------------------------------------------------------------


async def test_el_borrador_todavia_se_ajusta(escenario: Escenario) -> None:
    p = await _emitir(escenario)

    u = _usuario(escenario.taller)
    async with sesion_rls(u) as s:
        editado = await service.actualizar(s, p.id, PresupuestoEditar(descuento=Decimal("10")))

    assert editado.descuento == Decimal("10.00")


async def test_enviado_ya_no_se_toca(escenario: Escenario) -> None:
    p = await _enviar(escenario, (await _emitir(escenario)).id)
    assert p.estado is EstadoPresupuesto.ENVIADO

    u = _usuario(escenario.taller)
    async with sesion_rls(u) as s:
        with pytest.raises(ErrorConflicto, match="versión nueva"):
            await service.actualizar(s, p.id, PresupuestoEditar(descuento=Decimal("50")))


async def test_cargar_mas_trabajo_no_altera_lo_ya_enviado(escenario: Escenario) -> None:
    """Es la razón de ser de las líneas copiadas."""
    p = await _enviar(escenario, (await _emitir(escenario)).id)
    total_original = p.total

    u = _usuario(escenario.taller)
    async with sesion_rls(u) as s:
        await srv_diag.crear_mano_obra(
            s, escenario.orden, ManoObraCrear(descripcion="Trabajo extra", horas=Decimal("3")), u
        )

    async with sesion_rls(u) as s:
        sigue = await service.obtener(s, p.id)

    assert sigue.total == total_original
    assert len(sigue.items) == 2


async def test_enviar_dos_veces_da_conflicto(escenario: Escenario) -> None:
    p = await _enviar(escenario, (await _emitir(escenario)).id)

    u = _usuario(escenario.taller)
    async with sesion_rls(u) as s:
        with pytest.raises(ErrorConflicto):
            await service.enviar(s, p.id)


# -----------------------------------------------------------------------------
# El cliente responde desde el enlace, sin cuenta
# -----------------------------------------------------------------------------


async def test_el_enlace_no_funciona_mientras_es_borrador(escenario: Escenario) -> None:
    """Un borrador no debería circular: todavía puede cambiar."""
    p = await _emitir(escenario)

    with pytest.raises(ErrorNoEncontrado):
        await service.obtener_por_token(p.token_publico)


async def test_el_cliente_ve_lo_justo(escenario: Escenario) -> None:
    p = await _enviar(escenario, (await _emitir(escenario)).id)

    doc, orden, vehiculo, taller = await service.obtener_por_token(p.token_publico)

    assert doc.total == p.total
    assert orden.folio.startswith("PRE-")
    assert vehiculo.placa == "AB123CD"
    assert taller.telefono == "+58 212 555 0100"


async def test_un_token_inventado_no_existe() -> None:
    with pytest.raises(ErrorNoEncontrado):
        await service.obtener_por_token("a" * 64)


async def test_aprobar_desde_el_enlace_mueve_la_orden(escenario: Escenario) -> None:
    """El camino público no tiene rol, y aun así la transición es válida.

    Es el caso para el que `mch_ordenes_guard` solo comprueba el rol cuando hay
    uno en los claims.
    """
    p = await _enviar(escenario, (await _emitir(escenario)).id)

    u = _usuario(escenario.taller)
    async with sesion_rls(u) as s:
        await srv_ordenes.cambiar_estado(
            s, escenario.orden, CambioEstado(estado=E.EN_DIAGNOSTICO), u
        )
    async with sesion_rls(_usuario(escenario.taller, Rol.TECNICO)) as s:
        await srv_ordenes.cambiar_estado(
            s,
            escenario.orden,
            CambioEstado(estado=E.PRESUPUESTO_PENDIENTE),
            _usuario(escenario.taller, Rol.TECNICO),
        )

    await service.responder_por_token(
        p.token_publico, RespuestaCliente(aprobado=True, comentario="Conforme, procedan")
    )

    async with sesion_rls(u) as s:
        orden = await srv_ordenes.obtener(s, escenario.orden)
        actualizado = await service.obtener(s, p.id)

    assert orden.estado is E.APROBADO
    assert actualizado.estado is EstadoPresupuesto.APROBADO
    assert actualizado.comentario_cliente == "Conforme, procedan"


async def test_la_aprobacion_queda_en_la_bitacora(escenario: Escenario) -> None:
    p = await _enviar(escenario, (await _emitir(escenario)).id)
    u = _usuario(escenario.taller)

    async with sesion_rls(u) as s:
        await srv_ordenes.cambiar_estado(
            s, escenario.orden, CambioEstado(estado=E.EN_DIAGNOSTICO), u
        )
    tec = _usuario(escenario.taller, Rol.TECNICO)
    async with sesion_rls(tec) as s:
        await srv_ordenes.cambiar_estado(
            s, escenario.orden, CambioEstado(estado=E.PRESUPUESTO_PENDIENTE), tec
        )

    await service.responder_por_token(p.token_publico, RespuestaCliente(aprobado=True))

    async with sesion_rls(u) as s:
        eventos = await srv_ordenes.historial(s, escenario.orden)

    ultimo = eventos[-1]
    assert ultimo.estado_nuevo is E.APROBADO
    assert "aprobado por el cliente" in (ultimo.comentario or "")
    assert ultimo.usuario_id is None, "lo aprobó el cliente, no alguien del taller"


async def test_rechazar_no_mueve_la_orden(escenario: Escenario) -> None:
    p = await _enviar(escenario, (await _emitir(escenario)).id)

    await service.responder_por_token(
        p.token_publico, RespuestaCliente(aprobado=False, comentario="Muy caro")
    )

    u = _usuario(escenario.taller)
    async with sesion_rls(u) as s:
        orden = await srv_ordenes.obtener(s, escenario.orden)
        doc = await service.obtener(s, p.id)

    assert orden.estado is E.RECIBIDO
    assert doc.estado is EstadoPresupuesto.RECHAZADO


async def test_no_se_responde_dos_veces(escenario: Escenario) -> None:
    p = await _enviar(escenario, (await _emitir(escenario)).id)
    await service.responder_por_token(p.token_publico, RespuestaCliente(aprobado=True))

    with pytest.raises(ErrorConflicto, match="ya está"):
        await service.responder_por_token(p.token_publico, RespuestaCliente(aprobado=False))


async def test_un_presupuesto_vencido_no_se_aprueba(escenario: Escenario) -> None:
    p = await _enviar(escenario, (await _emitir(escenario)).id)

    async with sesion_servicio() as s:
        await s.execute(
            text("update public.presupuestos set valido_hasta = :ayer where id = :id"),
            {"ayer": date.today() - timedelta(days=1), "id": p.id},
        )

    with pytest.raises(ErrorConflicto, match="venció"):
        await service.responder_por_token(p.token_publico, RespuestaCliente(aprobado=True))


# -----------------------------------------------------------------------------
# Aislamiento
# -----------------------------------------------------------------------------


async def test_no_ve_presupuestos_de_otro_taller(escenario: Escenario) -> None:
    p = await _emitir(escenario)

    ajeno = _usuario(uuid4())
    async with sesion_rls(ajeno) as s:
        with pytest.raises(ErrorNoEncontrado):
            await service.obtener(s, p.id)


async def test_el_asesor_anota_la_respuesta_por_telefono(escenario: Escenario) -> None:
    p = await _enviar(escenario, (await _emitir(escenario)).id)

    u = _usuario(escenario.taller)
    async with sesion_rls(u) as s:
        doc = await service.responder(
            s, p.id, RespuestaCliente(aprobado=True, comentario="Aprobó por teléfono")
        )

    assert doc.estado is EstadoPresupuesto.APROBADO
    assert doc.respondido_en is not None


async def test_descuento_mayor_que_el_importe_se_rechaza(escenario: Escenario) -> None:
    with pytest.raises(ErrorValidacion, match="descuento"):
        await _emitir(escenario, descuento=Decimal("500"))
