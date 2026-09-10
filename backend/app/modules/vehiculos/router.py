"""Endpoints de vehículos.

Los roles de cada ruta replican las políticas RLS de la migración 000300:
lectura para todo el taller, alta para asesoría y administración, edición
también para el técnico (registra el kilometraje al recibir), y borrado solo
para administración.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import sesion_usuario
from app.core.permissions import recepcion, solo_admin, taller
from app.core.security import UsuarioAutenticado, usuario_actual
from app.modules.vehiculos import service
from app.modules.vehiculos.models import Vehiculo
from app.modules.vehiculos.schemas import VehiculoCrear, VehiculoEditar, VehiculoRespuesta
from app.shared.paginacion import Pagina, ParametrosPagina, parametros_pagina

router = APIRouter(prefix="/vehiculos", tags=["vehículos"])


def _a_respuesta(v: Vehiculo) -> VehiculoRespuesta:
    """Añade el nombre del propietario, que vive en la relación cargada."""
    return VehiculoRespuesta.model_validate(v).model_copy(
        update={"cliente_nombre": v.cliente.nombre}
    )


@router.get("", response_model=Pagina[VehiculoRespuesta], summary="Listar vehículos del taller")
async def listar_vehiculos(
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    pagina: Annotated[ParametrosPagina, Depends(parametros_pagina)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
    busqueda: Annotated[
        str | None,
        Query(description="Busca en placa, VIN, marca y modelo. Mínimo 3 caracteres."),
    ] = None,
    cliente_id: Annotated[UUID | None, Query(description="Solo los de este cliente")] = None,
    incluir_inactivos: Annotated[bool, Query(description="Incluye los dados de baja")] = False,
) -> Pagina[VehiculoRespuesta]:
    items, total = await service.listar(
        sesion,
        busqueda=busqueda,
        cliente_id=cliente_id,
        solo_activos=not incluir_inactivos,
        pagina=pagina,
    )
    return Pagina[VehiculoRespuesta](
        items=[_a_respuesta(v) for v in items],
        total=total,
        limite=pagina.limite,
        desplazamiento=pagina.desplazamiento,
    )


@router.get("/{vehiculo_id}", response_model=VehiculoRespuesta, summary="Consultar un vehículo")
async def obtener_vehiculo(
    vehiculo_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> VehiculoRespuesta:
    return _a_respuesta(await service.obtener(sesion, vehiculo_id))


@router.post(
    "",
    response_model=VehiculoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un vehículo",
)
async def crear_vehiculo(
    datos: VehiculoCrear,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    usuario: Annotated[UsuarioAutenticado, Depends(recepcion)],
) -> VehiculoRespuesta:
    return _a_respuesta(await service.crear(sesion, datos, usuario))


@router.patch(
    "/{vehiculo_id}",
    response_model=VehiculoRespuesta,
    summary="Editar un vehículo",
    description="El técnico puede editarlo para registrar el kilometraje al recibirlo.",
)
async def editar_vehiculo(
    vehiculo_id: UUID,
    datos: VehiculoEditar,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(taller)],
) -> VehiculoRespuesta:
    return _a_respuesta(await service.actualizar(sesion, vehiculo_id, datos))


@router.delete(
    "/{vehiculo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar un vehículo sin historial",
    description=(
        "Solo para registros creados por error. Un vehículo con órdenes de "
        "servicio no se puede borrar: se responde 409 y hay que desactivarlo."
    ),
)
async def borrar_vehiculo(
    vehiculo_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(solo_admin)],
) -> None:
    await service.eliminar(sesion, vehiculo_id)
