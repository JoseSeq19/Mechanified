"""Esquemas del catálogo de repuestos y de las piezas de una orden.

Al cargar una pieza a la orden hay dos formas de hacerlo, y el esquema admite
las dos en la misma petición:

  - Con `repuesto_id`: se toman la descripción y el precio del catálogo.
  - Sin él: hacen falta `descripcion` y `precio_unitario`, para la pieza que se
    compra suelta y no está dada de alta.

Lo valida `ItemCrear`, que rechaza el caso incompleto antes de llegar a la base.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.repuestos.models import EstadoItemRepuesto

_Nombre = Annotated[str, Field(min_length=2, max_length=160)]
_Corto = Annotated[str, Field(max_length=60)]
_Dinero = Annotated[Decimal, Field(ge=0, le=9_999_999, decimal_places=2)]
_Cantidad = Annotated[Decimal, Field(gt=0, le=999_999, decimal_places=2)]


def _limpiar(v: object) -> object:
    if isinstance(v, str):
        return v.strip() or None
    return v


def _sku(v: object) -> object:
    """El índice único es sobre upper(sku): se normaliza para que coincida."""
    if isinstance(v, str):
        return v.strip().upper() or None
    return v


# -----------------------------------------------------------------------------
# Catálogo
# -----------------------------------------------------------------------------


class RepuestoCrear(BaseModel):
    sku: Annotated[str, Field(min_length=1, max_length=40)]
    nombre: _Nombre
    descripcion: Annotated[str, Field(max_length=500)] | None = None
    categoria: _Corto | None = None
    unidad: _Corto = "unidad"
    costo: _Dinero = Decimal("0")
    precio_venta: _Dinero = Decimal("0")
    stock: Annotated[Decimal, Field(ge=0, le=999_999, decimal_places=2)] = Decimal("0")
    stock_minimo: Annotated[Decimal, Field(ge=0, le=999_999, decimal_places=2)] = Decimal("0")
    proveedor: _Corto | None = None

    @field_validator("sku", mode="before")
    @classmethod
    def _sku_normalizado(cls, v: object) -> object:
        return _sku(v)

    @field_validator("nombre", "descripcion", "categoria", "proveedor", "unidad", mode="before")
    @classmethod
    def _textos(cls, v: object) -> object:
        return _limpiar(v)


class RepuestoEditar(BaseModel):
    sku: Annotated[str, Field(min_length=1, max_length=40)] | None = None
    nombre: _Nombre | None = None
    descripcion: Annotated[str, Field(max_length=500)] | None = None
    categoria: _Corto | None = None
    unidad: _Corto | None = None
    costo: _Dinero | None = None
    precio_venta: _Dinero | None = None
    stock: Annotated[Decimal, Field(ge=0, le=999_999, decimal_places=2)] | None = None
    stock_minimo: Annotated[Decimal, Field(ge=0, le=999_999, decimal_places=2)] | None = None
    proveedor: _Corto | None = None
    activo: bool | None = None

    @field_validator("sku", mode="before")
    @classmethod
    def _sku_normalizado(cls, v: object) -> object:
        return _sku(v)

    @field_validator("nombre", "descripcion", "categoria", "proveedor", "unidad", mode="before")
    @classmethod
    def _textos(cls, v: object) -> object:
        return _limpiar(v)


class RepuestoRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    taller_id: UUID
    sku: str
    nombre: str
    descripcion: str | None
    categoria: str | None
    unidad: str
    costo: Decimal
    precio_venta: Decimal
    stock: Decimal
    stock_minimo: Decimal
    #: Señal para reponer. El stock es informativo: Mechanified todavía no lleva
    #: movimientos de inventario.
    bajo_minimo: bool
    proveedor: str | None
    activo: bool
    creado_en: datetime
    actualizado_en: datetime


# -----------------------------------------------------------------------------
# Piezas de una orden
# -----------------------------------------------------------------------------


class ItemCrear(BaseModel):
    repuesto_id: UUID | None = None
    descripcion: _Nombre | None = None
    cantidad: _Cantidad = Decimal("1")
    precio_unitario: _Dinero | None = None
    estado: EstadoItemRepuesto = EstadoItemRepuesto.SOLICITADO
    notas: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("descripcion", "notas", mode="before")
    @classmethod
    def _textos(cls, v: object) -> object:
        return _limpiar(v)

    @model_validator(mode="after")
    def _pieza_identificable(self) -> "ItemCrear":
        """O sale del catálogo, o trae descripción y precio propios."""
        if self.repuesto_id is None:
            faltan = [
                campo
                for campo, valor in (
                    ("descripcion", self.descripcion),
                    ("precio_unitario", self.precio_unitario),
                )
                if valor is None
            ]
            if faltan:
                raise ValueError(
                    "Una pieza fuera de catálogo necesita descripción y precio unitario. "
                    f"Falta: {', '.join(faltan)}."
                )
        return self


class ItemEditar(BaseModel):
    descripcion: _Nombre | None = None
    cantidad: _Cantidad | None = None
    precio_unitario: _Dinero | None = None
    estado: EstadoItemRepuesto | None = None
    notas: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("descripcion", "notas", mode="before")
    @classmethod
    def _textos(cls, v: object) -> object:
        return _limpiar(v)


class ItemRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    orden_id: UUID
    repuesto_id: UUID | None
    sku: str | None = None
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    subtotal: Decimal
    estado: EstadoItemRepuesto
    estado_etiqueta: str
    notas: str | None
    solicitante_nombre: str | None = None
    creado_en: datetime


class ResumenRepuestos(BaseModel):
    """Las piezas de la orden y lo que suman."""

    lineas: list[ItemRespuesta]
    total: Decimal
    #: Cuántas siguen sin llegar. Es lo que bloquea el avance de la reparación.
    pendientes: int
