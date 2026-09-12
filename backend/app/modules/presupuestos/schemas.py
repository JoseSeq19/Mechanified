"""Esquemas de presupuestos.

Hay dos familias de respuesta a propósito:

  - `PresupuestoRespuesta` es lo que ve el taller: incluye el token del enlace,
    quién lo emitió y los identificadores internos.
  - `PresupuestoPublico` es lo que ve el cliente al abrir el enlace, sin tener
    cuenta. Lleva el nombre del taller y el vehículo para que sepa de qué le
    hablan, y **nada más**: ni identificadores internos, ni el token, ni notas
    del taller.

Separarlas es lo que impide que un cambio en la ficha interna filtre datos al
documento que se manda fuera.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.presupuestos.models import EstadoPresupuesto

_Dinero = Annotated[Decimal, Field(ge=0, le=9_999_999, decimal_places=2)]
_Comentario = Annotated[str, Field(max_length=1000)]


class PresupuestoEmitir(BaseModel):
    """Emitir copia las líneas vivas de la orden; solo se ajustan estos tres."""

    descuento: _Dinero = Decimal("0")
    #: Si no viene, se toma el del taller. Un 0 explícito significa exento.
    impuesto_pct: Annotated[Decimal, Field(ge=0, le=100, decimal_places=2)] | None = None
    valido_hasta: date | None = None


class PresupuestoEditar(BaseModel):
    """Solo mientras es borrador. Después, los montos quedan sellados."""

    descuento: _Dinero | None = None
    impuesto_pct: Annotated[Decimal, Field(ge=0, le=100, decimal_places=2)] | None = None
    valido_hasta: date | None = None


class RespuestaCliente(BaseModel):
    aprobado: bool
    comentario: _Comentario | None = None

    @field_validator("comentario", mode="before")
    @classmethod
    def _limpio(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip() or None
        return v


class ItemRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tipo: str
    tipo_etiqueta: str
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    subtotal: Decimal
    orden_visual: int


class PresupuestoResumen(BaseModel):
    """Fila del listado de versiones de una orden."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    orden_id: UUID
    version: int
    estado: EstadoPresupuesto
    estado_etiqueta: str
    total: Decimal
    valido_hasta: date | None
    #: Pasada la fecha de validez y todavía sin respuesta del cliente.
    caducado: bool = False
    enviado_en: datetime | None
    respondido_en: datetime | None
    creado_en: datetime


class PresupuestoRespuesta(PresupuestoResumen):
    """Ficha completa, para el taller."""

    taller_id: UUID
    subtotal_mano_obra: Decimal
    subtotal_repuestos: Decimal
    descuento: Decimal
    impuesto_pct: Decimal
    impuesto_monto: Decimal
    comentario_cliente: str | None
    autor_nombre: str | None = None
    items: list[ItemRespuesta] = Field(default_factory=list)
    #: Enlace que se le manda al cliente. Solo aparece una vez enviado.
    enlace_publico: str | None = None


class PresupuestoPublico(BaseModel):
    """Lo que ve el cliente. Deliberadamente escueto."""

    taller_nombre: str
    taller_telefono: str | None
    moneda: str

    folio_orden: str
    vehiculo: str
    placa: str

    version: int
    estado: EstadoPresupuesto
    estado_etiqueta: str
    #: True si ya no admite respuesta, por caducidad o porque ya respondió.
    cerrado: bool
    valido_hasta: date | None

    items: list[ItemRespuesta]
    subtotal: Decimal
    descuento: Decimal
    impuesto_pct: Decimal
    impuesto_monto: Decimal
    total: Decimal

    comentario_cliente: str | None
    respondido_en: datetime | None
