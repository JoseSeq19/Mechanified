"""Aislamiento entre talleres a través de la sesión con RLS.

Es la prueba más importante del proyecto. Todo lo demás puede fallar de forma
visible y molesta; esto fallaría en silencio y filtraría datos de un taller a
otro.

La prueba crea sus propios dos talleres con la sesión de servicio, verifica el
aislamiento con sesiones de usuario, y limpia al terminar. No depende de datos
preexistentes, así que corre igual contra Supabase local o hospedado.

    pytest tests/integration -v -m integration
"""

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database import sesion_rls, sesion_servicio
from app.core.exceptions import extraer_sqlstate
from app.core.roles import Rol
from app.core.security import UsuarioAutenticado

pytestmark = pytest.mark.integration


def _usuario(taller_id: UUID, rol: Rol = Rol.ADMIN_TALLER) -> UsuarioAutenticado:
    """Identidad sintética.

    No hace falta un token real: lo que RLS evalúa son los claims, y esta prueba
    los inyecta por el mismo camino que usaría un request autenticado.
    """
    return UsuarioAutenticado(id=uuid4(), taller_id=taller_id, rol=rol)


@pytest_asyncio.fixture
async def dos_talleres() -> AsyncIterator[tuple[UUID, UUID]]:
    sufijo = uuid4().hex[:8]
    async with sesion_servicio() as s:
        filas = await s.execute(
            text("""
                insert into public.talleres (nombre, slug, prefijo_orden)
                values ('Prueba A ' || :sfx, 'prueba-a-' || :sfx, 'PRA'),
                       ('Prueba B ' || :sfx, 'prueba-b-' || :sfx, 'PRB')
                returning id
            """),
            {"sfx": sufijo},
        )
        a, b = (r[0] for r in filas.fetchall())

    yield a, b

    async with sesion_servicio() as s:
        await s.execute(text("delete from public.talleres where id = any(:ids)"), {"ids": [a, b]})


async def test_solo_ve_su_propio_taller(dos_talleres: tuple[UUID, UUID]) -> None:
    a, b = dos_talleres

    async with sesion_rls(_usuario(a)) as s:
        visibles = (await s.execute(text("select id from public.talleres"))).scalars().all()

    assert visibles == [a], "un usuario debe ver su taller y ningún otro"
    assert b not in visibles


async def test_no_puede_escribir_en_taller_ajeno(dos_talleres: tuple[UUID, UUID]) -> None:
    a, b = dos_talleres

    with pytest.raises(DBAPIError) as excinfo:
        async with sesion_rls(_usuario(a)) as s:
            await s.execute(
                text("insert into public.clientes (taller_id, nombre) values (:t, 'Intruso')"),
                {"t": b},
            )

    # 42501 = insufficient_privilege. Es RLS rechazando, no una falla de la app.
    assert extraer_sqlstate(excinfo.value) == "42501"


async def test_no_ve_clientes_de_otro_taller(dos_talleres: tuple[UUID, UUID]) -> None:
    a, b = dos_talleres

    async with sesion_servicio() as s:
        await s.execute(
            text("insert into public.clientes (taller_id, nombre) values (:t, 'Cliente de B')"),
            {"t": b},
        )

    async with sesion_rls(_usuario(a)) as s:
        visibles = (await s.execute(text("select nombre from public.clientes"))).scalars().all()

    assert "Cliente de B" not in visibles


async def test_sin_claims_no_ve_nada(dos_talleres: tuple[UUID, UUID]) -> None:
    """Un taller inexistente en los claims no da acceso a nada.

    Cubre el caso del hook de Auth apagado: el token es válido pero no trae
    tenant. El sistema debe fallar cerrado.
    """
    async with sesion_rls(_usuario(uuid4())) as s:
        visibles = (await s.execute(text("select id from public.talleres"))).scalars().all()

    assert visibles == []


async def test_rol_del_claim_gobierna_la_escritura(dos_talleres: tuple[UUID, UUID]) -> None:
    """El técnico no puede dar de alta clientes; el asesor sí.

    Mismo taller, misma consulta: lo único que cambia es el claim `rol`.
    """
    a, _ = dos_talleres

    with pytest.raises(DBAPIError) as excinfo:
        async with sesion_rls(_usuario(a, Rol.TECNICO)) as s:
            await s.execute(
                text("insert into public.clientes (taller_id, nombre) values (:t, 'X')"),
                {"t": a},
            )

    assert extraer_sqlstate(excinfo.value) == "42501"

    async with sesion_rls(_usuario(a, Rol.ASESOR_SERVICIO)) as s:
        await s.execute(
            text("insert into public.clientes (taller_id, nombre) values (:t, 'Cliente legítimo')"),
            {"t": a},
        )
