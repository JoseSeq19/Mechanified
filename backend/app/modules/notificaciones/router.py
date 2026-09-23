"""Endpoints de la cola de avisos al cliente.

Solo de consulta y reintento: nadie redacta un correo desde aquí. Los avisos los
encolan los módulos que provocan el hecho —enviar un presupuesto, dejar el
vehículo listo, entregarlo— y el contenido lo arma el worker al enviar.

Permisos: los mismos que la política RLS de `notificaciones`, que deja leer la
cola a administración y asesoría. Un técnico puede provocar un aviso, pero no
ver a qué dirección se mandó ni qué decía.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import sesion_usuario
from app.core.permissions import recepcion
from app.core.security import UsuarioAutenticado
from app.modules.notificaciones import service
from app.modules.notificaciones.models import EstadoNotificacion, Notificacion, PlantillaCorreo
from app.modules.notificaciones.schemas import NotificacionRespuesta, VistaPreviaCorreo

router = APIRouter(tags=["notificaciones"])


def _fila(n: Notificacion) -> NotificacionRespuesta:
    return NotificacionRespuesta(
        id=n.id,
        taller_id=n.taller_id,
        orden_id=n.orden_id,
        canal=n.canal.value,
        destinatario=n.destinatario,
        plantilla=n.plantilla,
        plantilla_etiqueta=PlantillaCorreo(n.plantilla).etiqueta,
        estado=n.estado.value,
        estado_etiqueta=EstadoNotificacion(n.estado).etiqueta,
        intentos=n.intentos,
        ultimo_error=n.ultimo_error,
        programada_para=n.programada_para,
        enviada_en=n.enviada_en,
        creado_en=n.creado_en,
    )


@router.get(
    "/ordenes/{orden_id}/notificaciones",
    response_model=list[NotificacionRespuesta],
    summary="Avisos enviados al cliente por esta orden",
)
async def listar_notificaciones(
    orden_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(recepcion)],
) -> list[NotificacionRespuesta]:
    return [_fila(n) for n in await service.listar_de_orden(sesion, orden_id)]


@router.get(
    "/notificaciones/{notificacion_id}/vista-previa",
    response_model=VistaPreviaCorreo,
    summary="Ver el correo",
    description=(
        "Redacta el mensaje con la plantilla y los datos actuales: es el mismo "
        "código que usa el worker al enviar, así que lo que se ve aquí es lo que "
        "recibe el cliente."
    ),
)
async def vista_previa(
    notificacion_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(recepcion)],
) -> VistaPreviaCorreo:
    n, correo = await service.vista_previa(sesion, notificacion_id)
    return VistaPreviaCorreo(
        asunto=correo.asunto,
        texto=correo.texto,
        html=correo.html,
        destinatario=n.destinatario,
    )


@router.post(
    "/notificaciones/{notificacion_id}/reintentar",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Volver a encolar un aviso que falló",
    description=(
        "No reabre el aviso fallido: encola uno nuevo, con el correo que el "
        "cliente tenga ahora. Solo sobre avisos en estado `fallida`."
    ),
)
async def reintentar(
    notificacion_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(recepcion)],
) -> dict[str, str]:
    return {"encolada_a": await service.reintentar(sesion, notificacion_id)}
