"""Alta, baja y cambios de la gente del taller.

Dos reglas gobiernan este módulo, y las dos existen para evitar dejar un taller
sin quien lo administre o sin historial:

  1. **A la gente se le da de baja, no se le borra.** Órdenes, presupuestos,
     controles de calidad y bitácora apuntan al perfil con `on delete set null`:
     borrar a alguien no rompería nada visible, simplemente evaporaría la autoría
     de todo lo que hizo. Por eso no hay endpoint de borrado; hay `activo`.

  2. **El último administrador activo no se queda sin serlo.** Ni bajándose el
     rol a sí mismo, ni desactivándose, ni de la mano de otro. Sin esto, un clic
     desafortunado deja un taller donde nadie puede volver a dar de alta a nadie,
     y la única salida es entrar por Supabase.

Sobre el alta: la cuenta se crea primero en Auth y el perfil después. Si el
perfil falla, se deshace la cuenta —la compensación está abajo, en `crear`—,
porque una cuenta sin perfil es un usuario que puede autenticarse y que, al no
tener claims de taller, chocará contra un "no autorizado" en todo lo que intente.
"""

import logging
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ErrorConflicto,
    ErrorNoEncontrado,
    ErrorPermiso,
    ErrorValidacion,
    extraer_sqlstate,
)
from app.core.roles import Rol
from app.core.security import UsuarioAutenticado
from app.modules.usuarios.cuentas import AdministradorDeCuentas, generar_clave
from app.modules.usuarios.models import Perfil
from app.modules.usuarios.schemas import UsuarioCrear, UsuarioEditar

_log = logging.getLogger(__name__)


async def listar(
    sesion: AsyncSession,
    *,
    roles: Sequence[Rol] | None = None,
    incluir_inactivos: bool = False,
) -> list[Perfil]:
    consulta = select(Perfil).order_by(Perfil.activo.desc(), Perfil.nombre_completo)
    if roles:
        consulta = consulta.where(Perfil.rol.in_(list(roles)))
    if not incluir_inactivos:
        consulta = consulta.where(Perfil.activo.is_(True))
    return list((await sesion.scalars(consulta)).all())


async def obtener(sesion: AsyncSession, perfil_id: UUID) -> Perfil:
    perfil = await sesion.scalar(
        select(Perfil).where(Perfil.id == perfil_id).execution_options(populate_existing=True)
    )
    if perfil is None:
        raise ErrorNoEncontrado("Esa persona no está en tu taller.")
    return perfil


async def crear(
    sesion: AsyncSession,
    datos: UsuarioCrear,
    usuario: UsuarioAutenticado,
    cuentas: AdministradorDeCuentas,
) -> tuple[Perfil, str]:
    """Crea la cuenta de acceso y su perfil. Devuelve la clave temporal."""
    correo = datos.email.strip().lower()
    clave = generar_clave()

    cuenta_id = await cuentas.crear(correo, clave)

    try:
        perfil = Perfil(
            id=cuenta_id,
            taller_id=usuario.taller_id,
            nombre_completo=datos.nombre_completo,
            email=correo,
            telefono=datos.telefono,
            rol=datos.rol,
        )
        sesion.add(perfil)
        await _guardar(sesion)
    except Exception:
        # Compensación: sin perfil, esa cuenta solo sirve para chocar contra un
        # "no autorizado", y además bloquearía el correo para un segundo intento.
        _log.warning("Perfil fallido para %s; se deshace la cuenta %s", correo, cuenta_id)
        await cuentas.borrar(cuenta_id)
        raise

    return await obtener(sesion, cuenta_id), clave


async def actualizar(
    sesion: AsyncSession, perfil_id: UUID, datos: UsuarioEditar, usuario: UsuarioAutenticado
) -> Perfil:
    perfil = await obtener(sesion, perfil_id)
    cambios = datos.model_dump(exclude_unset=True)

    propio = perfil.id == usuario.id
    if propio and "rol" in cambios and cambios["rol"] != perfil.rol:
        raise ErrorValidacion(
            "No puedes cambiarte el rol a ti mismo. Pídeselo a otro administrador."
        )
    if propio and cambios.get("activo") is False:
        raise ErrorValidacion("No puedes darte de baja a ti mismo.")

    pierde_admin = perfil.rol is Rol.ADMIN_TALLER and (
        cambios.get("activo") is False
        or ("rol" in cambios and cambios["rol"] is not Rol.ADMIN_TALLER)
    )
    if pierde_admin and await _administradores_activos(sesion) <= 1:
        raise ErrorConflicto(
            "Es el único administrador activo del taller. Nombra a otro antes de cambiarlo, "
            "o nadie podrá volver a dar de alta a nadie."
        )

    for campo, valor in cambios.items():
        setattr(perfil, campo, valor)

    await _guardar(sesion)
    return await obtener(sesion, perfil_id)


async def restablecer_clave(
    sesion: AsyncSession, perfil_id: UUID, cuentas: AdministradorDeCuentas
) -> str:
    """Genera una contraseña nueva para quien perdió la suya.

    Existe porque el proyecto no manda correos de recuperación: quien olvida su
    contraseña se lo dice a su administrador, que le da una nueva en el momento.
    """
    perfil = await obtener(sesion, perfil_id)
    clave = generar_clave()
    await cuentas.cambiar_clave(perfil.id, clave)
    return clave


async def cambiar_correo(
    sesion: AsyncSession, perfil_id: UUID, correo: str, cuentas: AdministradorDeCuentas
) -> Perfil:
    """Cambia la dirección con la que entra, en la cuenta y en el perfil.

    Las dos partes, o ninguna: si se cambiara solo en Auth, la pantalla de
    personal seguiría mostrando la vieja; si solo aquí, la persona entraría con
    una dirección que la aplicación no reconoce.
    """
    perfil = await obtener(sesion, perfil_id)
    nuevo = correo.strip().lower()
    if nuevo == (perfil.email or "").lower():
        return perfil

    await cuentas.cambiar_correo(perfil.id, nuevo)

    anterior = perfil.email
    try:
        perfil.email = nuevo
        await _guardar(sesion)
    except Exception:
        # Se devuelve la cuenta a su correo anterior: dejarla cambiada mientras
        # el perfil dice otra cosa es peor que no haber cambiado nada.
        if anterior:
            await cuentas.cambiar_correo(perfil.id, anterior)
        raise

    return await obtener(sesion, perfil_id)


async def _administradores_activos(sesion: AsyncSession) -> int:
    """Cuántos administradores activos quedan. RLS ya acota al propio taller."""
    return (
        await sesion.scalar(
            select(func.count())
            .select_from(Perfil)
            .where(Perfil.rol == Rol.ADMIN_TALLER, Perfil.activo.is_(True))
        )
    ) or 0


async def _guardar(sesion: AsyncSession) -> None:
    try:
        await sesion.flush()
    except (IntegrityError, DBAPIError) as exc:
        codigo = extraer_sqlstate(exc)
        if codigo == "23505":
            raise ErrorConflicto("Ya hay alguien registrado con ese correo.") from exc
        if codigo == "23514":
            # Texto redactado por los CHECK de la tabla (nombre demasiado corto).
            raise ErrorValidacion(str(exc).strip().splitlines()[0]) from exc
        if codigo == "42501":
            raise ErrorPermiso(
                "Solo la administración del taller puede gestionar personal."
            ) from exc
        raise
