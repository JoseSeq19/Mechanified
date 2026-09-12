"""Esquemas del diagnóstico y de la mano de obra.

El diagnóstico se crea **con sus hallazgos en la misma petición**. Podría
hacerse en dos pasos (crear la cabecera, luego cada hallazgo), pero eso dejaría
la puerta abierta a diagnósticos vacíos si el segundo paso falla, y obligaría a
la app móvil —donde se captura esto, con el vehículo delante y mala señal— a
encadenar varias llamadas.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.diagnosticos.models import SeveridadHallazgo

_Texto = Annotated[str, Field(min_length=3, max_length=1000)]
_Sistema = Annotated[str, Field(min_length=2, max_length=60)]
_Horas = Annotated[Decimal, Field(gt=0, le=999, decimal_places=2)]


def _recortar(v: object) -> object:
    return v.strip() if isinstance(v, str) else v


# -----------------------------------------------------------------------------
# Hallazgos
# -----------------------------------------------------------------------------


class HallazgoCrear(BaseModel):
    sistema: _Sistema
    descripcion: _Texto
    severidad: SeveridadHallazgo = SeveridadHallazgo.MODERADA
    requiere_repuesto: bool = False

    @field_validator("sistema", "descripcion", mode="before")
    @classmethod
    def _limpios(cls, v: object) -> object:
        return _recortar(v)


class HallazgoEditar(BaseModel):
    sistema: _Sistema | None = None
    descripcion: _Texto | None = None
    severidad: SeveridadHallazgo | None = None
    requiere_repuesto: bool | None = None
    orden_visual: int | None = None

    @field_validator("sistema", "descripcion", mode="before")
    @classmethod
    def _limpios(cls, v: object) -> object:
        return _recortar(v)


class HallazgoRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    diagnostico_id: UUID
    sistema: str
    descripcion: str
    severidad: SeveridadHallazgo
    severidad_etiqueta: str
    requiere_repuesto: bool
    orden_visual: int


# -----------------------------------------------------------------------------
# Diagnóstico
# -----------------------------------------------------------------------------


class DiagnosticoCrear(BaseModel):
    resumen: _Texto
    horas_estimadas: Annotated[Decimal, Field(ge=0, le=999, decimal_places=2)] = Decimal("0")
    tecnico_id: UUID | None = None
    hallazgos: list[HallazgoCrear] = Field(default_factory=list)

    @field_validator("resumen", mode="before")
    @classmethod
    def _resumen_limpio(cls, v: object) -> object:
        return _recortar(v)


class DiagnosticoEditar(BaseModel):
    resumen: _Texto | None = None
    horas_estimadas: Annotated[Decimal, Field(ge=0, le=999, decimal_places=2)] | None = None
    tecnico_id: UUID | None = None

    @field_validator("resumen", mode="before")
    @classmethod
    def _resumen_limpio(cls, v: object) -> object:
        return _recortar(v)


class DiagnosticoRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    taller_id: UUID
    orden_id: UUID
    tecnico_id: UUID | None
    tecnico_nombre: str | None = None
    resumen: str
    horas_estimadas: Decimal
    hallazgos: list[HallazgoRespuesta] = Field(default_factory=list)
    creado_en: datetime
    actualizado_en: datetime


# -----------------------------------------------------------------------------
# Mano de obra
# -----------------------------------------------------------------------------


class ManoObraCrear(BaseModel):
    descripcion: _Texto
    horas: _Horas
    #: Si no viene, se toma la tarifa configurada en el taller.
    tarifa_hora: Annotated[Decimal, Field(ge=0, le=99999, decimal_places=2)] | None = None
    tecnico_id: UUID | None = None

    @field_validator("descripcion", mode="before")
    @classmethod
    def _descripcion_limpia(cls, v: object) -> object:
        return _recortar(v)


class ManoObraEditar(BaseModel):
    descripcion: _Texto | None = None
    horas: _Horas | None = None
    tarifa_hora: Annotated[Decimal, Field(ge=0, le=99999, decimal_places=2)] | None = None
    tecnico_id: UUID | None = None

    @field_validator("descripcion", mode="before")
    @classmethod
    def _descripcion_limpia(cls, v: object) -> object:
        return _recortar(v)


class ManoObraRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    orden_id: UUID
    descripcion: str
    horas: Decimal
    tarifa_hora: Decimal
    subtotal: Decimal
    tecnico_id: UUID | None
    tecnico_nombre: str | None = None
    creado_en: datetime


class ResumenManoObra(BaseModel):
    """Las líneas y lo que suman, para no recalcularlo en la interfaz."""

    lineas: list[ManoObraRespuesta]
    total_horas: Decimal
    total: Decimal
