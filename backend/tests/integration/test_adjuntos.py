"""Adjuntos contra la base real, con RLS activo.

Aquí se prueban las dos barreras que separan un archivo de otro taller: la
política de la tabla, que filtra los metadatos, y la convención de la ruta, que
es lo que ata el objeto del bucket a una orden concreta. La segunda no la
comprueba ningún trigger más allá de la primera carpeta, así que si esta prueba
desaparece, nada avisa de que una foto puede colgarse de la orden equivocada.

El bucket no se toca: estas pruebas son de los metadatos. Subir y borrar el
objeto es cosa del cliente, que habla con Storage con su propia sesión.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database import sesion_rls, sesion_servicio
from app.core.exceptions import (
    ErrorConflicto,
    ErrorNoEncontrado,
    ErrorPermiso,
    ErrorValidacion,
)
from app.core.roles import Rol
from app.core.security import UsuarioAutenticado
from app.modules.adjuntos import service
from app.modules.adjuntos.models import ContextoAdjunto
from app.modules.adjuntos.schemas import AdjuntoRegistrar
from app.modules.clientes import service as srv_clientes
from app.modules.clientes.schemas import ClienteCrear
from app.modules.ordenes import service as srv_ordenes
from app.modules.ordenes.estados import EstadoOrden as E
from app.modules.ordenes.schemas import CambioEstado, OrdenCrear
from app.modules.vehiculos import service as srv_vehiculos
from app.modules.vehiculos.schemas import VehiculoCrear

pytestmark = pytest.mark.integration

#: El camino completo del taller, de la recepción a la entrega.
HASTA_ENTREGA = (
    E.EN_DIAGNOSTICO,
    E.PRESUPUESTO_PENDIENTE,
    E.APROBADO,
    E.EN_REPARACION,
    E.CONTROL_CALIDAD,
    E.LISTO_PARA_ENTREGA,
    E.ENTREGADO,
)

_ALTA_CUENTA = """
    insert into auth.users (
      instance_id, id, aud, role, email, encrypted_password,
      email_confirmed_at, created_at, updated_at,
      raw_app_meta_data, raw_user_meta_data, is_super_admin
    )
    values (
      '00000000-0000-0000-0000-000000000000',
      gen_random_uuid(), 'authenticated', 'authenticated', :correo, 'sin-uso',
      now(), now(), now(),
      '{"provider":"email","providers":["email"]}'::jsonb, '{}'::jsonb, false
    )
    returning id
"""


def _usuario(taller_id: UUID, rol: Rol = Rol.TECNICO, id: UUID | None = None) -> UsuarioAutenticado:
    return UsuarioAutenticado(id=id or uuid4(), taller_id=taller_id, rol=rol)


@dataclass
class Escenario:
    taller_a: UUID
    taller_b: UUID
    orden_a: UUID
    orden_b: UUID
    #: Perfiles de verdad: `adjuntos.subido_por` apunta a `perfiles`, y la
    #: política de borrado compara esa columna con `auth.uid()`. Sin cuentas
    #: reales no se puede probar quién puede borrar qué.
    tecnico_a: UUID
    otro_tecnico_a: UUID

    def ruta(self, orden_id: UUID | None = None, archivo: str | None = None) -> str:
        return (
            f"{self.taller_a}/{orden_id or self.orden_a}/{archivo or f'{uuid4().hex}-frontal.jpg'}"
        )


def _datos(ruta: str, **extra: object) -> AdjuntoRegistrar:
    base = {
        "ruta_storage": ruta,
        "nombre_archivo": "frontal.jpg",
        "mime": "image/jpeg",
        "tamano_bytes": 120_000,
    }
    return AdjuntoRegistrar(**{**base, **extra})


async def _perfil(taller_id: UUID, nombre: str, rol: Rol) -> UUID:
    """Cuenta en Auth y perfil en el taller, por la vía de sistema."""
    async with sesion_servicio() as s:
        cuenta = (
            await s.execute(text(_ALTA_CUENTA), {"correo": f"adj.{uuid4().hex[:10]}@example.com"})
        ).scalar_one()
        await s.execute(
            text("""
                insert into public.perfiles (id, taller_id, nombre_completo, rol)
                values (:id, :taller, :nombre, :rol)
            """),
            {"id": cuenta, "taller": taller_id, "nombre": nombre, "rol": rol.value},
        )
    return UUID(str(cuenta))


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
                motivo_ingreso="Revisión general antes de viaje",
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
                values ('Adj A ' || :sfx, 'adj-a-' || :sfx, 'ADA'),
                       ('Adj B ' || :sfx, 'adj-b-' || :sfx, 'ADB')
                returning id
            """),
            {"sfx": sfx},
        )
        ta, tb = (r[0] for r in filas.fetchall())

    yield Escenario(
        taller_a=ta,
        taller_b=tb,
        orden_a=await _montar_orden(ta, "AD123AA"),
        orden_b=await _montar_orden(tb, "AD456BB"),
        tecnico_a=await _perfil(ta, "Quien sube", Rol.TECNICO),
        otro_tecnico_a=await _perfil(ta, "Quien no subió", Rol.TECNICO),
    )

    async with sesion_servicio() as s:
        # Las cuentas de Auth cuelgan en cascada de nada, así que se borran
        # aparte; los perfiles sí caen con el taller.
        await s.execute(
            text("delete from auth.users where email like 'adj.%@example.com'"),
        )
        await s.execute(text("delete from public.talleres where id = any(:ids)"), {"ids": [ta, tb]})


# -----------------------------------------------------------------------------
# Alta
# -----------------------------------------------------------------------------


async def test_registrar_toma_el_taller_de_la_orden(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a, id=escenario.tecnico_a)
    async with sesion_rls(u) as s:
        a = await service.registrar(s, escenario.orden_a, _datos(escenario.ruta()), u)

    assert a.taller_id == escenario.taller_a
    assert a.orden_id == escenario.orden_a
    assert a.contexto is ContextoAdjunto.INGRESO
    assert a.subido_por == escenario.tecnico_a
    assert a.autor is not None and a.autor.nombre_completo == "Quien sube"


async def test_no_se_registra_en_una_orden_de_otro_taller(escenario: Escenario) -> None:
    """La orden ajena es invisible, así que ni se llega a validar la ruta."""
    u = _usuario(escenario.taller_a, id=escenario.tecnico_a)
    ruta = f"{escenario.taller_a}/{escenario.orden_b}/{uuid4().hex}-frontal.jpg"

    async with sesion_rls(u) as s:
        with pytest.raises(ErrorNoEncontrado):
            await service.registrar(s, escenario.orden_b, _datos(ruta), u)


async def test_no_se_registra_la_ruta_de_otra_orden(escenario: Escenario) -> None:
    """Mismo taller, carpeta de otra orden: la foto aparecería en dos fichas."""
    u = _usuario(escenario.taller_a, id=escenario.tecnico_a)
    otra = await _montar_orden(escenario.taller_a, "AD789CC")

    async with sesion_rls(u) as s:
        with pytest.raises(ErrorValidacion):
            await service.registrar(s, escenario.orden_a, _datos(escenario.ruta(otra)), u)


async def test_la_ruta_de_otro_taller_la_rechaza_tambien_la_base(escenario: Escenario) -> None:
    """Defensa en profundidad: si el servicio no filtrara, el trigger lo haría.

    Se salta la validación del servicio insertando a mano con la sesión del
    taller A, que es lo que haría un cliente que hablara con Postgres por otra
    vía.
    """
    u = _usuario(escenario.taller_a, id=escenario.tecnico_a)
    ruta = f"{escenario.taller_b}/{escenario.orden_a}/{uuid4().hex}-frontal.jpg"

    async with sesion_rls(u) as s:
        with pytest.raises(DBAPIError, match="no comienza con el taller"):
            await s.execute(
                text("""
                    insert into public.adjuntos
                           (taller_id, orden_id, ruta_storage, nombre_archivo)
                    values (:taller, :orden, :ruta, 'frontal.jpg')
                """),
                {"taller": escenario.taller_a, "orden": escenario.orden_a, "ruta": ruta},
            )


async def test_la_misma_ruta_dos_veces_da_conflicto(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a, id=escenario.tecnico_a)
    ruta = escenario.ruta()

    async with sesion_rls(u) as s:
        await service.registrar(s, escenario.orden_a, _datos(ruta), u)

    async with sesion_rls(u) as s:
        with pytest.raises(ErrorConflicto):
            await service.registrar(s, escenario.orden_a, _datos(ruta), u)


async def test_sin_perfil_el_archivo_se_queda_sin_autor(escenario: Escenario) -> None:
    """Pasa con una cuenta de Auth cuyo perfil se borró.

    Perder la autoría es menos grave que perder la evidencia, así que se registra
    igual en vez de fallar.
    """
    u = _usuario(escenario.taller_a)  # id al azar: no hay perfil con ese id

    async with sesion_rls(u) as s:
        a = await service.registrar(s, escenario.orden_a, _datos(escenario.ruta()), u)

    assert a.subido_por is None
    assert a.autor is None


async def test_una_orden_entregada_sigue_admitiendo_evidencia(escenario: Escenario) -> None:
    """Al contrario que las líneas de importe.

    La foto de la entrega se sube justo cuando la orden ya está entregada; si
    esto se bloqueara, el momento más disputado del trabajo sería el único sin
    respaldo.
    """
    admin = _usuario(escenario.taller_a, Rol.ADMIN_TALLER)
    for estado in HASTA_ENTREGA:
        async with sesion_rls(admin) as s:
            await srv_ordenes.cambiar_estado(
                s, escenario.orden_a, CambioEstado(estado=estado), admin
            )

    async with sesion_rls(admin) as s:
        a = await service.registrar(
            s,
            escenario.orden_a,
            _datos(escenario.ruta(), contexto=ContextoAdjunto.ENTREGA),
            admin,
        )

    assert a.contexto is ContextoAdjunto.ENTREGA


# -----------------------------------------------------------------------------
# Lectura
# -----------------------------------------------------------------------------


async def test_un_taller_no_ve_los_adjuntos_del_otro(escenario: Escenario) -> None:
    a = _usuario(escenario.taller_a, id=escenario.tecnico_a)
    async with sesion_rls(a) as s:
        await service.registrar(s, escenario.orden_a, _datos(escenario.ruta()), a)

    b = _usuario(escenario.taller_b)
    async with sesion_rls(b) as s:
        # Sin filtro de taller: lo que reduce la tabla es la política.
        total = await s.scalar(text("select count(*) from public.adjuntos"))
        propios = await service.listar(s, escenario.orden_b)

    assert total == 0
    assert propios == []


async def test_el_listado_va_en_orden_de_subida(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a, id=escenario.tecnico_a)
    async with sesion_rls(u) as s:
        for n in range(3):
            await service.registrar(
                s,
                escenario.orden_a,
                _datos(escenario.ruta(archivo=f"{uuid4().hex}-foto{n}.jpg"), descripcion=f"{n}"),
                u,
            )

    async with sesion_rls(u) as s:
        adjuntos = await service.listar(s, escenario.orden_a)

    assert [a.descripcion for a in adjuntos] == ["0", "1", "2"]


# -----------------------------------------------------------------------------
# Borrado
# -----------------------------------------------------------------------------


async def test_quien_lo_subio_lo_puede_borrar(escenario: Escenario) -> None:
    u = _usuario(escenario.taller_a, id=escenario.tecnico_a)
    async with sesion_rls(u) as s:
        a = await service.registrar(s, escenario.orden_a, _datos(escenario.ruta()), u)

    async with sesion_rls(u) as s:
        ruta = await service.eliminar(s, a.id)

    assert ruta == a.ruta_storage

    async with sesion_rls(u) as s:
        assert await service.listar(s, escenario.orden_a) == []


async def test_otro_tecnico_no_lo_puede_borrar(escenario: Escenario) -> None:
    """La política solo deja a quien lo subió o a administración.

    RLS no lanza error: deja el DELETE sin filas. El servicio lo traduce a una
    falta de permiso para que no salga como un fallo del servidor.
    """
    quien_subio = _usuario(escenario.taller_a, id=escenario.tecnico_a)
    async with sesion_rls(quien_subio) as s:
        a = await service.registrar(s, escenario.orden_a, _datos(escenario.ruta()), quien_subio)

    otro = _usuario(escenario.taller_a, id=escenario.otro_tecnico_a)
    async with sesion_rls(otro) as s:
        with pytest.raises(ErrorPermiso):
            await service.eliminar(s, a.id)

    async with sesion_rls(quien_subio) as s:
        assert len(await service.listar(s, escenario.orden_a)) == 1


async def test_administracion_borra_lo_de_cualquiera(escenario: Escenario) -> None:
    quien_subio = _usuario(escenario.taller_a, id=escenario.tecnico_a)
    async with sesion_rls(quien_subio) as s:
        a = await service.registrar(s, escenario.orden_a, _datos(escenario.ruta()), quien_subio)

    admin = _usuario(escenario.taller_a, Rol.ADMIN_TALLER)
    async with sesion_rls(admin) as s:
        await service.eliminar(s, a.id)

    async with sesion_rls(admin) as s:
        assert await service.listar(s, escenario.orden_a) == []


async def test_el_otro_taller_no_lo_encuentra_para_borrarlo(escenario: Escenario) -> None:
    a_usuario = _usuario(escenario.taller_a, id=escenario.tecnico_a)
    async with sesion_rls(a_usuario) as s:
        a = await service.registrar(s, escenario.orden_a, _datos(escenario.ruta()), a_usuario)

    b_admin = _usuario(escenario.taller_b, Rol.ADMIN_TALLER)
    async with sesion_rls(b_admin) as s:
        with pytest.raises(ErrorNoEncontrado):
            await service.eliminar(s, a.id)
