"""El panel del taller.

Estas cifras tienen una particularidad incómoda: cuando salen mal, siguen
saliendo. Un `sum()` que se cuela en el taller de al lado devuelve un número
perfectamente creíble, y una tasa mal calculada también. No hay pantalla en
blanco que avise.

Por eso lo primero que se prueba aquí es el aislamiento —dos talleres con datos
a la vez— y lo segundo, que cada tasa divida entre lo que dice dividir.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.database import sesion_rls, sesion_servicio
from app.core.roles import Rol
from app.core.security import UsuarioAutenticado
from app.modules.clientes import service as srv_clientes
from app.modules.clientes.schemas import ClienteCrear
from app.modules.diagnosticos import service as srv_diag
from app.modules.diagnosticos.schemas import ManoObraCrear
from app.modules.encuestas import service as srv_encuestas
from app.modules.encuestas.schemas import RespuestaCliente
from app.modules.metricas import service
from app.modules.ordenes import service as srv_ordenes
from app.modules.ordenes.estados import EstadoOrden as E
from app.modules.ordenes.schemas import CambioEstado, OrdenCrear, OrdenEditar
from app.modules.presupuestos import service as srv_presupuestos
from app.modules.presupuestos.schemas import PresupuestoEmitir
from app.modules.presupuestos.schemas import RespuestaCliente as RespuestaPresu
from app.modules.vehiculos import service as srv_vehiculos
from app.modules.vehiculos.schemas import VehiculoCrear

pytestmark = pytest.mark.integration

TARIFA = Decimal("25.00")
HORAS = Decimal("3")
#: 3 h × 25 = 75, sin impuesto ni repuestos: el total de la orden entregada.
TOTAL_ENTREGADA = Decimal("75.00")

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
class Taller:
    id: UUID
    cliente: UUID
    vehiculo: UUID


@dataclass
class Escenario:
    a: Taller
    b: Taller
    entregada: UUID
    abierta: UUID


async def _montar(taller_id: UUID, placa: str) -> Taller:
    u = _usuario(taller_id)
    async with sesion_rls(u) as s:
        cliente = await srv_clientes.crear(
            s,
            ClienteCrear(nombre=f"Cliente {placa}", email=f"cliente.{placa.lower()}@example.com"),
            u,
        )
        vehiculo = await srv_vehiculos.crear(
            s,
            VehiculoCrear(cliente_id=cliente.id, placa=placa, marca="Nissan", modelo="Versa"),
            u,
        )
    return Taller(id=taller_id, cliente=cliente.id, vehiculo=vehiculo.id)


async def _crear_orden(t: Taller, motivo: str) -> UUID:
    u = _usuario(t.id)
    async with sesion_rls(u) as s:
        orden = await srv_ordenes.crear(
            s,
            OrdenCrear(cliente_id=t.cliente, vehiculo_id=t.vehiculo, motivo_ingreso=motivo),
            u,
        )
        await srv_diag.crear_mano_obra(
            s, orden.id, ManoObraCrear(descripcion="Trabajo de taller", horas=HORAS), u
        )
    return orden.id


async def _mover(t: Taller, orden_id: UUID, estados: tuple[E, ...]) -> None:
    u = _usuario(t.id)
    for estado in estados:
        async with sesion_rls(u) as s:
            await srv_ordenes.cambiar_estado(s, orden_id, CambioEstado(estado=estado), u)


@pytest_asyncio.fixture
async def escenario() -> AsyncIterator[Escenario]:
    """Dos talleres con datos, y en el primero una orden entregada y otra viva."""
    sfx = uuid4().hex[:8]
    async with sesion_servicio() as s:
        filas = await s.execute(
            text("""
                insert into public.talleres
                       (nombre, slug, prefijo_orden, tarifa_hora_default)
                values ('Met A ' || :sfx, 'met-a-' || :sfx, 'MTA', :tarifa),
                       ('Met B ' || :sfx, 'met-b-' || :sfx, 'MTB', :tarifa)
                returning id
            """),
            {"sfx": sfx, "tarifa": TARIFA},
        )
        ta, tb = (f[0] for f in filas.fetchall())

    a = await _montar(ta, f"MA{sfx[:5].upper()}")
    b = await _montar(tb, f"MB{sfx[:5].upper()}")

    entregada = await _crear_orden(a, "Servicio completo")
    await _mover(a, entregada, HASTA_ENTREGA)

    abierta = await _crear_orden(a, "Cambio de embrague")
    await _mover(
        a, abierta, (E.EN_DIAGNOSTICO, E.PRESUPUESTO_PENDIENTE, E.APROBADO, E.EN_REPARACION)
    )

    yield Escenario(a=a, b=b, entregada=entregada, abierta=abierta)

    async with sesion_servicio() as s:
        await s.execute(text("delete from public.talleres where id = any(:ids)"), {"ids": [ta, tb]})


async def _panel(taller: UUID, dias: int = 30):
    u = _usuario(taller)
    async with sesion_rls(u) as s:
        return await service.panel(s, dias)


# -----------------------------------------------------------------------------
# Aislamiento
# -----------------------------------------------------------------------------


async def test_el_panel_no_suma_el_taller_de_al_lado(escenario: Escenario) -> None:
    """La prueba que más falta hace: un total mal filtrado no se nota a simple vista."""
    ajena = await _crear_orden(escenario.b, "Trabajo del otro taller")
    await _mover(escenario.b, ajena, HASTA_ENTREGA)

    panel = await _panel(escenario.a.id)

    assert panel.produccion.entregadas == 1
    assert panel.produccion.facturado == TOTAL_ENTREGADA
    assert panel.trabajo_vivo.abiertas == 1

    # Y el de enfrente ve lo suyo, no lo de este.
    otro = await _panel(escenario.b.id)
    assert otro.produccion.entregadas == 1
    assert otro.trabajo_vivo.abiertas == 0


# -----------------------------------------------------------------------------
# Trabajo vivo
# -----------------------------------------------------------------------------


async def test_trabajo_vivo_ignora_lo_terminado(escenario: Escenario) -> None:
    panel = await _panel(escenario.a.id)
    por_estado = {c.estado: c.cantidad for c in panel.trabajo_vivo.por_estado}

    assert panel.trabajo_vivo.abiertas == 1
    assert por_estado["en_reparacion"] == 1
    assert "entregado" not in por_estado, "el trabajo vivo es lo que sigue en el taller"
    assert panel.trabajo_vivo.atrasadas == 0


async def test_una_promesa_vencida_cuenta_como_atrasada(escenario: Escenario) -> None:
    u = _usuario(escenario.a.id)
    async with sesion_rls(u) as s:
        await srv_ordenes.actualizar(
            s,
            escenario.abierta,
            OrdenEditar(fecha_promesa=datetime.now(UTC) - timedelta(days=2)),
        )

    panel = await _panel(escenario.a.id)

    assert panel.trabajo_vivo.atrasadas == 1


# -----------------------------------------------------------------------------
# Producción
# -----------------------------------------------------------------------------


async def test_produccion_resume_lo_entregado(escenario: Escenario) -> None:
    panel = await _panel(escenario.a.id)
    p = panel.produccion

    assert p.recibidas == 2
    assert p.entregadas == 1
    assert p.canceladas == 0
    assert p.facturado == TOTAL_ENTREGADA
    assert p.ticket_promedio == TOTAL_ENTREGADA
    assert p.mano_obra == TOTAL_ENTREGADA
    assert p.repuestos == Decimal("0.00")
    assert p.horas_ciclo_promedio is not None


async def test_sin_entregas_no_hay_ticket_promedio(escenario: Escenario) -> None:
    """Un cero aquí se leería como "el ticket medio se hundió", y no es eso."""
    panel = await _panel(escenario.b.id)

    assert panel.produccion.entregadas == 0
    assert panel.produccion.ticket_promedio is None


async def test_el_periodo_deja_fuera_lo_viejo(escenario: Escenario) -> None:
    async with sesion_servicio() as s:
        await s.execute(
            text("""
                update public.ordenes_servicio
                   set fecha_entrega = now() - interval '60 days'
                 where id = :o
            """),
            {"o": escenario.entregada},
        )

    reciente = await _panel(escenario.a.id, dias=7)
    amplio = await _panel(escenario.a.id, dias=90)

    assert reciente.produccion.entregadas == 0
    assert reciente.produccion.facturado == Decimal("0")
    assert amplio.produccion.entregadas == 1


async def test_el_periodo_se_acota_a_lo_razonable(escenario: Escenario) -> None:
    """Pedir diez años no debe convertirse en una consulta a toda la historia."""
    panel = await _panel(escenario.a.id, dias=99_999)

    assert panel.dias == service.DIAS_MAXIMO


# -----------------------------------------------------------------------------
# Tiempos por etapa
# -----------------------------------------------------------------------------


async def test_los_tiempos_salen_de_la_bitacora(escenario: Escenario) -> None:
    panel = await _panel(escenario.a.id)
    etapas = {e.estado: e for e in panel.etapas}

    # Las dos órdenes pasaron por recepción y diagnóstico.
    assert etapas["recibido"].transiciones == 2
    assert etapas["en_diagnostico"].transiciones == 2
    # Y solo una llegó a control de calidad.
    assert etapas["control_calidad"].transiciones == 1
    assert all(e.horas_promedio >= 0 for e in panel.etapas)


async def test_la_etapa_en_curso_no_se_promedia(escenario: Escenario) -> None:
    """La orden abierta sigue en reparación: esa etapa aún no ha terminado.

    Contarla acortaría el promedio, porque se estaría midiendo un tramo a medias
    como si fuera completo.
    """
    panel = await _panel(escenario.a.id)
    etapas = {e.estado: e for e in panel.etapas}

    # La entregada sí pasó por reparación; la abierta todavía está ahí.
    assert etapas["en_reparacion"].transiciones == 1


# -----------------------------------------------------------------------------
# Tasas
# -----------------------------------------------------------------------------


async def test_la_tasa_de_aprobacion_ignora_lo_que_nadie_contestó(
    escenario: Escenario,
) -> None:
    """Un presupuesto sin responder no es un rechazo: todavía no es nada."""
    u = _usuario(escenario.a.id, Rol.ASESOR_SERVICIO)

    async with sesion_rls(u) as s:
        aprobado = await srv_presupuestos.emitir(s, escenario.abierta, PresupuestoEmitir(), u)
        await srv_presupuestos.enviar(s, aprobado.id)
        await srv_presupuestos.responder(s, aprobado.id, RespuestaPresu(aprobado=True))

    otra = await _crear_orden(escenario.a, "Otra más")
    async with sesion_rls(u) as s:
        pendiente = await srv_presupuestos.emitir(s, otra, PresupuestoEmitir(), u)
        await srv_presupuestos.enviar(s, pendiente.id)

    panel = await _panel(escenario.a.id)

    assert panel.presupuestos.emitidos >= 2
    assert panel.presupuestos.aprobados == 1
    assert panel.presupuestos.rechazados == 0
    assert panel.presupuestos.tasa_aprobacion == 100.0


async def test_la_tasa_de_rechazo_mide_el_retrabajo(escenario: Escenario) -> None:
    """Se escriben los controles directo en la base: aquí se mide, no se inspecciona."""
    async with sesion_rls(_usuario(escenario.a.id)) as s:
        for resultado in ("aprobado", "rechazado"):
            await s.execute(
                text("""
                    insert into public.controles_calidad
                           (taller_id, orden_id, resultado, cerrado_en)
                    values (:t, :o, :r, now())
                """),
                {"t": escenario.a.id, "o": escenario.entregada, "r": resultado},
            )

    panel = await _panel(escenario.a.id)

    assert panel.calidad.controles == 2
    assert panel.calidad.tasa_rechazo == 50.0


async def test_sin_controles_cerrados_no_hay_tasa(escenario: Escenario) -> None:
    panel = await _panel(escenario.b.id)

    assert panel.calidad.controles == 0
    assert panel.calidad.tasa_rechazo is None


# -----------------------------------------------------------------------------
# Satisfacción y técnicos
# -----------------------------------------------------------------------------


async def test_la_satisfaccion_del_periodo_entra_en_el_panel(escenario: Escenario) -> None:
    u = _usuario(escenario.a.id)
    async with sesion_rls(u) as s:
        encuesta = await srv_encuestas.obtener_de_orden(s, escenario.entregada)
    assert encuesta is not None

    await srv_encuestas.responder_por_token(
        encuesta.token_publico,
        RespuestaCliente(puntaje_atencion=5, puntaje_tiempo=4, puntaje_calidad=5, recomendaria=10),
    )

    panel = await _panel(escenario.a.id)

    assert panel.satisfaccion.respondidas == 1
    assert panel.satisfaccion.nps == 100
    assert panel.satisfaccion.promedio_tiempo == 4.0


async def test_sin_tecnicos_asignados_el_cuadro_queda_vacio(escenario: Escenario) -> None:
    """Y no falla ni inventa una fila sin nombre.

    El cuadro de honor se queda en este caso, deliberadamente. Para probarlo con
    datos haría falta un perfil, y `perfiles.id` referencia a `auth.users`: estas
    pruebas no crean usuarios de autenticación, porque correrían contra el
    proyecto hospedado y dejarían cuentas sueltas si un fallo interrumpe la
    limpieza. El ranking se verifica a mano contra datos reales.
    """
    panel = await _panel(escenario.a.id)

    assert panel.tecnicos == []
