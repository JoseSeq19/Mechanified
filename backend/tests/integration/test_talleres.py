"""Configuración del taller contra la base real, con RLS activo.

El valor de estas pruebas está en lo que el servicio **no** hace: no filtra por
`taller_id` en ninguna consulta. Si las políticas `talleres_select` y
`talleres_update` dejaran de reducir la tabla a la fila del taller de la sesión,
un `select(Taller)` sin `where` empezaría a devolver filas ajenas y un UPDATE
las tocaría. Eso es exactamente lo que se comprueba aquí.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.database import sesion_rls, sesion_servicio
from app.core.exceptions import ErrorNoEncontrado, ErrorPermiso
from app.core.roles import Rol
from app.core.security import UsuarioAutenticado
from app.modules.talleres import service
from app.modules.talleres.schemas import TallerEditar

pytestmark = pytest.mark.integration

_ALTA_TALLERES = """
    insert into public.talleres
           (nombre, slug, prefijo_orden, moneda,
            tarifa_hora_default, impuesto_pct, dias_validez_presupuesto)
    values ('Cfg A ' || :sfx, 'cfg-a-' || :sfx, 'CFA', 'USD', 20.00, 16.00, 15),
           ('Cfg B ' || :sfx, 'cfg-b-' || :sfx, 'CFB', 'EUR', 35.00,  7.00, 30)
    returning id
"""


def _usuario(taller_id: UUID, rol: Rol = Rol.ADMIN_TALLER) -> UsuarioAutenticado:
    return UsuarioAutenticado(id=uuid4(), taller_id=taller_id, rol=rol)


@dataclass
class Escenario:
    """Dos talleres con configuración distinta, para notar si se cruzan."""

    taller_a: UUID
    taller_b: UUID


@pytest_asyncio.fixture
async def escenario() -> AsyncIterator[Escenario]:
    sfx = uuid4().hex[:8]
    async with sesion_servicio() as s:
        filas = await s.execute(text(_ALTA_TALLERES), {"sfx": sfx})
        a, b = (r[0] for r in filas.fetchall())

    yield Escenario(taller_a=a, taller_b=b)

    async with sesion_servicio() as s:
        await s.execute(text("delete from public.talleres where id = any(:ids)"), {"ids": [a, b]})


# -----------------------------------------------------------------------------
# Lectura
# -----------------------------------------------------------------------------


async def test_solo_se_ve_el_taller_propio(escenario: Escenario) -> None:
    """`obtener` no recibe id: la política ya dejó una sola fila visible."""
    async with sesion_rls(_usuario(escenario.taller_a)) as s:
        a = await service.obtener(s)
    async with sesion_rls(_usuario(escenario.taller_b)) as s:
        b = await service.obtener(s)

    assert a.id == escenario.taller_a
    assert b.id == escenario.taller_b
    assert a.moneda == "USD"
    assert b.moneda == "EUR"


async def test_la_tabla_entera_es_una_sola_fila(escenario: Escenario) -> None:
    """Ni siquiera un contador sin filtro ve más de un taller."""
    async with sesion_rls(_usuario(escenario.taller_a)) as s:
        total = await s.scalar(text("select count(*) from public.talleres"))

    assert total == 1


async def test_todos_los_roles_leen_la_configuracion(escenario: Escenario) -> None:
    """La lectura es de todo el taller: el técnico necesita la moneda igual."""
    for rol in (Rol.ASESOR_SERVICIO, Rol.TECNICO, Rol.ENCARGADO_REPUESTOS):
        async with sesion_rls(_usuario(escenario.taller_a, rol)) as s:
            assert (await service.obtener(s)).id == escenario.taller_a


async def test_sesion_con_taller_que_no_existe_da_no_encontrado() -> None:
    """Pasa si se borra un taller con sesiones abiertas.

    Mejor decirlo así que devolver una pantalla vacía sin explicación.
    """
    async with sesion_rls(_usuario(uuid4())) as s:
        with pytest.raises(ErrorNoEncontrado):
            await service.obtener(s)


# -----------------------------------------------------------------------------
# Escritura
# -----------------------------------------------------------------------------


async def test_actualizar_cambia_solo_lo_que_viene(escenario: Escenario) -> None:
    async with sesion_rls(_usuario(escenario.taller_a)) as s:
        taller = await service.actualizar(s, TallerEditar(tarifa_hora_default=Decimal("28.50")))

    assert taller.tarifa_hora_default == Decimal("28.50")
    # Lo que no vino en el PATCH sigue igual.
    assert taller.impuesto_pct == Decimal("16.00")
    assert taller.moneda == "USD"
    assert taller.dias_validez_presupuesto == 15


async def test_un_patch_no_alcanza_al_otro_taller(escenario: Escenario) -> None:
    async with sesion_rls(_usuario(escenario.taller_a)) as s:
        await service.actualizar(s, TallerEditar(nombre="Renombrado por A"))

    async with sesion_rls(_usuario(escenario.taller_b)) as s:
        b = await service.obtener(s)

    assert b.nombre.startswith("Cfg B")


async def test_un_update_sin_filtro_solo_toca_el_taller_propio(escenario: Escenario) -> None:
    """Es la prueba de la política, no del servicio.

    Se lanza a mano el UPDATE más descuidado posible —sin `where`— para
    comprobar que lo que impide tocar al taller B es Postgres y no el cuidado de
    quien escribió la consulta.
    """
    async with sesion_rls(_usuario(escenario.taller_a)) as s:
        tocadas = (
            await s.scalars(text("update public.talleres set impuesto_pct = 1 returning id"))
        ).all()

    assert list(tocadas) == [escenario.taller_a]

    async with sesion_servicio() as s:
        impuesto_b = await s.scalar(
            text("select impuesto_pct from public.talleres where id = :id"),
            {"id": escenario.taller_b},
        )

    assert impuesto_b == Decimal("7.00")


@pytest.mark.parametrize("rol", [Rol.ASESOR_SERVICIO, Rol.TECNICO, Rol.ENCARGADO_REPUESTOS])
async def test_quien_no_es_admin_no_cambia_la_configuracion(escenario: Escenario, rol: Rol) -> None:
    """RLS deja el UPDATE sin filas, no lanza error.

    Por eso el servicio traduce la fila desaparecida a una falta de permiso: si
    no, esto saldría como un 500 y daría la impresión de que algo se rompió.
    """
    async with sesion_rls(_usuario(escenario.taller_a, rol)) as s:
        with pytest.raises(ErrorPermiso):
            await service.actualizar(s, TallerEditar(impuesto_pct=Decimal("0")))

    async with sesion_servicio() as s:
        impuesto = await s.scalar(
            text("select impuesto_pct from public.talleres where id = :id"),
            {"id": escenario.taller_a},
        )

    assert impuesto == Decimal("16.00")


async def test_cambiar_el_prefijo_no_reinicia_el_contador(escenario: Escenario) -> None:
    """Lo que la interfaz le promete al administrador.

    El trigger `mch_talleres_secuencia` sincroniza el prefijo de
    `secuencias_folio`, pero deja el contador donde estaba: las órdenes ya
    emitidas conservan su folio y las nuevas estrenan el prefijo nuevo.
    """
    async with sesion_servicio() as s:
        await s.execute(
            text("update public.secuencias_folio set valor = 42 where taller_id = :id"),
            {"id": escenario.taller_a},
        )

    async with sesion_rls(_usuario(escenario.taller_a)) as s:
        nuevo = await service.actualizar(s, TallerEditar(prefijo_orden="nvo"))

    assert nuevo.prefijo_orden == "NVO"

    async with sesion_servicio() as s:
        fila = (
            await s.execute(
                text("select prefijo, valor from public.secuencias_folio where taller_id = :id"),
                {"id": escenario.taller_a},
            )
        ).one()

    assert fila.prefijo == "NVO"
    assert fila.valor == 42
