"""Endpoints de diagnóstico y mano de obra.

Las rutas de alta y de listado cuelgan de la orden (`/ordenes/{id}/...`) porque
ni un diagnóstico ni una línea de trabajo existen fuera de una; las de edición
y borrado van por el identificador del recurso, que ya es único.

Permisos: el diagnóstico lo escribe el técnico (y administración). La mano de
obra la puede tocar también asesoría, que es quien ajusta la cotización cuando
habla con el cliente. Son los mismos roles que aplican las políticas RLS de la
migración 000500.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import sesion_usuario
from app.core.permissions import requiere_rol
from app.core.roles import Rol
from app.core.security import UsuarioAutenticado, usuario_actual
from app.modules.diagnosticos import service
from app.modules.diagnosticos.models import Diagnostico, DiagnosticoHallazgo, ManoObra
from app.modules.diagnosticos.schemas import (
    DiagnosticoCrear,
    DiagnosticoEditar,
    DiagnosticoRespuesta,
    HallazgoCrear,
    HallazgoEditar,
    HallazgoRespuesta,
    ManoObraCrear,
    ManoObraEditar,
    ManoObraRespuesta,
    ResumenManoObra,
)

router = APIRouter(tags=["diagnóstico"])

#: Quién registra el diagnóstico.
diagnostica = requiere_rol(Rol.ADMIN_TALLER, Rol.TECNICO)
#: Quién puede cargar trabajo a la orden.
cotiza = requiere_rol(Rol.ADMIN_TALLER, Rol.TECNICO, Rol.ASESOR_SERVICIO)


def _hallazgo(h: DiagnosticoHallazgo) -> HallazgoRespuesta:
    return HallazgoRespuesta(
        id=h.id,
        diagnostico_id=h.diagnostico_id,
        sistema=h.sistema,
        descripcion=h.descripcion,
        severidad=h.severidad,
        severidad_etiqueta=h.severidad.etiqueta,
        requiere_repuesto=h.requiere_repuesto,
        orden_visual=h.orden_visual,
    )


def _diagnostico(d: Diagnostico) -> DiagnosticoRespuesta:
    return DiagnosticoRespuesta(
        id=d.id,
        taller_id=d.taller_id,
        orden_id=d.orden_id,
        tecnico_id=d.tecnico_id,
        tecnico_nombre=d.tecnico.nombre_completo if d.tecnico else None,
        resumen=d.resumen,
        horas_estimadas=d.horas_estimadas,
        hallazgos=[_hallazgo(h) for h in d.hallazgos],
        creado_en=d.creado_en,
        actualizado_en=d.actualizado_en,
    )


def _linea(m: ManoObra) -> ManoObraRespuesta:
    return ManoObraRespuesta(
        id=m.id,
        orden_id=m.orden_id,
        descripcion=m.descripcion,
        horas=m.horas,
        tarifa_hora=m.tarifa_hora,
        subtotal=m.subtotal,
        tecnico_id=m.tecnico_id,
        tecnico_nombre=m.tecnico.nombre_completo if m.tecnico else None,
        creado_en=m.creado_en,
    )


# -----------------------------------------------------------------------------
# Diagnósticos
# -----------------------------------------------------------------------------


@router.get(
    "/ordenes/{orden_id}/diagnosticos",
    response_model=list[DiagnosticoRespuesta],
    summary="Diagnósticos de la orden",
    description="Puede haber varios: el trabajo adicional se registra como uno nuevo.",
)
async def listar_diagnosticos(
    orden_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> list[DiagnosticoRespuesta]:
    return [_diagnostico(d) for d in await service.listar_diagnosticos(sesion, orden_id)]


@router.post(
    "/ordenes/{orden_id}/diagnosticos",
    response_model=DiagnosticoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un diagnóstico",
    description="Se crea con sus hallazgos en la misma petición.",
)
async def crear_diagnostico(
    orden_id: UUID,
    datos: DiagnosticoCrear,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    usuario: Annotated[UsuarioAutenticado, Depends(diagnostica)],
) -> DiagnosticoRespuesta:
    return _diagnostico(await service.crear_diagnostico(sesion, orden_id, datos, usuario))


@router.patch(
    "/diagnosticos/{diagnostico_id}",
    response_model=DiagnosticoRespuesta,
    summary="Editar un diagnóstico",
)
async def editar_diagnostico(
    diagnostico_id: UUID,
    datos: DiagnosticoEditar,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(diagnostica)],
) -> DiagnosticoRespuesta:
    return _diagnostico(await service.actualizar_diagnostico(sesion, diagnostico_id, datos))


@router.delete(
    "/diagnosticos/{diagnostico_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar un diagnóstico",
)
async def borrar_diagnostico(
    diagnostico_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(diagnostica)],
) -> None:
    await service.eliminar_diagnostico(sesion, diagnostico_id)


# -----------------------------------------------------------------------------
# Hallazgos
# -----------------------------------------------------------------------------


@router.post(
    "/diagnosticos/{diagnostico_id}/hallazgos",
    response_model=DiagnosticoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Añadir un hallazgo",
    description="Devuelve el diagnóstico completo, para no tener que recargarlo.",
)
async def agregar_hallazgo(
    diagnostico_id: UUID,
    datos: HallazgoCrear,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(diagnostica)],
) -> DiagnosticoRespuesta:
    return _diagnostico(await service.agregar_hallazgo(sesion, diagnostico_id, datos))


@router.patch(
    "/hallazgos/{hallazgo_id}",
    response_model=DiagnosticoRespuesta,
    summary="Editar un hallazgo",
)
async def editar_hallazgo(
    hallazgo_id: UUID,
    datos: HallazgoEditar,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(diagnostica)],
) -> DiagnosticoRespuesta:
    return _diagnostico(await service.actualizar_hallazgo(sesion, hallazgo_id, datos))


@router.delete(
    "/hallazgos/{hallazgo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar un hallazgo",
)
async def borrar_hallazgo(
    hallazgo_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(diagnostica)],
) -> None:
    await service.eliminar_hallazgo(sesion, hallazgo_id)


# -----------------------------------------------------------------------------
# Mano de obra
# -----------------------------------------------------------------------------


@router.get(
    "/ordenes/{orden_id}/mano-obra",
    response_model=ResumenManoObra,
    summary="Mano de obra cargada a la orden",
)
async def listar_mano_obra(
    orden_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> ResumenManoObra:
    lineas = await service.listar_mano_obra(sesion, orden_id)
    horas, total = await service.total_mano_obra(sesion, orden_id)
    return ResumenManoObra(lineas=[_linea(m) for m in lineas], total_horas=horas, total=total)


@router.post(
    "/ordenes/{orden_id}/mano-obra",
    response_model=ManoObraRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Cargar trabajo a la orden",
    description=(
        "Si no se indica `tarifa_hora`, se toma la del taller y queda fija en la "
        "línea: cambiar la tarifa después no altera órdenes ya cotizadas."
    ),
)
async def crear_mano_obra(
    orden_id: UUID,
    datos: ManoObraCrear,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    usuario: Annotated[UsuarioAutenticado, Depends(cotiza)],
) -> ManoObraRespuesta:
    return _linea(await service.crear_mano_obra(sesion, orden_id, datos, usuario))


@router.patch(
    "/mano-obra/{linea_id}",
    response_model=ManoObraRespuesta,
    summary="Editar una línea de trabajo",
)
async def editar_mano_obra(
    linea_id: UUID,
    datos: ManoObraEditar,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(cotiza)],
) -> ManoObraRespuesta:
    return _linea(await service.actualizar_mano_obra(sesion, linea_id, datos))


@router.delete(
    "/mano-obra/{linea_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar una línea de trabajo",
)
async def borrar_mano_obra(
    linea_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(cotiza)],
) -> None:
    await service.eliminar_mano_obra(sesion, linea_id)
