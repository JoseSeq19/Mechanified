"""Endpoints de adjuntos.

El listado y el alta cuelgan de la orden, porque un archivo no existe fuera de
una; el borrado va por el identificador del adjunto, que ya es único.

Dos ausencias a propósito:

- **No hay PATCH.** La tabla `adjuntos` solo tiene políticas de SELECT, INSERT y
  DELETE: la evidencia no se corrige, se borra y se vuelve a subir. Exponer una
  edición que RLS va a rechazar sería ofrecer un botón que no funciona.
- **No hay subida ni descarga por esta API.** El archivo va directo al bucket
  con la sesión de Supabase de quien lo sube, y se lee con una URL firmada que
  el propio navegador pide. Ver el docstring de `schemas.py`.

Los cuatro roles pueden documentar: el asesor hace las fotos de recepción, el
técnico las del diagnóstico, repuestos la factura de una pieza. Es lo mismo que
dice la política `adjuntos_insert`.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import sesion_usuario
from app.core.roles import Rol
from app.core.security import UsuarioAutenticado, usuario_actual
from app.modules.adjuntos import service
from app.modules.adjuntos.models import Adjunto
from app.modules.adjuntos.schemas import AdjuntoRegistrar, AdjuntoRespuesta

router = APIRouter(tags=["adjuntos"])


def _respuesta(a: Adjunto, usuario: UsuarioAutenticado) -> AdjuntoRespuesta:
    return AdjuntoRespuesta(
        id=a.id,
        orden_id=a.orden_id,
        contexto=a.contexto,
        contexto_etiqueta=a.contexto.etiqueta,
        ruta_storage=a.ruta_storage,
        nombre_archivo=a.nombre_archivo,
        mime=a.mime,
        tamano_bytes=a.tamano_bytes,
        descripcion=a.descripcion,
        autor_nombre=a.autor.nombre_completo if a.autor else None,
        # Se calcula aquí para que la interfaz no tenga que repetir la regla de
        # la política de borrado y acabe mostrando un botón que da 403.
        puede_borrar=usuario.rol is Rol.ADMIN_TALLER or a.subido_por == usuario.id,
        creado_en=a.creado_en,
    )


@router.get(
    "/ordenes/{orden_id}/adjuntos",
    response_model=list[AdjuntoRespuesta],
    summary="Archivos de la orden",
    description=(
        "Devuelve los metadatos, no los archivos. Cada fila trae su "
        "`ruta_storage`, que es con lo que el cliente pide al bucket una URL "
        "firmada para mostrarla."
    ),
)
async def listar_adjuntos(
    orden_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    usuario: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> list[AdjuntoRespuesta]:
    return [_respuesta(a, usuario) for a in await service.listar(sesion, orden_id)]


@router.post(
    "/ordenes/{orden_id}/adjuntos",
    response_model=AdjuntoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un archivo ya subido al bucket",
    description=(
        "Se llama **después** de subir el archivo a `mch-evidencias`. La ruta "
        "tiene que seguir la convención `{taller_id}/{orden_id}/{archivo}`: es "
        "lo que ata el objeto del bucket a esta orden y a este taller."
    ),
)
async def registrar_adjunto(
    orden_id: UUID,
    datos: AdjuntoRegistrar,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    usuario: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> AdjuntoRespuesta:
    return _respuesta(await service.registrar(sesion, orden_id, datos, usuario), usuario)


@router.delete(
    "/adjuntos/{adjunto_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar un archivo de la orden",
    description=(
        "Solo quien lo subió o la administración del taller. Borra el registro; "
        "el objeto del bucket lo borra después el cliente, que es quien tiene "
        "sesión en Storage."
    ),
)
async def borrar_adjunto(
    adjunto_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> None:
    await service.eliminar(sesion, adjunto_id)
