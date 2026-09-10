"""Consulta de los usuarios del taller.

Solo lectura, y a propósito: dar de alta a alguien exige crear también su
usuario en Supabase Auth, y eso pertenece al módulo completo de usuarios, que
todavía no está. Lo que hay aquí es lo mínimo para poder asignar un técnico o un
asesor a una orden sin tener que teclear su UUID.

La política RLS de `perfiles` ya limita lo que se ve al propio taller.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import sesion_usuario
from app.core.roles import Rol
from app.core.security import UsuarioAutenticado, usuario_actual
from app.modules.usuarios.models import Perfil
from app.modules.usuarios.schemas import UsuarioRespuesta

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.get("", response_model=list[UsuarioRespuesta], summary="Gente del taller")
async def listar_usuarios(
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
    rol: Annotated[Rol | None, Query(description="Filtra por rol")] = None,
    incluir_inactivos: Annotated[bool, Query()] = False,
) -> list[UsuarioRespuesta]:
    consulta = select(Perfil).order_by(Perfil.nombre_completo)
    if rol is not None:
        consulta = consulta.where(Perfil.rol == rol)
    if not incluir_inactivos:
        consulta = consulta.where(Perfil.activo.is_(True))

    perfiles = (await sesion.scalars(consulta)).all()
    return [
        UsuarioRespuesta(
            id=p.id,
            nombre_completo=p.nombre_completo,
            rol=p.rol,
            rol_etiqueta=p.rol.etiqueta,
            telefono=p.telefono,
            activo=p.activo,
        )
        for p in perfiles
    ]
