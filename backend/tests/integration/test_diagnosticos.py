"""Diagnóstico y mano de obra contra la base real.

Lo que más importa aquí es que el dinero cuadre: el subtotal lo calcula
Postgres, y los totales de la orden los mantiene un trigger. Nada de eso se
puede comprobar sin una base de verdad.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database import sesion_rls, sesion_servicio
from app.core.exceptions import ErrorNoEncontrado, ErrorValidacion
from app.core.roles import Rol
from app.core.security import UsuarioAutenticado
from app.modules.clientes import service as srv_clientes
from app.modules.clientes.schemas import ClienteCrear
from app.modules.diagnosticos import service
from app.modules.diagnosticos.models import SeveridadHallazgo
from app.modules.diagnosticos.schemas import (
    DiagnosticoCrear,
    DiagnosticoEditar,
    HallazgoCrear,
    HallazgoEditar,
    ManoObraCrear,
    ManoObraEditar,
)
from app.modules.ordenes import service as srv_ordenes
from app.modules.ordenes.estados import EstadoOrden as E
from app.modules.ordenes.schemas import CambioEstado, OrdenCrear
from app.modules.vehiculos import service as srv_vehiculos
from app.modules.vehiculos.schemas import VehiculoCrear

pytestmark = pytest.mark.integration

TARIFA = Decimal("18.00")


def _usuario(taller_id: UUID, rol: Rol = Rol.TECNICO) -> UsuarioAutenticado:
    return UsuarioAutenticado(id=uuid4(), taller_id=taller_id, rol=rol)


@dataclass
class Escenario:
    taller_a: UUID
    taller_b: UUID
    orden_a: UUID
    orden_b: UUID


async def _montar(taller_id: UUID, placa: str) -> UUID:
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
                insert into public.talleres (nombre, slug, prefijo_orden, tarifa_hora_default)
                values ('Dg A ' || :sfx, 'dg-a-' || :sfx, 'DGA', :tar),
                       ('Dg B ' || :sfx, 'dg-b-' || :sfx, 'DGB', :tar)
                returning id
            """),
            {"sfx": sfx, "tar": TARIFA},
        )
        ta, tb = (r[0] for r in filas.fetchall())

    yield Escenario(
        taller_a=ta,
        taller_b=tb,
        orden_a=await _montar(ta, "AB123CD"),
        orden_b=await _montar(tb, "XY456ZW"),
    )

    async with sesion_servicio() as s:
        await s.execute(text("delete from public.talleres where id = any(:ids)"), {"ids": [ta, tb]})


def _diag(**extra: object) -> DiagnosticoCrear:
    base = {"resumen": "Pastillas al límite y disco con alabeo", "horas_estimadas": Decimal("2.5")}
    return DiagnosticoCrear(**{**base, **extra})  # type: ignore[arg-type]


# -----------------------------------------------------------------------------
# Diagnóstico
# -----------------------------------------------------------------------------


async def test_se_crea_con_sus_hallazgos_de_una_vez(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        d = await service.crear_diagnostico(
            s,
            escenario.orden_a,
            _diag(
                hallazgos=[
                    HallazgoCrear(
                        sistema="Frenos",
                        descripcion="Pastillas delanteras por debajo del mínimo",
                        severidad=SeveridadHallazgo.CRITICA,
                        requiere_repuesto=True,
                    ),
                    HallazgoCrear(sistema="Frenos", descripcion="Disco con alabeo leve"),
                ]
            ),
            u,
        )

    assert len(d.hallazgos) == 2
    assert d.hallazgos[0].severidad is SeveridadHallazgo.CRITICA
    assert [h.orden_visual for h in d.hallazgos] == [1, 2]


async def test_una_orden_admite_varios_diagnosticos(escenario: Escenario) -> None:
    """El trabajo adicional se registra aparte, sin tocar el original."""
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        await service.crear_diagnostico(s, escenario.orden_a, _diag(), u)
        await service.crear_diagnostico(
            s, escenario.orden_a, _diag(resumen="Aparece fuga de dirección"), u
        )

    async with sesion_rls(u) as s:
        lista = await service.listar_diagnosticos(s, escenario.orden_a)

    assert len(lista) == 2


async def test_el_tecnico_por_omision_es_quien_escribe(escenario: Escenario) -> None:
    """En pruebas el usuario sintético no tiene perfil, así que queda en NULL."""
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        d = await service.crear_diagnostico(s, escenario.orden_a, _diag(), u)

    assert d.tecnico_id is None


async def test_no_se_asigna_un_tecnico_de_otro_taller(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        with pytest.raises(ErrorValidacion, match="técnico"):
            await service.crear_diagnostico(s, escenario.orden_a, _diag(tecnico_id=uuid4()), u)


async def test_el_asesor_no_registra_diagnosticos(escenario: Escenario) -> None:
    """Lo rechaza RLS: la política de `diagnosticos` es de técnico y admin."""
    asesor = _usuario(escenario.taller_a, Rol.ASESOR_SERVICIO)
    async with sesion_rls(asesor) as s:
        with pytest.raises(DBAPIError):
            await service.crear_diagnostico(s, escenario.orden_a, _diag(), asesor)


# -----------------------------------------------------------------------------
# Hallazgos
# -----------------------------------------------------------------------------


async def test_agregar_y_editar_un_hallazgo(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        d = await service.crear_diagnostico(
            s,
            escenario.orden_a,
            _diag(hallazgos=[HallazgoCrear(sistema="Frenos", descripcion="Pastillas gastadas")]),
            u,
        )
        diag_id = d.id

    async with sesion_rls(u) as s:
        d = await service.agregar_hallazgo(
            s, diag_id, HallazgoCrear(sistema="Suspensión", descripcion="Amortiguador vencido")
        )
    assert [h.orden_visual for h in d.hallazgos] == [1, 2]

    segundo = d.hallazgos[1].id
    async with sesion_rls(u) as s:
        d = await service.actualizar_hallazgo(
            s, segundo, HallazgoEditar(severidad=SeveridadHallazgo.CRITICA)
        )

    assert d.hallazgos[1].severidad is SeveridadHallazgo.CRITICA


async def test_borrar_un_hallazgo(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        d = await service.crear_diagnostico(
            s,
            escenario.orden_a,
            _diag(hallazgos=[HallazgoCrear(sistema="Frenos", descripcion="Pastillas gastadas")]),
            u,
        )
        hallazgo_id, diag_id = d.hallazgos[0].id, d.id

    async with sesion_rls(u) as s:
        await service.eliminar_hallazgo(s, hallazgo_id)

    async with sesion_rls(u) as s:
        d = await service.obtener_diagnostico(s, diag_id)
    assert d.hallazgos == []


# -----------------------------------------------------------------------------
# Mano de obra y dinero
# -----------------------------------------------------------------------------


async def test_la_tarifa_sale_del_taller_y_el_subtotal_lo_calcula_postgres(
    escenario: Escenario,
) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        linea = await service.crear_mano_obra(
            s,
            escenario.orden_a,
            ManoObraCrear(descripcion="Sustitución de pastillas", horas=Decimal("2.5")),
            u,
        )

    assert linea.tarifa_hora == TARIFA
    assert linea.subtotal == Decimal("45.00"), "2.5 h × 18.00"


async def test_cargar_trabajo_actualiza_el_total_de_la_orden(escenario: Escenario) -> None:
    """Lo hace el trigger mch_recalcular_totales_orden, no la aplicación."""
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        await service.crear_mano_obra(
            s, escenario.orden_a, ManoObraCrear(descripcion="Frenos", horas=Decimal("2")), u
        )
        await service.crear_mano_obra(
            s, escenario.orden_a, ManoObraCrear(descripcion="Alineación", horas=Decimal("1.5")), u
        )

    async with sesion_rls(u) as s:
        orden = await srv_ordenes.obtener(s, escenario.orden_a)

    assert orden.total_mano_obra == Decimal("63.00"), "3.5 h × 18.00"
    assert orden.total == Decimal("63.00")


async def test_quitar_una_linea_baja_el_total(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        linea = await service.crear_mano_obra(
            s, escenario.orden_a, ManoObraCrear(descripcion="Frenos", horas=Decimal("2")), u
        )
        linea_id = linea.id

    async with sesion_rls(u) as s:
        await service.eliminar_mano_obra(s, linea_id)

    async with sesion_rls(u) as s:
        orden = await srv_ordenes.obtener(s, escenario.orden_a)

    assert orden.total_mano_obra == Decimal("0.00")


async def test_la_tarifa_queda_congelada_en_la_linea(escenario: Escenario) -> None:
    """Subir la tarifa del taller no puede alterar lo ya cotizado."""
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        linea = await service.crear_mano_obra(
            s, escenario.orden_a, ManoObraCrear(descripcion="Frenos", horas=Decimal("2")), u
        )
        linea_id = linea.id

    async with sesion_servicio() as s:
        await s.execute(
            text("update public.talleres set tarifa_hora_default = 30 where id = :t"),
            {"t": escenario.taller_a},
        )

    async with sesion_rls(u) as s:
        vieja = await service.obtener_mano_obra(s, linea_id)
        nueva = await service.crear_mano_obra(
            s, escenario.orden_a, ManoObraCrear(descripcion="Otra cosa", horas=Decimal("1")), u
        )

    assert vieja.tarifa_hora == TARIFA, "la línea existente no se mueve"
    assert nueva.tarifa_hora == Decimal("30.00"), "la nueva toma la tarifa vigente"


async def test_se_puede_fijar_una_tarifa_distinta(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        linea = await service.crear_mano_obra(
            s,
            escenario.orden_a,
            ManoObraCrear(
                descripcion="Trabajo especializado", horas=Decimal("1"), tarifa_hora=Decimal("45")
            ),
            u,
        )

    assert linea.subtotal == Decimal("45.00")


async def test_editar_las_horas_recalcula_todo(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        linea_id = (
            await service.crear_mano_obra(
                s, escenario.orden_a, ManoObraCrear(descripcion="Frenos", horas=Decimal("2")), u
            )
        ).id

    async with sesion_rls(u) as s:
        linea = await service.actualizar_mano_obra(s, linea_id, ManoObraEditar(horas=Decimal("4")))

    assert linea.subtotal == Decimal("72.00")

    async with sesion_rls(u) as s:
        orden = await srv_ordenes.obtener(s, escenario.orden_a)
    assert orden.total_mano_obra == Decimal("72.00")


async def test_el_resumen_devuelve_horas_y_dinero(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        await service.crear_mano_obra(
            s,
            escenario.orden_a,
            ManoObraCrear(descripcion="Frenos delanteros", horas=Decimal("2")),
            u,
        )
        await service.crear_mano_obra(
            s, escenario.orden_a, ManoObraCrear(descripcion="Alineación", horas=Decimal("1.5")), u
        )

    async with sesion_rls(u) as s:
        horas, total = await service.total_mano_obra(s, escenario.orden_a)

    assert horas == Decimal("3.50")
    assert total == Decimal("63.00")


# -----------------------------------------------------------------------------
# Orden cerrada
# -----------------------------------------------------------------------------


async def _cerrar(orden_id: UUID, taller_id: UUID) -> None:
    asesor = _usuario(taller_id, Rol.ASESOR_SERVICIO)
    async with sesion_rls(asesor) as s:
        await srv_ordenes.cambiar_estado(
            s, orden_id, CambioEstado(estado=E.CANCELADO, comentario="Prueba"), asesor
        )


async def test_no_se_carga_trabajo_a_una_orden_cerrada(escenario: Escenario) -> None:
    await _cerrar(escenario.orden_a, escenario.taller_a)
    u = _usuario(escenario.taller_a)

    async with sesion_rls(u) as s:
        with pytest.raises(ErrorValidacion, match="ya no admite"):
            await service.crear_mano_obra(
                s, escenario.orden_a, ManoObraCrear(descripcion="Tarde", horas=Decimal("1")), u
            )


async def test_la_base_tambien_lo_impide(escenario: Escenario) -> None:
    """Saltándose el servicio, el trigger mch_linea_orden_abierta sigue ahí."""
    await _cerrar(escenario.orden_a, escenario.taller_a)
    u = _usuario(escenario.taller_a)

    async with sesion_rls(u) as s:
        with pytest.raises(DBAPIError) as excinfo:
            await s.execute(
                text("""
                    insert into public.orden_mano_obra
                           (taller_id, orden_id, descripcion, horas, tarifa_hora)
                    values (:t, :o, 'Por la puerta de atrás', 1, 18)
                """),
                {"t": escenario.taller_a, "o": escenario.orden_a},
            )

    assert "no admite cambios" in str(excinfo.value)


async def test_tampoco_se_registra_un_diagnostico_en_orden_cerrada(escenario: Escenario) -> None:
    await _cerrar(escenario.orden_a, escenario.taller_a)
    u = _usuario(escenario.taller_a)

    async with sesion_rls(u) as s:
        with pytest.raises(ErrorValidacion, match="ya no admite"):
            await service.crear_diagnostico(s, escenario.orden_a, _diag(), u)


# -----------------------------------------------------------------------------
# Aislamiento
# -----------------------------------------------------------------------------


async def test_no_ve_diagnosticos_de_otro_taller(escenario: Escenario) -> None:
    ub = _usuario(escenario.taller_b)
    async with sesion_rls(ub) as s:
        ajeno = await service.crear_diagnostico(s, escenario.orden_b, _diag(), ub)
        ajeno_id = ajeno.id

    ua = _usuario(escenario.taller_a)
    async with sesion_rls(ua) as s:
        with pytest.raises(ErrorNoEncontrado):
            await service.obtener_diagnostico(s, ajeno_id)

    async with sesion_rls(ua) as s:
        with pytest.raises(ErrorNoEncontrado):
            await service.listar_diagnosticos(s, escenario.orden_b)


async def test_no_carga_trabajo_en_una_orden_ajena(escenario: Escenario) -> None:
    ua = _usuario(escenario.taller_a)
    async with sesion_rls(ua) as s:
        with pytest.raises(ErrorNoEncontrado):
            await service.crear_mano_obra(
                s, escenario.orden_b, ManoObraCrear(descripcion="Intruso", horas=Decimal("1")), ua
            )


# -----------------------------------------------------------------------------
# Edición del diagnóstico
# -----------------------------------------------------------------------------


async def test_patch_parcial_del_diagnostico(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a)
    async with sesion_rls(u) as s:
        diag_id = (await service.crear_diagnostico(s, escenario.orden_a, _diag(), u)).id

    async with sesion_rls(u) as s:
        d = await service.actualizar_diagnostico(
            s, diag_id, DiagnosticoEditar(horas_estimadas=Decimal("4"))
        )

    assert d.horas_estimadas == Decimal("4.00")
    assert d.resumen == "Pastillas al límite y disco con alabeo"
