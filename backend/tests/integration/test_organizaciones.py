"""Organizaciones y cuentas del sitio, contra la base real con RLS activo.

Tres cosas importan aquí, por orden:

1. Que la organización **no abra** el aislamiento entre sedes. Dos talleres de
   la misma organización siguen sin verse, y una sede ve su organización y
   ninguna otra.
2. Que el alta por cuenta propia sea una puerta estrecha: solo para la propia
   cuenta, una sola vez, y sin la llave de servicio.
3. Que las solicitudes no se puedan falsear desde la API de datos expuesta: ni
   el correo, ni el estado, ni la cuenta.

Las cuentas se crean directamente en `auth.users`, como hace el seed: ninguna
prueba de aquí llama a la API de Auth.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database import sesion_rls, sesion_servicio
from app.core.exceptions import ErrorConflicto, extraer_sqlstate
from app.core.roles import Rol
from app.core.security import CuentaAutenticada, UsuarioAutenticado
from app.modules.organizaciones import alta, service
from app.modules.organizaciones.models import EstadoSolicitud
from app.modules.organizaciones.schemas import OrganizacionNueva, SolicitudNueva

pytestmark = pytest.mark.integration


def _usuario(taller_id: UUID, rol: Rol = Rol.ADMIN_TALLER) -> UsuarioAutenticado:
    return UsuarioAutenticado(id=uuid4(), taller_id=taller_id, rol=rol)


# -----------------------------------------------------------------------------
# Escenario: dos organizaciones, una de ellas con dos sedes
# -----------------------------------------------------------------------------


@dataclass
class Escenario:
    org_grupo: UUID
    org_suelta: UUID
    sede_1: UUID
    sede_2: UUID
    taller_suelto: UUID


@pytest_asyncio.fixture
async def escenario() -> AsyncIterator[Escenario]:
    sfx = uuid4().hex[:8]
    async with sesion_servicio() as s:
        org_grupo = await s.scalar(
            text(
                "insert into public.organizaciones (nombre, slug)"
                " values ('Grupo ' || :sfx, 'grupo-' || :sfx) returning id"
            ),
            {"sfx": sfx},
        )
        filas = await s.execute(
            text("""
                insert into public.talleres (organizacion_id, nombre, slug, prefijo_orden)
                values (:org, 'Sede 1 ' || :sfx, 'sede-1-' || :sfx, 'SA'),
                       (:org, 'Sede 2 ' || :sfx, 'sede-2-' || :sfx, 'SB')
                returning id
            """),
            {"org": org_grupo, "sfx": sfx},
        )
        sede_1, sede_2 = (r[0] for r in filas.fetchall())
        # Sin organización: funda la suya.
        taller_suelto, org_suelta = (
            await s.execute(
                text(
                    "insert into public.talleres (nombre, slug, prefijo_orden)"
                    " values ('Suelto ' || :sfx, 'suelto-' || :sfx, 'SU')"
                    " returning id, organizacion_id"
                ),
                {"sfx": sfx},
            )
        ).one()

    yield Escenario(org_grupo, org_suelta, sede_1, sede_2, taller_suelto)

    async with sesion_servicio() as s:
        await s.execute(
            text("delete from public.talleres where id = any(:ids)"),
            {"ids": [sede_1, sede_2, taller_suelto]},
        )


async def test_cada_sede_ve_su_organizacion_y_ninguna_otra(escenario: Escenario) -> None:
    async with sesion_rls(_usuario(escenario.sede_1, Rol.TECNICO)) as s:
        visibles = (await s.execute(text("select id from public.organizaciones"))).scalars().all()
        org = await service.obtener(s)

    assert visibles == [escenario.org_grupo]
    assert org.id == escenario.org_grupo

    async with sesion_rls(_usuario(escenario.taller_suelto)) as s:
        visibles = (await s.execute(text("select id from public.organizaciones"))).scalars().all()

    assert visibles == [escenario.org_suelta]


async def test_la_organizacion_no_abre_el_aislamiento_entre_sedes(escenario: Escenario) -> None:
    """Sede 1 y sede 2 son del mismo cliente y siguen sin verse."""
    async with sesion_rls(_usuario(escenario.sede_1)) as s:
        talleres = (await s.execute(text("select id from public.talleres"))).scalars().all()

    assert talleres == [escenario.sede_1]


async def test_el_taller_suelto_funda_una_organizacion_con_su_nombre(escenario: Escenario) -> None:
    async with sesion_servicio() as s:
        nombre = await s.scalar(
            text("select nombre from public.organizaciones where id = :id"),
            {"id": escenario.org_suelta},
        )

    assert nombre is not None
    assert nombre.startswith("Suelto ")


async def test_la_administracion_no_cambia_su_sede_de_organizacion(escenario: Escenario) -> None:
    """Ni con un UPDATE directo, que es lo que permitiría la API de datos."""
    with pytest.raises(DBAPIError) as excinfo:
        async with sesion_rls(_usuario(escenario.taller_suelto)) as s:
            await s.execute(
                text("update public.talleres set organizacion_id = :org"),
                {"org": escenario.org_grupo},
            )

    assert extraer_sqlstate(excinfo.value) == "42501"


async def test_nadie_escribe_organizaciones_desde_una_sesion(escenario: Escenario) -> None:
    async with sesion_rls(_usuario(escenario.sede_1)) as s:
        filas = await s.execute(
            text("update public.organizaciones set nombre = 'Usurpada'"),
        )
        assert filas.rowcount == 0

    with pytest.raises(DBAPIError) as excinfo:
        async with sesion_rls(_usuario(escenario.sede_1)) as s:
            await s.execute(
                text("insert into public.organizaciones (nombre, slug) values ('X', 'x-x-x')")
            )
    assert extraer_sqlstate(excinfo.value) == "42501"


async def test_la_organizacion_se_va_con_su_ultimo_taller() -> None:
    sfx = uuid4().hex[:8]
    async with sesion_servicio() as s:
        taller, org = (
            await s.execute(
                text(
                    "insert into public.talleres (nombre, slug, prefijo_orden)"
                    " values ('Efímero ' || :sfx, 'efimero-' || :sfx, 'EF')"
                    " returning id, organizacion_id"
                ),
                {"sfx": sfx},
            )
        ).one()
        await s.execute(text("delete from public.talleres where id = :id"), {"id": taller})
        queda = await s.scalar(
            text("select count(*) from public.organizaciones where id = :id"), {"id": org}
        )

    assert queda == 0


# -----------------------------------------------------------------------------
# Cuentas del sitio
# -----------------------------------------------------------------------------


@dataclass
class Cuentas:
    """Fábrica de cuentas de Auth para la prueba, que limpia lo que crea."""

    creadas: list[UUID] = field(default_factory=list)

    async def nueva(self) -> CuentaAutenticada:
        cuenta = CuentaAutenticada(id=uuid4(), email=f"org-{uuid4().hex[:10]}@example.com")
        async with sesion_servicio() as s:
            await s.execute(
                text("""
                    insert into auth.users (
                      instance_id, id, aud, role, email, encrypted_password,
                      created_at, updated_at, raw_app_meta_data, raw_user_meta_data,
                      is_super_admin
                    ) values (
                      '00000000-0000-0000-0000-000000000000', :id, 'authenticated',
                      'authenticated', :email, '', now(), now(),
                      '{"provider":"email","providers":["email"]}', '{}', false
                    )
                """),
                {"id": cuenta.id, "email": cuenta.email},
            )
        self.creadas.append(cuenta.id)
        return cuenta


@pytest_asyncio.fixture
async def cuentas() -> AsyncIterator[Cuentas]:
    fabrica = Cuentas()
    yield fabrica

    async with sesion_servicio() as s:
        # Borrar el taller arrastra el perfil y, con él vacío, la organización.
        await s.execute(
            text(
                "delete from public.talleres where id in"
                " (select taller_id from public.perfiles where id = any(:ids))"
            ),
            {"ids": fabrica.creadas},
        )
        await s.execute(
            text("delete from auth.users where id = any(:ids)"), {"ids": fabrica.creadas}
        )


def _nueva_organizacion(nombre: str = "Taller Prueba", **extra: object) -> OrganizacionNueva:
    return OrganizacionNueva(nombre=nombre, nombre_completo="Ana Prueba", **extra)  # type: ignore[arg-type]


async def test_una_cuenta_nueva_no_ve_datos_de_ningun_taller(cuentas: Cuentas) -> None:
    cuenta = await cuentas.nueva()

    async with sesion_rls(cuenta) as s:
        talleres = await s.scalar(text("select count(*) from public.talleres"))
        organizaciones = await s.scalar(text("select count(*) from public.organizaciones"))
        estado = await service.estado_cuenta(s, cuenta)

    assert talleres == 0
    assert organizaciones == 0
    assert estado.organizacion is None
    assert estado.solicitud is None


async def test_crear_la_propia_deja_a_la_cuenta_como_administradora(cuentas: Cuentas) -> None:
    cuenta = await cuentas.nueva()

    async with sesion_rls(cuenta) as s:
        estado = await service.crear_propia(
            s, cuenta, _nueva_organizacion("Grupo Cerro Verde", sede="Cerro Verde Norte")
        )

    assert estado.organizacion is not None
    assert estado.organizacion.organizacion_nombre == "Grupo Cerro Verde"
    assert estado.organizacion.taller_nombre == "Cerro Verde Norte"
    assert estado.organizacion.rol is Rol.ADMIN_TALLER
    assert estado.organizacion.activo

    # Con el token renovado —que ya lleva el taller— entra como cualquier sede.
    usuario = UsuarioAutenticado(
        id=cuenta.id, taller_id=estado.organizacion.taller_id, rol=Rol.ADMIN_TALLER
    )
    async with sesion_rls(usuario) as s:
        org = await service.obtener(s)
        prefijo = await s.scalar(text("select prefijo_orden from public.talleres"))

    assert org.nombre == "Grupo Cerro Verde"
    assert prefijo == "CER"


async def test_una_cuenta_solo_funda_una_organizacion(cuentas: Cuentas) -> None:
    cuenta = await cuentas.nueva()
    async with sesion_rls(cuenta) as s:
        await service.crear_propia(s, cuenta, _nueva_organizacion("Primera"))

    with pytest.raises(ErrorConflicto, match="ya pertenece a Primera"):
        async with sesion_rls(cuenta) as s:
            await service.crear_propia(s, cuenta, _nueva_organizacion("Segunda"))


async def test_dos_organizaciones_con_el_mismo_nombre_no_chocan(cuentas: Cuentas) -> None:
    una, otra = await cuentas.nueva(), await cuentas.nueva()
    nombre = f"Taller Homonimo {uuid4().hex[:6]}"

    async with sesion_rls(una) as s:
        a = await service.crear_propia(s, una, _nueva_organizacion(nombre))
    async with sesion_rls(otra) as s:
        b = await service.crear_propia(s, otra, _nueva_organizacion(nombre))

    assert a.organizacion and b.organizacion
    async with sesion_servicio() as s:
        slugs = (
            (
                await s.execute(
                    text(
                        "select slug from public.organizaciones where id = any(:ids) order by slug"
                    ),
                    {"ids": [a.organizacion.organizacion_id, b.organizacion.organizacion_id]},
                )
            )
            .scalars()
            .all()
        )

    assert len(set(slugs)) == 2
    assert slugs[1] == f"{slugs[0]}-2"


async def test_el_nucleo_del_alta_no_esta_al_alcance_de_una_sesion(cuentas: Cuentas) -> None:
    """`mch_crear_organizacion` recibe la cuenta por parámetro: abierta, dejaría
    fundar organizaciones a nombre de otro."""
    atacante, victima = await cuentas.nueva(), await cuentas.nueva()

    with pytest.raises(DBAPIError) as excinfo:
        async with sesion_rls(atacante) as s:
            await s.execute(
                text(
                    "select * from public.mch_crear_organizacion("
                    " :v, 'Robada', 'Robada', 'robada', 'robada', 'ROB', 'Nadie')"
                ),
                {"v": victima.id},
            )

    assert extraer_sqlstate(excinfo.value) == "42501"


# -----------------------------------------------------------------------------
# Solicitudes
# -----------------------------------------------------------------------------


def _solicitud(nombre: str = "Autos del Llano") -> SolicitudNueva:
    return SolicitudNueva(nombre_organizacion=nombre, nombre_contacto="Luis Prueba", sedes=3)


async def test_la_solicitud_lleva_el_correo_de_la_cuenta(cuentas: Cuentas) -> None:
    cuenta = await cuentas.nueva()

    async with sesion_rls(cuenta) as s:
        estado = await service.solicitar(s, cuenta, _solicitud())

    assert estado.solicitud is not None
    assert estado.solicitud.estado is EstadoSolicitud.PENDIENTE

    async with sesion_servicio() as s:
        email = await s.scalar(
            text("select email from public.solicitudes_organizacion where id = :id"),
            {"id": estado.solicitud.id},
        )
    assert email == cuenta.email


async def test_una_solicitud_directa_no_se_puede_falsear(cuentas: Cuentas) -> None:
    """Escrita a mano contra la tabla, como permitiría la API de datos: el
    correo, el estado y la organización los pone la base."""
    cuenta, otra = await cuentas.nueva(), await cuentas.nueva()

    async with sesion_rls(cuenta) as s:
        await s.execute(
            text("""
                insert into public.solicitudes_organizacion
                  (cuenta_id, email, nombre_contacto, nombre_organizacion, estado)
                values (:c, 'otro@example.com', 'Falsa', 'Falsa', 'atendida')
            """),
            {"c": cuenta.id},
        )
        fila = (
            await s.execute(text("select email, estado from public.solicitudes_organizacion"))
        ).one()

    assert fila.email == cuenta.email
    assert fila.estado == "pendiente"

    # Ni a nombre de otra cuenta.
    with pytest.raises(DBAPIError) as excinfo:
        async with sesion_rls(cuenta) as s:
            await s.execute(
                text("""
                    insert into public.solicitudes_organizacion
                      (cuenta_id, email, nombre_contacto, nombre_organizacion)
                    values (:o, '', 'Ajena', 'Ajena')
                """),
                {"o": otra.id},
            )
    assert extraer_sqlstate(excinfo.value) == "42501"


async def test_cada_cuenta_ve_solo_sus_solicitudes(cuentas: Cuentas) -> None:
    una, otra = await cuentas.nueva(), await cuentas.nueva()
    async with sesion_rls(una) as s:
        await service.solicitar(s, una, _solicitud())

    async with sesion_rls(otra) as s:
        ajenas = await s.scalar(text("select count(*) from public.solicitudes_organizacion"))
        estado = await service.estado_cuenta(s, otra)

    assert ajenas == 0
    assert estado.solicitud is None


async def test_una_pendiente_por_cuenta(cuentas: Cuentas) -> None:
    cuenta = await cuentas.nueva()
    async with sesion_rls(cuenta) as s:
        await service.solicitar(s, cuenta, _solicitud())

    with pytest.raises(ErrorConflicto, match="pendiente"):
        async with sesion_rls(cuenta) as s:
            await service.solicitar(s, cuenta, _solicitud("Otra"))


async def test_quien_ya_tiene_organizacion_no_solicita_otra(cuentas: Cuentas) -> None:
    cuenta = await cuentas.nueva()
    async with sesion_rls(cuenta) as s:
        await service.crear_propia(s, cuenta, _nueva_organizacion("Ya Tengo"))

    with pytest.raises(ErrorConflicto):
        async with sesion_rls(cuenta) as s:
            await service.solicitar(s, cuenta, _solicitud())

    # Tampoco escribiendo directo: la política lo impide aunque se salte el servicio.
    with pytest.raises(DBAPIError) as excinfo:
        async with sesion_rls(cuenta) as s:
            await s.execute(
                text("""
                    insert into public.solicitudes_organizacion
                      (cuenta_id, email, nombre_contacto, nombre_organizacion)
                    values (:c, '', 'Yo', 'Otra')
                """),
                {"c": cuenta.id},
            )
    assert extraer_sqlstate(excinfo.value) == "42501"


async def test_crearla_uno_mismo_atiende_la_solicitud_pendiente(cuentas: Cuentas) -> None:
    cuenta = await cuentas.nueva()
    async with sesion_rls(cuenta) as s:
        await service.solicitar(s, cuenta, _solicitud())
    async with sesion_rls(cuenta) as s:
        estado = await service.crear_propia(s, cuenta, _nueva_organizacion("Al Final Yo"))

    assert estado.solicitud is not None
    assert estado.solicitud.estado is EstadoSolicitud.ATENDIDA


async def test_el_equipo_atiende_la_solicitud_para_esa_cuenta(cuentas: Cuentas) -> None:
    cuenta = await cuentas.nueva()
    async with sesion_rls(cuenta) as s:
        pedida = await service.solicitar(s, cuenta, _solicitud("Autos del Llano"))
    assert pedida.solicitud is not None

    hecha = await alta.atender(str(pedida.solicitud.id)[:8], sede="Llano Centro", moneda="cop")

    assert hecha.email == cuenta.email
    async with sesion_rls(cuenta) as s:
        estado = await service.estado_cuenta(s, cuenta)

    assert estado.organizacion is not None
    assert estado.organizacion.organizacion_nombre == "Autos del Llano"
    assert estado.organizacion.taller_nombre == "Llano Centro"
    assert estado.organizacion.rol is Rol.ADMIN_TALLER
    assert estado.solicitud is not None
    assert estado.solicitud.estado is EstadoSolicitud.ATENDIDA

    with pytest.raises(ErrorConflicto, match="atendida"):
        await alta.atender(str(pedida.solicitud.id))


async def test_descartar_permite_volver_a_pedirlo(cuentas: Cuentas) -> None:
    cuenta = await cuentas.nueva()
    async with sesion_rls(cuenta) as s:
        pedida = await service.solicitar(s, cuenta, _solicitud())
    assert pedida.solicitud is not None

    await alta.descartar(str(pedida.solicitud.id))

    async with sesion_rls(cuenta) as s:
        otra = await service.solicitar(s, cuenta, _solicitud("Segundo intento"))
    assert otra.solicitud is not None
    assert otra.solicitud.estado is EstadoSolicitud.PENDIENTE
