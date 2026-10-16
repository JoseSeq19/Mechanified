"""Alta de un taller nuevo, contra la base real y contra Supabase Auth.

Es la única operación del sistema que escribe en `talleres`, y la que arranca
todo lo demás: si deja el taller a medias —sin administrador, o con un
administrador sin perfil—, no hay ninguna pantalla desde la que arreglarlo.
Por eso lo que más se prueba aquí es lo que pasa cuando falla a mitad de camino.

Las cuentas se crean de verdad en Auth y se borran al terminar. Las direcciones
van bajo `example.com`, que es un dominio reservado que no entrega correo.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.database import sesion_rls, sesion_servicio
from app.core.exceptions import ErrorConflicto
from app.core.roles import Rol
from app.core.security import UsuarioAutenticado
from app.modules.talleres import service as srv_talleres
from app.modules.talleres.alta import crear_taller
from app.modules.talleres.schemas import TallerAlta, TallerEditar
from app.modules.usuarios.cuentas import CuentasSupabase

pytestmark = pytest.mark.integration


class CuentasQueFallan:
    """Doble que no crea ninguna cuenta. Para probar la compensación."""

    async def crear(self, correo: str, clave: str) -> UUID:
        raise RuntimeError("Supabase no responde")

    async def borrar(self, cuenta_id: UUID) -> None: ...

    async def cambiar_clave(self, cuenta_id: UUID, clave: str) -> None: ...

    async def cambiar_correo(self, cuenta_id: UUID, correo: str) -> None: ...


class CuentasFingidas:
    """Doble que inventa identificadores que no existen en `auth.users`.

    Sirve para provocar lo que con el sistema real no ocurre: que el perfil
    falle después de haber creado la cuenta. `perfiles.id` es una llave foránea
    contra Auth, así que un id inventado la rompe.
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
class Rastro:
    """Lo que hay que limpiar al final de cada prueba."""

    sufijo: str
    talleres: list[UUID] = field(default_factory=list)
    cuentas: list[UUID] = field(default_factory=list)

    def datos(self, **extra: object) -> TallerAlta:
        base = {
            "nombre": f"Taller Alta {self.sufijo}",
            "admin_email": f"alta.{uuid4().hex[:10]}@example.com",
            "admin_nombre": "Primera Administradora",
        }
        return TallerAlta(**{**base, **extra})


@pytest_asyncio.fixture
async def rastro() -> AsyncIterator[Rastro]:
    r = Rastro(sufijo=uuid4().hex[:8])
    yield r

    cuentas = CuentasSupabase()
    for cuenta_id in r.cuentas:
        await cuentas.borrar(cuenta_id)
    if r.talleres:
        async with sesion_servicio() as s:
            await s.execute(
                text("delete from public.talleres where id = any(:ids)"), {"ids": r.talleres}
            )


# -----------------------------------------------------------------------------
# Camino normal
# -----------------------------------------------------------------------------


async def test_el_alta_deja_el_taller_listo_para_usarse(rastro: Rastro) -> None:
    datos = rastro.datos(moneda="VES", tarifa_hora_default=Decimal("18.50"), impuesto_pct=16)

    creado = await crear_taller(datos)
    rastro.talleres.append(creado.taller_id)
    rastro.cuentas.append(creado.admin_id)

    assert creado.slug == f"taller-alta-{rastro.sufijo}"
    assert creado.prefijo_orden == "TAL"
    assert creado.clave_temporal  # se muestra una vez y no se guarda en claro

    async with sesion_servicio() as s:
        taller = (
            await s.execute(
                text("""
                    select nombre, slug, moneda, tarifa_hora_default, impuesto_pct, prefijo_orden
                      from public.talleres where id = :id
                """),
                {"id": creado.taller_id},
            )
        ).one()
        perfil = (
            await s.execute(
                text("select taller_id, rol, email, activo from public.perfiles where id = :id"),
                {"id": creado.admin_id},
            )
        ).one()
        secuencia = (
            await s.execute(
                text("select prefijo, valor from public.secuencias_folio where taller_id = :id"),
                {"id": creado.taller_id},
            )
        ).one()

    assert taller.moneda == "VES"
    assert taller.tarifa_hora_default == Decimal("18.50")
    assert taller.impuesto_pct == Decimal("16.00")

    assert perfil.taller_id == creado.taller_id
    assert perfil.rol == Rol.ADMIN_TALLER.value
    assert perfil.email == str(datos.admin_email).lower()
    assert perfil.activo is True

    # La secuencia la crea un trigger al insertar el taller. Sin ella, la
    # primera orden no podría tomar folio.
    assert secuencia.prefijo == "TAL"
    assert secuencia.valor == 0


async def test_el_administrador_puede_configurar_su_taller_de_inmediato(rastro: Rastro) -> None:
    """La prueba de que los claims que tendrá su token sirven para algo.

    Es el primer paso real de quien recibe el alta: entrar y poner su tarifa.
    """
    creado = await crear_taller(rastro.datos())
    rastro.talleres.append(creado.taller_id)
    rastro.cuentas.append(creado.admin_id)

    usuario = UsuarioAutenticado(
        id=creado.admin_id, taller_id=creado.taller_id, rol=Rol.ADMIN_TALLER
    )
    async with sesion_rls(usuario) as s:
        taller = await srv_talleres.actualizar(s, TallerEditar(tarifa_hora_default=Decimal("25")))

    assert taller.tarifa_hora_default == Decimal("25.00")


async def test_el_prefijo_y_el_slug_se_pueden_imponer(rastro: Rastro) -> None:
    slug = f"delta-{rastro.sufijo}"
    creado = await crear_taller(rastro.datos(slug=slug, prefijo_orden="DLT"))
    rastro.talleres.append(creado.taller_id)
    rastro.cuentas.append(creado.admin_id)

    assert creado.slug == slug
    assert creado.prefijo_orden == "DLT"


# -----------------------------------------------------------------------------
# Lo que falla a medias
# -----------------------------------------------------------------------------


async def test_un_slug_ya_usado_no_crea_nada(rastro: Rastro) -> None:
    primero = await crear_taller(rastro.datos())
    rastro.talleres.append(primero.taller_id)
    rastro.cuentas.append(primero.admin_id)

    with pytest.raises(ErrorConflicto, match="--slug"):
        await crear_taller(rastro.datos())

    async with sesion_servicio() as s:
        cuantos = await s.scalar(
            text("select count(*) from public.talleres where slug = :slug"),
            {"slug": primero.slug},
        )

    assert cuantos == 1


async def test_si_no_se_puede_crear_la_cuenta_no_queda_el_taller(rastro: Rastro) -> None:
    """Un taller sin administrador no se arregla desde ninguna pantalla.

    Y además dejaría su identificador ocupado, así que el segundo intento
    fallaría por un motivo que no tiene nada que ver.
    """
    datos = rastro.datos()

    with pytest.raises(RuntimeError):
        await crear_taller(datos, CuentasQueFallan())

    async with sesion_servicio() as s:
        cuantos = await s.scalar(
            text("select count(*) from public.talleres where nombre = :nombre"),
            {"nombre": datos.nombre},
        )

    assert cuantos == 0


async def test_si_falla_el_perfil_se_deshacen_la_cuenta_y_el_taller(rastro: Rastro) -> None:
    cuentas = CuentasFingidas()
    datos = rastro.datos()

    with pytest.raises(Exception, match=r"perfiles|foreign key|llave"):
        await crear_taller(datos, cuentas)

    async with sesion_servicio() as s:
        cuantos = await s.scalar(
            text("select count(*) from public.talleres where nombre = :nombre"),
            {"nombre": datos.nombre},
        )

    assert cuantos == 0
    assert len(cuentas.borradas) == 1
