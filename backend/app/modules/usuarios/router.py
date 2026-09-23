"""Endpoints de la gente del taller.

Leer la lista puede cualquiera con sesión: la ficha de una orden necesita saber
qué técnicos hay para poder asignar uno, y la política RLS de `perfiles` ya la
acota al propio taller. Todo lo demás —dar de alta, cambiar un rol, dar de baja,
restablecer una contraseña— es de administración, igual que en las políticas.

La contraseña temporal viaja en la respuesta del alta y en la del
restablecimiento, y en ningún otro sitio. No se guarda ni se puede volver a
consultar: si se pierde, se genera otra.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import sesion_usuario
from app.core.permissions import solo_admin
from app.core.roles import Rol
from app.core.security import UsuarioAutenticado, usuario_actual
from app.modules.usuarios import service
from app.modules.usuarios.cuentas import AdministradorDeCuentas, administrador_de_cuentas
from app.modules.usuarios.models import Perfil
from app.modules.usuarios.schemas import (
    ClaveTemporal,
    CorreoNuevo,
    UsuarioCreado,
    UsuarioCrear,
    UsuarioEditar,
    UsuarioRespuesta,
)

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


def _ficha(p: Perfil) -> UsuarioRespuesta:
    return UsuarioRespuesta(
        id=p.id,
        nombre_completo=p.nombre_completo,
        email=p.email,
        rol=p.rol,
        rol_etiqueta=p.rol.etiqueta,
        telefono=p.telefono,
        activo=p.activo,
        creado_en=p.creado_en,
    )


@router.get("", response_model=list[UsuarioRespuesta], summary="Gente del taller")
async def listar_usuarios(
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
    rol: Annotated[Rol | None, Query(description="Filtra por rol")] = None,
    incluir_inactivos: Annotated[bool, Query(description="Incluye a quien está de baja")] = False,
) -> list[UsuarioRespuesta]:
    perfiles = await service.listar(
        sesion, roles=[rol] if rol else None, incluir_inactivos=incluir_inactivos
    )
    return [_ficha(p) for p in perfiles]


@router.post(
    "",
    response_model=UsuarioCreado,
    status_code=status.HTTP_201_CREATED,
    summary="Dar de alta a alguien",
    description=(
        "Crea la cuenta de acceso y el perfil de una vez. Devuelve una contraseña "
        "temporal que **solo se muestra aquí**: hay que entregársela a la persona "
        "para que entre y la cambie. Si se pierde, se genera otra."
    ),
)
async def crear_usuario(
    datos: UsuarioCrear,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    usuario: Annotated[UsuarioAutenticado, Depends(solo_admin)],
    cuentas: Annotated[AdministradorDeCuentas, Depends(administrador_de_cuentas)],
) -> UsuarioCreado:
    perfil, clave = await service.crear(sesion, datos, usuario, cuentas)
    return UsuarioCreado(**_ficha(perfil).model_dump(), clave_temporal=clave)


@router.patch(
    "/{perfil_id}",
    response_model=UsuarioRespuesta,
    summary="Cambiar nombre, teléfono, rol o alta/baja",
    description=(
        "Un cambio de rol viaja en el token, así que surte efecto cuando la "
        "persona renueva su sesión: como mucho en una hora, o al volver a entrar. "
        "Dar de baja quita los permisos por el mismo camino."
    ),
)
async def editar_usuario(
    perfil_id: UUID,
    datos: UsuarioEditar,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    usuario: Annotated[UsuarioAutenticado, Depends(solo_admin)],
) -> UsuarioRespuesta:
    return _ficha(await service.actualizar(sesion, perfil_id, datos, usuario))


@router.post(
    "/{perfil_id}/clave",
    response_model=ClaveTemporal,
    summary="Restablecer la contraseña",
    description=(
        "Para quien olvidó la suya. Genera una nueva y la devuelve una sola vez; "
        "la anterior deja de servir en el momento."
    ),
)
async def restablecer_clave(
    perfil_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(solo_admin)],
    cuentas: Annotated[AdministradorDeCuentas, Depends(administrador_de_cuentas)],
) -> ClaveTemporal:
    return ClaveTemporal(clave_temporal=await service.restablecer_clave(sesion, perfil_id, cuentas))


@router.patch(
    "/{perfil_id}/correo",
    response_model=UsuarioRespuesta,
    summary="Cambiar el correo de acceso",
    description="Cambia la dirección en la cuenta y en el perfil, o en ninguna de las dos.",
)
async def cambiar_correo(
    perfil_id: UUID,
    datos: CorreoNuevo,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(solo_admin)],
    cuentas: Annotated[AdministradorDeCuentas, Depends(administrador_de_cuentas)],
) -> UsuarioRespuesta:
    return _ficha(await service.cambiar_correo(sesion, perfil_id, datos.email, cuentas))
