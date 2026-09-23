"""Esquemas de encuestas.

Como en presupuestos, hay dos familias a propósito:

  - `EncuestaRespuesta` es lo que ve el taller, con el enlace y los
    identificadores internos.
  - `EncuestaPublica` es lo que ve el cliente al abrir el enlace: el nombre del
    taller, su vehículo y poco más. Ni notas internas, ni importes, ni quién lo
    atendió.

La separación no es cosmética: es lo que impide que añadir un campo a la ficha
interna lo publique sin querer en una página que puede abrir cualquiera con el
enlace.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_Nota = Annotated[int, Field(ge=1, le=5, description="De 1 (muy mal) a 5 (excelente)")]
_Comentario = Annotated[str, Field(max_length=1000)]


class RespuestaCliente(BaseModel):
    """Lo que contesta el cliente. Las cuatro notas son obligatorias.

    Una encuesta a medias no se puede promediar con las demás sin falsear la
    media, así que se piden enteras. El comentario sí es opcional: es lo único
    que cuesta escribir.
    """

    puntaje_atencion: _Nota
    puntaje_tiempo: _Nota
    puntaje_calidad: _Nota
    #: La pregunta de recomendación va de 0 a 10 —no de 1 a 5— porque es la
    #: escala con la que se calcula el NPS, y reescalarla lo desvirtúa.
    recomendaria: Annotated[int, Field(ge=0, le=10)]
    comentario: _Comentario | None = None

    @field_validator("comentario", mode="before")
    @classmethod
    def _limpio(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip() or None
        return v


class EncuestaRespuesta(BaseModel):
    """Ficha de la encuesta de una orden, para el taller."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    orden_id: UUID
    enviada_en: datetime | None
    respondida_en: datetime | None
    respondida: bool
    puntaje_atencion: int | None
    puntaje_tiempo: int | None
    puntaje_calidad: int | None
    recomendaria: int | None
    comentario: str | None
    creado_en: datetime
    #: Enlace para compartir a mano cuando el cliente no tiene correo.
    enlace_publico: str


class EncuestaEnviada(EncuestaRespuesta):
    """Resultado de pedir el envío, con el desenlace del correo."""

    #: A quién se le encoló el aviso, o None si el cliente no tiene correo. La
    #: interfaz lo usa para decir "se lo mandamos a x@y" o "cópiale el enlace".
    encolada_a: str | None = None


class EncuestaFila(EncuestaRespuesta):
    """Fila del listado general, con lo justo para identificar el servicio."""

    folio: str
    placa: str
    vehiculo: str
    cliente_nombre: str
    fecha_entrega: datetime | None


class ResumenEncuestas(BaseModel):
    """Lo que se muestra arriba del listado."""

    enviadas: int
    respondidas: int
    #: Porcentaje de encuestas creadas que el cliente contestó.
    tasa_respuesta: float
    promedio_atencion: float | None
    promedio_tiempo: float | None
    promedio_calidad: float | None
    #: Promotores (9-10) menos detractores (0-6), en porcentaje. Va de -100 a
    #: 100. None mientras nadie haya contestado.
    nps: int | None
    promotores: int
    pasivos: int
    detractores: int


class EncuestaPublica(BaseModel):
    """Lo que ve el cliente. Deliberadamente escueto."""

    taller_nombre: str
    taller_telefono: str | None
    folio_orden: str
    vehiculo: str
    placa: str
    fecha_entrega: datetime | None
    respondida: bool
    respondida_en: datetime | None
    puntaje_atencion: int | None
    puntaje_tiempo: int | None
    puntaje_calidad: int | None
    recomendaria: int | None
    comentario: str | None
