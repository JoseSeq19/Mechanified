"""Endpoints de órdenes de servicio.

El cambio de estado tiene ruta propia (`POST /ordenes/{id}/estado`) en vez de
ser un campo del PATCH. Es una acción con reglas, autorización por rol y rastro
en la bitácora; mezclarla con la edición del kilometraje borraría esa distinción
y haría imposible pedir un comentario solo cuando hace falta.

Esa ruta no restringe roles por sí misma: quién puede hacer *cada* transición lo
decide la máquina de estados, porque no es lo mismo pasar a diagnóstico que
entregar el vehículo.
"""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import sesion_usuario
from app.core.permissions import recepcion, taller
from app.core.security import UsuarioAutenticado, usuario_actual
from app.modules.ordenes import estados as maquina
from app.modules.ordenes import service
from app.modules.ordenes.estados import ORDEN_TABLERO, TERMINALES, EstadoOrden
from app.modules.ordenes.models import OrdenEvento, OrdenServicio
from app.modules.ordenes.schemas import (
    CambioEstado,
    ColumnaTablero,
    EventoRespuesta,
    OrdenCrear,
    OrdenEditar,
    OrdenRespuesta,
    OrdenResumen,
    ResumenTablero,
)
from app.shared.paginacion import Pagina, ParametrosPagina, parametros_pagina

router = APIRouter(prefix="/ordenes", tags=["órdenes"])


def _descripcion_vehiculo(o: OrdenServicio) -> str:
    partes = [o.vehiculo.marca, o.vehiculo.modelo]
    if o.vehiculo.anio:
        partes.append(str(o.vehiculo.anio))
    return " ".join(partes)


def _campos_resumen(o: OrdenServicio) -> dict[str, Any]:
    return {
        "id": o.id,
        "folio": o.folio,
        "estado": o.estado,
        "estado_etiqueta": o.estado.etiqueta,
        "cliente_id": o.cliente_id,
        "cliente_nombre": o.cliente.nombre,
        "vehiculo_id": o.vehiculo_id,
        "vehiculo_placa": o.vehiculo.placa,
        "vehiculo_descripcion": _descripcion_vehiculo(o),
        "tecnico_nombre": o.tecnico.nombre_completo if o.tecnico else None,
        "asesor_nombre": o.asesor.nombre_completo if o.asesor else None,
        "fecha_ingreso": o.fecha_ingreso,
        "fecha_promesa": o.fecha_promesa,
        "total": o.total,
        "atrasada": bool(
            o.fecha_promesa and o.estado not in TERMINALES and o.fecha_promesa < datetime.now(UTC)
        ),
    }


def _resumen(o: OrdenServicio) -> OrdenResumen:
    return OrdenResumen(**_campos_resumen(o))


def _ficha(o: OrdenServicio, usuario: UsuarioAutenticado) -> OrdenRespuesta:
    return OrdenRespuesta(
        **_campos_resumen(o),
        taller_id=o.taller_id,
        motivo_ingreso=o.motivo_ingreso,
        kilometraje_ingreso=o.kilometraje_ingreso,
        nivel_combustible=o.nivel_combustible,
        inventario_ingreso=o.inventario_ingreso,
        fecha_entrega=o.fecha_entrega,
        total_mano_obra=o.total_mano_obra,
        total_repuestos=o.total_repuestos,
        notas_internas=o.notas_internas,
        motivo_cancelacion=o.motivo_cancelacion,
        creado_en=o.creado_en,
        actualizado_en=o.actualizado_en,
        # La interfaz dibuja un botón por cada uno y no necesita conocer las
        # reglas del flujo ni el rol de quien mira.
        transiciones_posibles=maquina.siguientes(o.estado, usuario.rol),
    )


def _evento(e: OrdenEvento) -> EventoRespuesta:
    return EventoRespuesta(
        id=e.id,
        estado_anterior=e.estado_anterior,
        estado_nuevo=e.estado_nuevo,
        estado_nuevo_etiqueta=e.estado_nuevo.etiqueta,
        usuario_nombre=e.usuario.nombre_completo if e.usuario else None,
        comentario=e.comentario,
        creado_en=e.creado_en,
    )


# -----------------------------------------------------------------------------
# El tablero va antes que /{orden_id}: si no, FastAPI intentaría interpretar
# "tablero" como un UUID y respondería 422.
# -----------------------------------------------------------------------------


@router.get("/tablero", response_model=ResumenTablero, summary="Conteo de órdenes por estado")
async def tablero(
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> ResumenTablero:
    conteo = await service.resumen_tablero(sesion)
    return ResumenTablero(
        columnas=[
            ColumnaTablero(estado=e, etiqueta=e.etiqueta, cantidad=conteo.get(e, 0))
            for e in ORDEN_TABLERO
        ],
        total_abiertas=sum(c for e, c in conteo.items() if e not in TERMINALES),
    )


@router.get("", response_model=Pagina[OrdenResumen], summary="Listar órdenes")
async def listar_ordenes(
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    pagina: Annotated[ParametrosPagina, Depends(parametros_pagina)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
    busqueda: Annotated[
        str | None, Query(description="Folio, placa o nombre del cliente. Mínimo 3 caracteres.")
    ] = None,
    estado: Annotated[
        list[EstadoOrden] | None, Query(description="Filtra por uno o varios estados")
    ] = None,
    tecnico_id: Annotated[UUID | None, Query()] = None,
    cliente_id: Annotated[UUID | None, Query()] = None,
    vehiculo_id: Annotated[UUID | None, Query()] = None,
    incluir_cerradas: Annotated[bool, Query(description="Incluye entregadas y canceladas")] = False,
) -> Pagina[OrdenResumen]:
    items, total = await service.listar(
        sesion,
        busqueda=busqueda,
        estados=estado,
        tecnico_id=tecnico_id,
        cliente_id=cliente_id,
        vehiculo_id=vehiculo_id,
        incluir_cerradas=incluir_cerradas,
        pagina=pagina,
    )
    return Pagina[OrdenResumen](
        items=[_resumen(o) for o in items],
        total=total,
        limite=pagina.limite,
        desplazamiento=pagina.desplazamiento,
    )


@router.get("/{orden_id}", response_model=OrdenRespuesta, summary="Ficha de una orden")
async def obtener_orden(
    orden_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    usuario: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> OrdenRespuesta:
    return _ficha(await service.obtener(sesion, orden_id), usuario)


@router.get(
    "/{orden_id}/eventos",
    response_model=list[EventoRespuesta],
    summary="Bitácora de la orden",
    description="Historial de cambios de estado. Es la fuente de las métricas de tiempo.",
)
async def eventos_orden(
    orden_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> list[EventoRespuesta]:
    return [_evento(e) for e in await service.historial(sesion, orden_id)]


@router.post(
    "",
    response_model=OrdenRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Abrir una orden de servicio",
    description="Nace en estado `recibido`. El folio lo asigna la base de datos.",
)
async def crear_orden(
    datos: OrdenCrear,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    usuario: Annotated[UsuarioAutenticado, Depends(recepcion)],
) -> OrdenRespuesta:
    return _ficha(await service.crear(sesion, datos, usuario), usuario)


@router.patch(
    "/{orden_id}",
    response_model=OrdenRespuesta,
    summary="Editar los datos de una orden",
    description="No cambia el estado: para eso está POST /ordenes/{id}/estado.",
)
async def editar_orden(
    orden_id: UUID,
    datos: OrdenEditar,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    usuario: Annotated[UsuarioAutenticado, Depends(taller)],
) -> OrdenRespuesta:
    return _ficha(await service.actualizar(sesion, orden_id, datos), usuario)


@router.post(
    "/{orden_id}/estado",
    response_model=OrdenRespuesta,
    summary="Mover la orden por el flujo",
    description=(
        "Qué rol puede hacer cada transición lo decide la máquina de estados. "
        "Cancelar exige indicar el motivo en el comentario."
    ),
)
async def cambiar_estado_orden(
    orden_id: UUID,
    cambio: CambioEstado,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    usuario: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> OrdenRespuesta:
    return _ficha(await service.cambiar_estado(sesion, orden_id, cambio, usuario), usuario)
