"""Alta, baja y cambio de rol de la gente del taller.

Estas pruebas crean **cuentas de verdad** en Supabase Auth y las borran al
terminar. Es deliberado: el alta consiste precisamente en coordinar dos sistemas
—la cuenta en Auth y el perfil en Postgres—, y una prueba que simulara el primero
verificaría solo la mitad que no falla. Las direcciones van bajo `example.com`,
que es un dominio reservado y no entrega correo a nadie.

La compensación sí se prueba con un doble, porque hace falta provocar un fallo
que con el sistema real no ocurre.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database import sesion_rls, sesion_servicio
from app.core.exceptions import ErrorConflicto, ErrorNoEncontrado, ErrorValidacion
from app.core.roles import Rol
from app.core.security import UsuarioAutenticado
from app.modules.usuarios import service
from app.modules.usuarios.cuentas import CuentasSupabase
from app.modules.usuarios.models import Perfil
from app.modules.usuarios.schemas import UsuarioCrear, UsuarioEditar

pytestmark = pytest.mark.integration


def _usuario(
    taller_id: UUID, rol: Rol = Rol.ADMIN_TALLER, id: UUID | None = None
) -> UsuarioAutenticado:
    return UsuarioAutenticado(id=id or uuid4(), taller_id=taller_id, rol=rol)


class CuentasFingidas:
    """Doble que inventa identificadores que no existen en `auth.users`.

    Sirve para lo que el sistema real no deja provocar: que el perfil falle
    después de haber creado la cuenta.
    """

    def __init__(self) -> None:
        self.borradas: list[UUID] = []

    async def crear(self, correo: str, clave: str) -> UUID:
        return uuid4()

    async def borrar(self, cuenta_id: UUID) -> None:
        self.borradas.append(cuenta_id)

    async def cambiar_clave(self, cuenta_id: UUID, clave: str) -> None: ...

    async def cambiar_correo(self, cuenta_id: UUID, correo: str) -> None: ...


@dataclass
class Escenario:
    taller: UUID
    otro_taller: UUID
    cuentas: CuentasSupabase
    #: Todo lo que haya que borrar de Auth al final.
    creadas: list[UUID] = field(default_factory=list)

    def correo(self) -> str:
        return f"prueba.{uuid4().hex[:10]}@example.com"

    async def alta(
        self,
        nombre: str,
        rol: Rol,
        taller: UUID | None = None,
        actor: UsuarioAutenticado | None = None,
    ) -> tuple[Perfil, str]:
        """Da de alta a alguien de verdad y apunta la cuenta para borrarla."""
        admin = actor or _usuario(taller or self.taller)
        async with sesion_rls(admin) as s:
            perfil, clave = await service.crear(
                s,
                UsuarioCrear(nombre_completo=nombre, email=self.correo(), rol=rol),
                admin,
                self.cuentas,
            )
            self.creadas.append(perfil.id)
            return perfil, clave


@pytest_asyncio.fixture
async def escenario() -> AsyncIterator[Escenario]:
    sfx = uuid4().hex[:8]
    async with sesion_servicio() as s:
        filas = await s.execute(
            text("""
                insert into public.talleres (nombre, slug, prefijo_orden)
                values ('Usr A ' || :sfx, 'usr-a-' || :sfx, 'USA'),
                       ('Usr B ' || :sfx, 'usr-b-' || :sfx, 'USB')
                returning id
            """),
            {"sfx": sfx},
        )
        ta, tb = (f[0] for f in filas.fetchall())

    e = Escenario(taller=ta, otro_taller=tb, cuentas=CuentasSupabase())
    try:
        yield e
    finally:
        # Primero las cuentas: el perfil se va con ellas por la clave foránea.
        for cuenta in e.creadas:
            await e.cuentas.borrar(cuenta)
        async with sesion_servicio() as s:
            await s.execute(
                text("delete from public.talleres where id = any(:ids)"), {"ids": [ta, tb]}
            )


# -----------------------------------------------------------------------------
# Alta
# -----------------------------------------------------------------------------


async def test_el_alta_crea_cuenta_y_perfil(escenario: Escenario) -> None:
    perfil, clave = await escenario.alta("Rosa Belmonte", Rol.TECNICO)

    assert perfil.rol is Rol.TECNICO
    assert perfil.activo
    assert perfil.email is not None and perfil.email.endswith("@example.com")
    assert len(clave) >= 16

    # El perfil y la cuenta comparten identificador: es lo que hace que el hook
    # de Auth encuentre el taller y el rol al emitir el token.
    async with sesion_servicio() as s:
        existe = await s.scalar(
            text("select count(*) from auth.users where id = :id"), {"id": perfil.id}
        )
    assert existe == 1


async def test_el_correo_no_se_repite(escenario: Escenario) -> None:
    perfil, _ = await escenario.alta("Primero", Rol.TECNICO)
    admin = _usuario(escenario.taller)

    async with sesion_rls(admin) as s:
        with pytest.raises(ErrorConflicto, match=r"(?i)ya existe una cuenta"):
            await service.crear(
                s,
                UsuarioCrear(
                    nombre_completo="Segundo", email=perfil.email or "", rol=Rol.ASESOR_SERVICIO
                ),
                admin,
                escenario.cuentas,
            )


async def test_si_el_perfil_falla_no_queda_una_cuenta_suelta(escenario: Escenario) -> None:
    """Una cuenta sin perfil puede autenticarse y no puede hacer nada.

    Además bloquearía ese correo para el siguiente intento, así que el alta
    deshace la cuenta cuando el perfil no llega a guardarse.
    """
    fingidas = CuentasFingidas()
    admin = _usuario(escenario.taller)

    async with sesion_rls(admin) as s:
        with pytest.raises(DBAPIError):
            await service.crear(
                s,
                UsuarioCrear(nombre_completo="Fantasma", email=escenario.correo(), rol=Rol.TECNICO),
                admin,
                fingidas,
            )

    assert len(fingidas.borradas) == 1, "la cuenta creada tiene que deshacerse"


async def test_un_tecnico_no_puede_dar_de_alta(escenario: Escenario) -> None:
    """La barrera es la política RLS, así que se prueba escribiendo directo."""
    tecnico = _usuario(escenario.taller, Rol.TECNICO)

    with pytest.raises(DBAPIError) as excinfo:
        async with sesion_rls(tecnico) as s:
            await s.execute(
                text("""
                    insert into public.perfiles (id, taller_id, nombre_completo, rol)
                    values (gen_random_uuid(), :t, 'Colado', 'admin_taller')
                """),
                {"t": escenario.taller},
            )

    assert "42501" in str(excinfo.value) or "row-level security" in str(excinfo.value).lower()


# -----------------------------------------------------------------------------
# Cambios de rol y de estado
# -----------------------------------------------------------------------------


async def test_el_rol_se_cambia_y_se_da_de_baja(escenario: Escenario) -> None:
    perfil, _ = await escenario.alta("Iván Segura", Rol.TECNICO)
    admin = _usuario(escenario.taller)

    async with sesion_rls(admin) as s:
        ascendido = await service.actualizar(
            s, perfil.id, UsuarioEditar(rol=Rol.ASESOR_SERVICIO), admin
        )
        assert ascendido.rol is Rol.ASESOR_SERVICIO

        de_baja = await service.actualizar(s, perfil.id, UsuarioEditar(activo=False), admin)
        assert not de_baja.activo

    # De baja no es borrado: el perfil sigue ahí y el historial conserva su autoría.
    async with sesion_rls(admin) as s:
        assert await service.obtener(s, perfil.id) is not None
        visibles = await service.listar(s)
        assert perfil.id not in [p.id for p in visibles]
        todos = await service.listar(s, incluir_inactivos=True)
        assert perfil.id in [p.id for p in todos]


async def test_nadie_se_cambia_el_rol_ni_se_da_de_baja_a_si_mismo(escenario: Escenario) -> None:
    """Si no, el único administrador se deja fuera de su propio taller."""
    perfil, _ = await escenario.alta("Jefa del taller", Rol.ADMIN_TALLER)
    ella = _usuario(escenario.taller, Rol.ADMIN_TALLER, id=perfil.id)

    async with sesion_rls(ella) as s:
        with pytest.raises(ErrorValidacion, match=r"(?i)a ti mismo"):
            await service.actualizar(s, perfil.id, UsuarioEditar(rol=Rol.TECNICO), ella)
        with pytest.raises(ErrorValidacion, match=r"(?i)a ti mismo"):
            await service.actualizar(s, perfil.id, UsuarioEditar(activo=False), ella)


async def test_el_ultimo_administrador_activo_se_protege(escenario: Escenario) -> None:
    """Un taller sin administrador solo se arregla entrando por Supabase."""
    primera, _ = await escenario.alta("Admin uno", Rol.ADMIN_TALLER)
    segunda, _ = await escenario.alta("Admin dos", Rol.ADMIN_TALLER)

    otra = _usuario(escenario.taller, Rol.ADMIN_TALLER, id=segunda.id)
    async with sesion_rls(otra) as s:
        # Con dos administradores, bajar a uno es legítimo.
        await service.actualizar(s, primera.id, UsuarioEditar(rol=Rol.TECNICO), otra)

    # Ahora solo queda una, y ni ella ni nadie puede dejarla sin el rol.
    una = _usuario(escenario.taller, Rol.ADMIN_TALLER, id=primera.id)
    async with sesion_rls(una) as s:
        with pytest.raises(ErrorConflicto, match=r"(?i)único administrador"):
            await service.actualizar(s, segunda.id, UsuarioEditar(rol=Rol.TECNICO), una)
        with pytest.raises(ErrorConflicto, match=r"(?i)único administrador"):
            await service.actualizar(s, segunda.id, UsuarioEditar(activo=False), una)


# -----------------------------------------------------------------------------
# Correo y contraseña
# -----------------------------------------------------------------------------


async def test_cambiar_el_correo_toca_las_dos_partes(escenario: Escenario) -> None:
    perfil, _ = await escenario.alta("Nuria Pardo", Rol.ASESOR_SERVICIO)
    nuevo = escenario.correo()
    admin = _usuario(escenario.taller)

    async with sesion_rls(admin) as s:
        actualizado = await service.cambiar_correo(s, perfil.id, nuevo, escenario.cuentas)

    assert actualizado.email == nuevo
    async with sesion_servicio() as s:
        en_auth = await s.scalar(
            text("select email from auth.users where id = :id"), {"id": perfil.id}
        )
    assert en_auth == nuevo, "la cuenta y el perfil no pueden quedar diciendo cosas distintas"


async def test_restablecer_la_clave_devuelve_una_nueva(escenario: Escenario) -> None:
    perfil, original = await escenario.alta("Olvidadizo", Rol.TECNICO)
    admin = _usuario(escenario.taller)

    async with sesion_rls(admin) as s:
        nueva = await service.restablecer_clave(s, perfil.id, escenario.cuentas)

    assert nueva != original
    assert len(nueva) >= 16


# -----------------------------------------------------------------------------
# Aislamiento
# -----------------------------------------------------------------------------


async def test_no_se_ve_ni_se_toca_a_la_gente_de_otro_taller(escenario: Escenario) -> None:
    ajeno, _ = await escenario.alta("De otro taller", Rol.TECNICO, taller=escenario.otro_taller)

    admin = _usuario(escenario.taller)
    async with sesion_rls(admin) as s:
        assert ajeno.id not in [p.id for p in await service.listar(s, incluir_inactivos=True)]

        with pytest.raises(ErrorNoEncontrado):
            await service.obtener(s, ajeno.id)

        with pytest.raises(ErrorNoEncontrado):
            await service.actualizar(s, ajeno.id, UsuarioEditar(rol=Rol.ADMIN_TALLER), admin)
