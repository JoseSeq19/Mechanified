"""Esquemas de entrada y salida de vehículos.

La placa y el VIN se normalizan a mayúsculas sin espacios antes de llegar a la
base. No es cosmético: los índices únicos son sobre `upper(placa)` y
`upper(vin)`, así que sin normalizar, "ab123cd" y "AB123CD" se guardarían como
filas distintas que el índice sí considera la misma, y la búsqueda por placa
dependería de cómo la escribió quien la capturó.

Como en clientes, `taller_id` no aparece en ningún esquema de entrada: sale del
token.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ANIO_MIN = 1900
_ANIO_MAX = 2100

_Placa = Annotated[str, Field(min_length=4, max_length=12)]
_Texto = Annotated[str, Field(max_length=80)]


def _limpiar(valor: str | None) -> str | None:
    """Recorta y convierte la cadena vacía en NULL."""
    if valor is None:
        return None
    limpio = valor.strip()
    return limpio or None


def _normalizar_identificador(valor: object) -> object:
    """Mayúsculas y sin espacios internos, para placas y VIN."""
    if not isinstance(valor, str):
        return valor
    return _limpiar(valor.replace(" ", "").replace("-", "").upper())


class VehiculoBase(BaseModel):
    vin: Annotated[str, Field(max_length=25)] | None = None
    anio: Annotated[int, Field(ge=_ANIO_MIN, le=_ANIO_MAX)] | None = None
    color: _Texto | None = None
    tipo_combustible: _Texto | None = None
    transmision: _Texto | None = None
    kilometraje_ultimo: Annotated[int, Field(ge=0, le=9_999_999)] | None = None
    notas: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("vin", mode="before")
    @classmethod
    def _vin_normalizado(cls, v: object) -> object:
        return _normalizar_identificador(v)

    @field_validator("color", "tipo_combustible", "transmision", "notas", mode="before")
    @classmethod
    def _texto_limpio(cls, v: object) -> object:
        return _limpiar(v) if isinstance(v, str) or v is None else v


class VehiculoCrear(VehiculoBase):
    cliente_id: UUID
    placa: _Placa
    marca: _Texto
    modelo: _Texto

    @field_validator("placa", mode="before")
    @classmethod
    def _placa_normalizada(cls, v: object) -> object:
        return _normalizar_identificador(v)

    @field_validator("marca", "modelo", mode="before")
    @classmethod
    def _sin_espacios(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class VehiculoEditar(BaseModel):
    """Todo opcional: es un PATCH."""

    cliente_id: UUID | None = None
    placa: _Placa | None = None
    vin: Annotated[str, Field(max_length=25)] | None = None
    marca: _Texto | None = None
    modelo: _Texto | None = None
    anio: Annotated[int, Field(ge=_ANIO_MIN, le=_ANIO_MAX)] | None = None
    color: _Texto | None = None
    tipo_combustible: _Texto | None = None
    transmision: _Texto | None = None
    kilometraje_ultimo: Annotated[int, Field(ge=0, le=9_999_999)] | None = None
    notas: Annotated[str, Field(max_length=500)] | None = None
    activo: bool | None = None

    @field_validator("placa", "vin", mode="before")
    @classmethod
    def _identificadores(cls, v: object) -> object:
        return _normalizar_identificador(v)

    @field_validator("marca", "modelo", mode="before")
    @classmethod
    def _sin_espacios(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @field_validator("color", "tipo_combustible", "transmision", "notas", mode="before")
    @classmethod
    def _texto_limpio(cls, v: object) -> object:
        return _limpiar(v) if isinstance(v, str) or v is None else v


class VehiculoRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    taller_id: UUID
    cliente_id: UUID
    #: Nombre del propietario, resuelto con un JOIN. Evita que la interfaz tenga
    #: que pedir cada cliente por separado para pintar un listado.
    cliente_nombre: str | None = None
    placa: str
    vin: str | None
    marca: str
    modelo: str
    anio: int | None
    color: str | None
    tipo_combustible: str | None
    transmision: str | None
    kilometraje_ultimo: int | None
    notas: str | None
    activo: bool
    creado_en: datetime
    actualizado_en: datetime
