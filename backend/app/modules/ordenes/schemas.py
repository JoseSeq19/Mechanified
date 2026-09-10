"""Esquemas de entrada y salida de órdenes de servicio.

El estado **no se edita como un campo más**: se cambia con una acción propia
(`POST /ordenes/{id}/estado`). Es una decisión de diseño, no un capricho de la
API. Un cambio de estado tiene reglas, autorización por rol y deja rastro en la
bitácora; tratarlo como un `PATCH` cualquiera invitaría a mezclarlo con la
edición del kilometraje y a perder esa distinción.

Por eso `OrdenEditar` no incluye `estado`, y `CambioEstado` no incluye nada más.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.ordenes.estados import EstadoOrden

_Motivo = Annotated[str, Field(min_length=3, max_length=1000)]
_Nota = Annotated[str, Field(max_length=2000)]


def _limpiar(valor: object) -> object:
    if isinstance(valor, str):
        limpio = valor.strip()
        return limpio or None
    return valor


class OrdenCrear(BaseModel):
    """Alta de una orden. Nace siempre en `recibido`, así que no se indica."""

    cliente_id: UUID
    vehiculo_id: UUID
    motivo_ingreso: _Motivo

    asesor_id: UUID | None = None
    tecnico_id: UUID | None = None
    kilometraje_ingreso: Annotated[int, Field(ge=0, le=9_999_999)] | None = None
    nivel_combustible: Annotated[int, Field(ge=0, le=100)] | None = None
    #: Lo que trae el vehículo al entrar (gato, repuesto, radio…). Libre a
    #: propósito: cada taller inventaría cosas distintas.
    inventario_ingreso: dict[str, Any] = Field(default_factory=dict)
    fecha_promesa: datetime | None = None
    notas_internas: _Nota | None = None

    @field_validator("motivo_ingreso", mode="before")
    @classmethod
    def _motivo_limpio(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @field_validator("notas_internas", mode="before")
    @classmethod
    def _nota_limpia(cls, v: object) -> object:
        return _limpiar(v)


class OrdenEditar(BaseModel):
    """Campos administrativos. El estado se cambia por su propia ruta."""

    asesor_id: UUID | None = None
    tecnico_id: UUID | None = None
    motivo_ingreso: _Motivo | None = None
    kilometraje_ingreso: Annotated[int, Field(ge=0, le=9_999_999)] | None = None
    nivel_combustible: Annotated[int, Field(ge=0, le=100)] | None = None
    inventario_ingreso: dict[str, Any] | None = None
    fecha_promesa: datetime | None = None
    notas_internas: _Nota | None = None

    @field_validator("notas_internas", "motivo_ingreso", mode="before")
    @classmethod
    def _limpios(cls, v: object) -> object:
        return _limpiar(v)


class CambioEstado(BaseModel):
    estado: EstadoOrden
    comentario: _Nota | None = None

    @field_validator("comentario", mode="before")
    @classmethod
    def _comentario_limpio(cls, v: object) -> object:
        return _limpiar(v)

    @model_validator(mode="after")
    def _cancelar_exige_motivo(self) -> "CambioEstado":
        """Cancelar sin explicar por qué deja un hueco en el historial.

        La base también lo exige (`mch_ordenes_guard`), pero rechazarlo aquí da
        un mensaje que se puede mostrar junto al campo.
        """
        if self.estado is EstadoOrden.CANCELADO and not self.comentario:
            raise ValueError("Cancelar una orden exige indicar el motivo en el comentario.")
        return self


# -----------------------------------------------------------------------------
# Salida
# -----------------------------------------------------------------------------


class OrdenResumen(BaseModel):
    """Fila del listado y tarjeta del tablero. Lo justo para pintar sin abrir."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    folio: str
    estado: EstadoOrden
    estado_etiqueta: str

    cliente_id: UUID
    cliente_nombre: str
    vehiculo_id: UUID
    vehiculo_placa: str
    vehiculo_descripcion: str

    tecnico_nombre: str | None = None
    asesor_nombre: str | None = None

    fecha_ingreso: datetime
    fecha_promesa: datetime | None
    total: Decimal
    #: Pasada la fecha prometida y todavía sin entregar.
    atrasada: bool = False


class OrdenRespuesta(OrdenResumen):
    """Ficha completa."""

    taller_id: UUID
    motivo_ingreso: str
    kilometraje_ingreso: int | None
    nivel_combustible: int | None
    inventario_ingreso: dict[str, Any]
    fecha_entrega: datetime | None
    total_mano_obra: Decimal
    total_repuestos: Decimal
    notas_internas: str | None
    motivo_cancelacion: str | None
    creado_en: datetime
    actualizado_en: datetime

    #: Estados a los que **este** usuario puede mover la orden ahora mismo.
    #: La interfaz dibuja un botón por cada uno y no necesita conocer las reglas.
    transiciones_posibles: list[EstadoOrden] = Field(default_factory=list)


class EventoRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    estado_anterior: EstadoOrden | None
    estado_nuevo: EstadoOrden
    estado_nuevo_etiqueta: str
    usuario_nombre: str | None = None
    comentario: str | None
    creado_en: datetime


class ColumnaTablero(BaseModel):
    estado: EstadoOrden
    etiqueta: str
    cantidad: int


class ResumenTablero(BaseModel):
    """Conteo por estado, para las cabeceras del tablero."""

    columnas: list[ColumnaTablero]
    total_abiertas: int
