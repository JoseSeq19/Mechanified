"""Esquemas del checklist y de los controles de calidad."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.calidad.models import ResultadoCheck

_Nombre = Annotated[str, Field(min_length=2, max_length=120)]
_Punto = Annotated[str, Field(min_length=3, max_length=300)]
_Texto = Annotated[str, Field(max_length=1000)]


def _limpiar(v: object) -> object:
    if isinstance(v, str):
        return v.strip() or None
    return v


# -----------------------------------------------------------------------------
# Plantillas
# -----------------------------------------------------------------------------


class PuntoCrear(BaseModel):
    descripcion: _Punto
    categoria: Annotated[str, Field(max_length=60)] | None = None
    obligatorio: bool = True

    @field_validator("descripcion", "categoria", mode="before")
    @classmethod
    def _textos(cls, v: object) -> object:
        return _limpiar(v)


class PuntoEditar(BaseModel):
    descripcion: _Punto | None = None
    categoria: Annotated[str, Field(max_length=60)] | None = None
    obligatorio: bool | None = None
    orden_visual: int | None = None

    @field_validator("descripcion", "categoria", mode="before")
    @classmethod
    def _textos(cls, v: object) -> object:
        return _limpiar(v)


class PuntoRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plantilla_id: UUID
    categoria: str | None
    descripcion: str
    obligatorio: bool
    orden_visual: int


class PlantillaCrear(BaseModel):
    nombre: _Nombre
    descripcion: _Texto | None = None
    puntos: list[PuntoCrear] = Field(default_factory=list)

    @field_validator("nombre", "descripcion", mode="before")
    @classmethod
    def _textos(cls, v: object) -> object:
        return _limpiar(v)


class PlantillaEditar(BaseModel):
    nombre: _Nombre | None = None
    descripcion: _Texto | None = None
    activo: bool | None = None

    @field_validator("nombre", "descripcion", mode="before")
    @classmethod
    def _textos(cls, v: object) -> object:
        return _limpiar(v)


class PlantillaRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    taller_id: UUID
    nombre: str
    descripcion: str | None
    activo: bool
    puntos: list[PuntoRespuesta] = Field(default_factory=list)
    #: Cuántos de esos puntos impiden aprobar si no quedan conformes.
    obligatorios: int = 0
    creado_en: datetime


# -----------------------------------------------------------------------------
# Controles
# -----------------------------------------------------------------------------


class ControlIniciar(BaseModel):
    plantilla_id: UUID
    inspector_id: UUID | None = None


class ControlEditar(BaseModel):
    observaciones: _Texto | None = None
    inspector_id: UUID | None = None

    @field_validator("observaciones", mode="before")
    @classmethod
    def _texto(cls, v: object) -> object:
        return _limpiar(v)


class RespuestaEditar(BaseModel):
    resultado: ResultadoCheck | None = None
    comentario: _Texto | None = None
    evidencia_url: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("comentario", "evidencia_url", mode="before")
    @classmethod
    def _textos(cls, v: object) -> object:
        return _limpiar(v)


class CerrarControl(BaseModel):
    aprobado: bool
    observaciones: _Texto | None = None

    @field_validator("observaciones", mode="before")
    @classmethod
    def _texto(cls, v: object) -> object:
        return _limpiar(v)


class RespuestaControl(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    control_id: UUID
    item_id: UUID | None
    descripcion: str
    resultado: ResultadoCheck
    resultado_etiqueta: str
    #: Copiado de la plantilla al iniciar, para saber qué bloquea la aprobación.
    obligatorio: bool = True
    comentario: str | None
    evidencia_url: str | None
    orden_visual: int


class ControlRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    taller_id: UUID
    orden_id: UUID
    plantilla_id: UUID | None
    inspector_id: UUID | None
    inspector_nombre: str | None = None
    resultado: str
    resultado_etiqueta: str
    observaciones: str | None
    respuestas: list[RespuestaControl] = Field(default_factory=list)
    #: Puntos obligatorios que todavía no están conformes. Mientras haya alguno,
    #: aprobar el control falla.
    pendientes: int = 0
    creado_en: datetime
    cerrado_en: datetime | None
