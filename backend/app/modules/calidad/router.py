"""Endpoints del checklist configurable y de los controles de calidad.

Permisos, los mismos que aplican las políticas RLS de la migración 000800:

  - Las **plantillas** las consulta todo el taller, pero solo administración las
    define: son el criterio de calidad del taller, no algo que cada técnico
    ajuste a su gusto.
  - Los **controles** los ejecutan administración, asesoría y técnicos.

Cerrar un control mueve la orden (aprobado → listo para entrega, rechazado →
de vuelta a reparación). Ver `service.cerrar_control`.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import sesion_usuario
from app.core.permissions import solo_admin, taller
from app.core.security import UsuarioAutenticado, usuario_actual
from app.modules.calidad import service
from app.modules.calidad.models import Control, Plantilla, ResultadoControl
from app.modules.calidad.schemas import (
    CerrarControl,
    ControlEditar,
    ControlIniciar,
    ControlRespuesta,
    PlantillaCrear,
    PlantillaEditar,
    PlantillaRespuesta,
    PuntoCrear,
    PuntoEditar,
    PuntoRespuesta,
    RespuestaControl,
    RespuestaEditar,
)

router = APIRouter(tags=["calidad"])


def _plantilla(p: Plantilla) -> PlantillaRespuesta:
    return PlantillaRespuesta(
        id=p.id,
        taller_id=p.taller_id,
        nombre=p.nombre,
        descripcion=p.descripcion,
        activo=p.activo,
        puntos=[PuntoRespuesta.model_validate(x) for x in p.puntos],
        obligatorios=sum(1 for x in p.puntos if x.obligatorio),
        creado_en=p.creado_en,
    )


def _control(c: Control) -> ControlRespuesta:
    return ControlRespuesta(
        id=c.id,
        taller_id=c.taller_id,
        orden_id=c.orden_id,
        plantilla_id=c.plantilla_id,
        inspector_id=c.inspector_id,
        inspector_nombre=c.inspector.nombre_completo if c.inspector else None,
        resultado=c.resultado,
        resultado_etiqueta=ResultadoControl(c.resultado).etiqueta,
        observaciones=c.observaciones,
        respuestas=[
            RespuestaControl(
                id=r.id,
                control_id=r.control_id,
                item_id=r.item_id,
                descripcion=r.descripcion,
                resultado=r.resultado,
                resultado_etiqueta=r.resultado.etiqueta,
                obligatorio=bool(r.item and r.item.obligatorio),
                comentario=r.comentario,
                evidencia_url=r.evidencia_url,
                orden_visual=r.orden_visual,
            )
            for r in c.respuestas
        ],
        pendientes=len(service.pendientes(c)),
        creado_en=c.creado_en,
        cerrado_en=c.cerrado_en,
    )


# -----------------------------------------------------------------------------
# Plantillas
# -----------------------------------------------------------------------------


@router.get(
    "/calidad/plantillas",
    response_model=list[PlantillaRespuesta],
    summary="Plantillas de checklist del taller",
)
async def listar_plantillas(
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
    incluir_inactivas: Annotated[bool, Query()] = False,
) -> list[PlantillaRespuesta]:
    return [
        _plantilla(p)
        for p in await service.listar_plantillas(sesion, solo_activas=not incluir_inactivas)
    ]


@router.get(
    "/calidad/plantillas/{plantilla_id}",
    response_model=PlantillaRespuesta,
    summary="Consultar una plantilla",
)
async def obtener_plantilla(
    plantilla_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> PlantillaRespuesta:
    return _plantilla(await service.obtener_plantilla(sesion, plantilla_id))


@router.post(
    "/calidad/plantillas",
    response_model=PlantillaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una plantilla",
    description="Se crea con sus puntos en la misma petición.",
)
async def crear_plantilla(
    datos: PlantillaCrear,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    usuario: Annotated[UsuarioAutenticado, Depends(solo_admin)],
) -> PlantillaRespuesta:
    return _plantilla(await service.crear_plantilla(sesion, datos, usuario))


@router.patch(
    "/calidad/plantillas/{plantilla_id}",
    response_model=PlantillaRespuesta,
    summary="Editar una plantilla",
)
async def editar_plantilla(
    plantilla_id: UUID,
    datos: PlantillaEditar,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(solo_admin)],
) -> PlantillaRespuesta:
    return _plantilla(await service.actualizar_plantilla(sesion, plantilla_id, datos))


@router.delete(
    "/calidad/plantillas/{plantilla_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar una plantilla",
    description=(
        "Los controles ya hechos conservan sus puntos, pero pierden la referencia "
        "a cuáles eran obligatorios. Para retirar una plantilla usada, desactivarla."
    ),
)
async def borrar_plantilla(
    plantilla_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(solo_admin)],
) -> None:
    await service.eliminar_plantilla(sesion, plantilla_id)


@router.post(
    "/calidad/plantillas/{plantilla_id}/puntos",
    response_model=PlantillaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Añadir un punto a la plantilla",
)
async def agregar_punto(
    plantilla_id: UUID,
    datos: PuntoCrear,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(solo_admin)],
) -> PlantillaRespuesta:
    return _plantilla(await service.agregar_punto(sesion, plantilla_id, datos))


@router.patch(
    "/calidad/puntos/{punto_id}",
    response_model=PlantillaRespuesta,
    summary="Editar un punto de plantilla",
)
async def editar_punto(
    punto_id: UUID,
    datos: PuntoEditar,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(solo_admin)],
) -> PlantillaRespuesta:
    return _plantilla(await service.actualizar_punto(sesion, punto_id, datos))


@router.delete(
    "/calidad/puntos/{punto_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar un punto de plantilla",
)
async def borrar_punto(
    punto_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(solo_admin)],
) -> None:
    await service.eliminar_punto(sesion, punto_id)


# -----------------------------------------------------------------------------
# Controles
# -----------------------------------------------------------------------------


@router.get(
    "/ordenes/{orden_id}/controles",
    response_model=list[ControlRespuesta],
    summary="Controles de calidad de la orden",
)
async def listar_controles(
    orden_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> list[ControlRespuesta]:
    return [_control(c) for c in await service.listar_controles(sesion, orden_id)]


@router.post(
    "/ordenes/{orden_id}/controles",
    response_model=ControlRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Iniciar un control de calidad",
    description=(
        "Copia los puntos de la plantilla. No se puede abrir otro mientras haya "
        "uno en curso para la misma orden."
    ),
)
async def iniciar_control(
    orden_id: UUID,
    datos: ControlIniciar,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    usuario: Annotated[UsuarioAutenticado, Depends(taller)],
) -> ControlRespuesta:
    return _control(await service.iniciar_control(sesion, orden_id, datos, usuario))


@router.get(
    "/controles/{control_id}",
    response_model=ControlRespuesta,
    summary="Consultar un control",
)
async def obtener_control(
    control_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> ControlRespuesta:
    return _control(await service.obtener_control(sesion, control_id))


@router.patch(
    "/controles/{control_id}",
    response_model=ControlRespuesta,
    summary="Anotar observaciones o cambiar inspector",
)
async def editar_control(
    control_id: UUID,
    datos: ControlEditar,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(taller)],
) -> ControlRespuesta:
    return _control(await service.actualizar_control(sesion, control_id, datos))


@router.patch(
    "/control-respuestas/{respuesta_id}",
    response_model=ControlRespuesta,
    summary="Marcar un punto",
    description="Devuelve el control completo, con los pendientes recalculados.",
)
async def marcar_punto(
    respuesta_id: UUID,
    datos: RespuestaEditar,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(taller)],
) -> ControlRespuesta:
    return _control(await service.actualizar_respuesta(sesion, respuesta_id, datos))


@router.post(
    "/controles/{control_id}/cerrar",
    response_model=ControlRespuesta,
    summary="Aprobar o rechazar la inspección",
    description=(
        "Aprobar exige todos los puntos obligatorios conformes y pasa la orden a "
        "`listo_para_entrega`. Rechazar exige observaciones y la devuelve a "
        "`en_reparacion`. La orden solo se mueve si está en `control_calidad`."
    ),
)
async def cerrar_control(
    control_id: UUID,
    datos: CerrarControl,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    usuario: Annotated[UsuarioAutenticado, Depends(taller)],
) -> ControlRespuesta:
    return _control(await service.cerrar_control(sesion, control_id, datos, usuario))
