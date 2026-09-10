"""Endpoints de clientes.

El router solo valida entrada, delega en el servicio y serializa. Las reglas
están en `service.py` y, sobre todo, en las políticas RLS.

Sobre los roles de cada ruta: son los mismos que aplican las políticas de
`clientes` en la migración 000300 (lectura para todo el taller, escritura para
asesoría y administración, borrado solo administración). Se declaran aquí para
poder responder un 403 explicando qué rol hace falta, en vez del `42501` seco
que devolvería Postgres.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import sesion_usuario
from app.core.permissions import recepcion, solo_admin
from app.core.security import UsuarioAutenticado, usuario_actual
from app.modules.clientes import service
from app.modules.clientes.schemas import ClienteCrear, ClienteEditar, ClienteRespuesta
from app.shared.paginacion import Pagina, ParametrosPagina, parametros_pagina

router = APIRouter(prefix="/clientes", tags=["clientes"])


@router.get(
    "",
    response_model=Pagina[ClienteRespuesta],
    summary="Listar clientes del taller",
)
async def listar_clientes(
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    pagina: Annotated[ParametrosPagina, Depends(parametros_pagina)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
    busqueda: Annotated[
        str | None,
        Query(description="Busca en nombre, documento, teléfono y correo. Mínimo 3 caracteres."),
    ] = None,
    incluir_inactivos: Annotated[bool, Query(description="Incluye los dados de baja")] = False,
) -> Pagina[ClienteRespuesta]:
    items, total = await service.listar(
        sesion,
        busqueda=busqueda,
        solo_activos=not incluir_inactivos,
        pagina=pagina,
    )
    return Pagina[ClienteRespuesta](
        items=[ClienteRespuesta.model_validate(c) for c in items],
        total=total,
        limite=pagina.limite,
        desplazamiento=pagina.desplazamiento,
    )


@router.get(
    "/{cliente_id}",
    response_model=ClienteRespuesta,
    summary="Consultar un cliente",
)
async def obtener_cliente(
    cliente_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> ClienteRespuesta:
    return ClienteRespuesta.model_validate(await service.obtener(sesion, cliente_id))


@router.post(
    "",
    response_model=ClienteRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un cliente",
)
async def crear_cliente(
    datos: ClienteCrear,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    usuario: Annotated[UsuarioAutenticado, Depends(recepcion)],
) -> ClienteRespuesta:
    return ClienteRespuesta.model_validate(await service.crear(sesion, datos, usuario))


@router.patch(
    "/{cliente_id}",
    response_model=ClienteRespuesta,
    summary="Editar un cliente",
)
async def editar_cliente(
    cliente_id: UUID,
    datos: ClienteEditar,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(recepcion)],
) -> ClienteRespuesta:
    return ClienteRespuesta.model_validate(await service.actualizar(sesion, cliente_id, datos))


@router.delete(
    "/{cliente_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar un cliente sin historial",
    description=(
        "Solo para registros creados por error. Un cliente con vehículos no se "
        "puede borrar: se responde 409 y hay que desactivarlo con PATCH."
    ),
)
async def borrar_cliente(
    cliente_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(solo_admin)],
) -> None:
    await service.eliminar(sesion, cliente_id)
