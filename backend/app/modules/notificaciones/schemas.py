"""Esquemas de la cola de notificaciones.

Lo que expone la API es el **estado del aviso**, no su contenido: a quién se le
escribió, por qué, si salió y qué falló. El texto se pide aparte, con la vista
previa, porque redactarlo obliga a leer media orden y no tiene sentido hacerlo
para pintar una lista.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NotificacionRespuesta(BaseModel):
    """Una fila de la cola, tal como la ve el taller."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    taller_id: UUID
    orden_id: UUID | None
    canal: str
    destinatario: str
    plantilla: str
    plantilla_etiqueta: str
    estado: str
    estado_etiqueta: str
    intentos: int
    #: Por qué no salió. Es el mensaje del servidor de correo, en crudo: quien
    #: lo lee necesita el detalle para saber si el problema es la dirección.
    ultimo_error: str | None
    programada_para: datetime
    enviada_en: datetime | None
    creado_en: datetime


class VistaPreviaCorreo(BaseModel):
    """El mensaje ya redactado, para verlo antes o después de enviarlo."""

    asunto: str
    texto: str
    html: str
    destinatario: str
