"""Endpoints del catálogo de repuestos y de las piezas de una orden.

Permisos, los mismos que aplican las políticas RLS de la migración 000600:

  - El **catálogo** lo consulta todo el taller y lo edita repuestos (y
    administración). Es su inventario.
  - Las **piezas de una orden** las puede solicitar también el técnico, que es
    quien descubre que hace falta una pieza con el vehículo abierto. Cambiarles
    el precio o el estado queda para repuestos y asesoría.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import sesion_usuario
from app.core.permissions import inventario, requiere_rol
from app.core.roles import Rol
from app.core.security import UsuarioAutenticado, usuario_actual
from app.modules.repuestos import service
from app.modules.repuestos.models import OrdenRepuesto, Repuesto
from app.modules.repuestos.schemas import (
    ItemCrear,
    ItemEditar,
    ItemRespuesta,
    RepuestoCrear,
    RepuestoEditar,
    RepuestoRespuesta,
    ResumenRepuestos,
)
from app.shared.paginacion import Pagina, ParametrosPagina, parametros_pagina

router = APIRouter(tags=["repuestos"])

#: Quién puede pedir una pieza para una orden.
solicita = requiere_rol(Rol.ADMIN_TALLER, Rol.ENCARGADO_REPUESTOS, Rol.ASESOR_SERVICIO, Rol.TECNICO)
#: Quién puede cambiarle el precio o el estado.
gestiona = requiere_rol(Rol.ADMIN_TALLER, Rol.ENCARGADO_REPUESTOS, Rol.ASESOR_SERVICIO)


def _repuesto(r: Repuesto) -> RepuestoRespuesta:
    return RepuestoRespuesta(
        id=r.id,
        taller_id=r.taller_id,
        sku=r.sku,
        nombre=r.nombre,
        descripcion=r.descripcion,
        categoria=r.categoria,
        unidad=r.unidad,
        costo=r.costo,
        precio_venta=r.precio_venta,
        stock=r.stock,
        stock_minimo=r.stock_minimo,
        bajo_minimo=r.bajo_minimo,
        proveedor=r.proveedor,
        activo=r.activo,
        creado_en=r.creado_en,
        actualizado_en=r.actualizado_en,
    )


def _item(i: OrdenRepuesto) -> ItemRespuesta:
    return ItemRespuesta(
        id=i.id,
        orden_id=i.orden_id,
        repuesto_id=i.repuesto_id,
        sku=i.repuesto.sku if i.repuesto else None,
        descripcion=i.descripcion,
        cantidad=i.cantidad,
        precio_unitario=i.precio_unitario,
        subtotal=i.subtotal,
        estado=i.estado,
        estado_etiqueta=i.estado.etiqueta,
        notas=i.notas,
        solicitante_nombre=i.solicitante.nombre_completo if i.solicitante else None,
        creado_en=i.creado_en,
    )


# -----------------------------------------------------------------------------
# Catálogo
# -----------------------------------------------------------------------------


@router.get("/repuestos", response_model=Pagina[RepuestoRespuesta], summary="Catálogo del taller")
async def listar_catalogo(
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    pagina: Annotated[ParametrosPagina, Depends(parametros_pagina)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
    busqueda: Annotated[
        str | None, Query(description="SKU, nombre o categoría. Mínimo 3 caracteres.")
    ] = None,
    incluir_inactivos: Annotated[bool, Query()] = False,
    solo_bajo_minimo: Annotated[
        bool, Query(description="Solo las piezas que hay que reponer")
    ] = False,
) -> Pagina[RepuestoRespuesta]:
    items, total = await service.listar_catalogo(
        sesion,
        busqueda=busqueda,
        solo_activos=not incluir_inactivos,
        solo_bajo_minimo=solo_bajo_minimo,
        pagina=pagina,
    )
    return Pagina[RepuestoRespuesta](
        items=[_repuesto(r) for r in items],
        total=total,
        limite=pagina.limite,
        desplazamiento=pagina.desplazamiento,
    )


@router.get(
    "/repuestos/{repuesto_id}", response_model=RepuestoRespuesta, summary="Consultar un repuesto"
)
async def obtener_repuesto(
    repuesto_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> RepuestoRespuesta:
    return _repuesto(await service.obtener_repuesto(sesion, repuesto_id))


@router.post(
    "/repuestos",
    response_model=RepuestoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Dar de alta un repuesto",
)
async def crear_repuesto(
    datos: RepuestoCrear,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    usuario: Annotated[UsuarioAutenticado, Depends(inventario)],
) -> RepuestoRespuesta:
    return _repuesto(await service.crear_repuesto(sesion, datos, usuario))


@router.patch(
    "/repuestos/{repuesto_id}", response_model=RepuestoRespuesta, summary="Editar un repuesto"
)
async def editar_repuesto(
    repuesto_id: UUID,
    datos: RepuestoEditar,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(inventario)],
) -> RepuestoRespuesta:
    return _repuesto(await service.actualizar_repuesto(sesion, repuesto_id, datos))


@router.delete(
    "/repuestos/{repuesto_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar un repuesto del catálogo",
    description=(
        "Las órdenes que lo usaron no se rompen: sus líneas conservan la "
        "descripción y el precio que se copiaron al cargarlas."
    ),
)
async def borrar_repuesto(
    repuesto_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(inventario)],
) -> None:
    await service.eliminar_repuesto(sesion, repuesto_id)


# -----------------------------------------------------------------------------
# Piezas de una orden
# -----------------------------------------------------------------------------


@router.get(
    "/ordenes/{orden_id}/repuestos",
    response_model=ResumenRepuestos,
    summary="Piezas cargadas a la orden",
)
async def listar_items(
    orden_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> ResumenRepuestos:
    lineas = await service.listar_items(sesion, orden_id)
    total, pendientes = await service.resumen_items(sesion, orden_id)
    return ResumenRepuestos(lineas=[_item(i) for i in lineas], total=total, pendientes=pendientes)


@router.post(
    "/ordenes/{orden_id}/repuestos",
    response_model=ItemRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Cargar una pieza a la orden",
    description=(
        "Con `repuesto_id` se toman nombre y precio del catálogo y quedan fijos "
        "en la línea. Sin él, hay que indicar `descripcion` y `precio_unitario`: "
        "es la pieza que se compra suelta y no está en el catálogo."
    ),
)
async def agregar_item(
    orden_id: UUID,
    datos: ItemCrear,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    usuario: Annotated[UsuarioAutenticado, Depends(solicita)],
) -> ItemRespuesta:
    return _item(await service.agregar_item(sesion, orden_id, datos, usuario))


@router.patch(
    "/orden-repuestos/{item_id}",
    response_model=ItemRespuesta,
    summary="Editar una pieza de la orden",
)
async def editar_item(
    item_id: UUID,
    datos: ItemEditar,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(gestiona)],
) -> ItemRespuesta:
    return _item(await service.actualizar_item(sesion, item_id, datos))


@router.delete(
    "/orden-repuestos/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar una pieza de la orden",
)
async def borrar_item(
    item_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(gestiona)],
) -> None:
    await service.eliminar_item(sesion, item_id)
