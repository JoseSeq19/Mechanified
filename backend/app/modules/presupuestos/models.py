"""Mapeo de presupuestos y sus líneas.

Refleja `supabase/migrations/20260907000700_presupuestos.sql`.

Dos cosas que este modelo no puede hacer, porque las decide Postgres:

  - `version` la asigna un trigger al insertar (el siguiente número de esa
    orden), así que no se escribe desde aquí.
  - `impuesto_monto` y `total` son columnas generadas.

Y una que sí importa entender: `PresupuestoItem` **no apunta** a las líneas
vivas de mano de obra ni de repuestos. Las copia. Si el cliente aprobó 480,00,
ese documento sigue diciendo 480,00 aunque después suba la tarifa del taller o
el precio de una pieza.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Computed,
    Date,
    DateTime,
    Enum,
    FetchedValue,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.usuarios.models import Perfil
from app.shared.modelo import Base


class EstadoPresupuesto(StrEnum):
    """Refleja el enum `public.estado_presupuesto`."""

    BORRADOR = "borrador"
    ENVIADO = "enviado"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"
    VENCIDO = "vencido"

    @property
    def etiqueta(self) -> str:
        return {
            "borrador": "Borrador",
            "enviado": "Enviado al cliente",
            "aprobado": "Aprobado",
            "rechazado": "Rechazado",
            "vencido": "Vencido",
        }[self.value]


class TipoLinea(StrEnum):
    MANO_OBRA = "mano_obra"
    REPUESTO = "repuesto"

    @property
    def etiqueta(self) -> str:
        return "Mano de obra" if self is TipoLinea.MANO_OBRA else "Repuesto"


_estado_sql = Enum(
    EstadoPresupuesto,
    name="estado_presupuesto",
    native_enum=True,
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class Presupuesto(Base):
    __tablename__ = "presupuestos"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    taller_id: Mapped[UUID] = mapped_column(nullable=False)
    orden_id: Mapped[UUID] = mapped_column(ForeignKey("ordenes_servicio.id"), nullable=False)

    #: La asigna mch_presupuestos_preparar al insertar.
    version: Mapped[int] = mapped_column(Integer, server_default=FetchedValue())

    subtotal_mano_obra: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    subtotal_repuestos: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    descuento: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    #: Sin valor por defecto: el trigger lo toma del taller cuando llega NULL,
    #: para poder distinguir "no lo indicaron" de "es exento".
    impuesto_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), server_default=FetchedValue())

    impuesto_monto: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        Computed(
            "round((subtotal_mano_obra + subtotal_repuestos - descuento) * impuesto_pct / 100, 2)",
            persisted=True,
        ),
    )
    total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        Computed(
            "round(subtotal_mano_obra + subtotal_repuestos - descuento, 2)"
            " + round((subtotal_mano_obra + subtotal_repuestos - descuento)"
            " * impuesto_pct / 100, 2)",
            persisted=True,
        ),
    )

    estado: Mapped[EstadoPresupuesto] = mapped_column(
        _estado_sql, nullable=False, server_default=text("'borrador'")
    )
    valido_hasta: Mapped[date | None] = mapped_column(Date, server_default=FetchedValue())

    #: Identificador opaco del enlace que recibe el cliente. No se expone por
    #: RLS: lo resuelve un endpoint público con el rol de servicio.
    token_publico: Mapped[str] = mapped_column(Text, server_default=FetchedValue())

    enviado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    respondido_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comentario_cliente: Mapped[str | None] = mapped_column(Text)
    creado_por: Mapped[UUID | None] = mapped_column(ForeignKey("perfiles.id"))

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    autor: Mapped[Perfil | None] = relationship(lazy="raise")
    items: Mapped[list["PresupuestoItem"]] = relationship(
        back_populates="presupuesto",
        lazy="raise",
        cascade="all, delete-orphan",
        order_by="PresupuestoItem.orden_visual",
    )

    def __repr__(self) -> str:
        return f"<Presupuesto v{self.version} {self.estado}>"


class PresupuestoItem(Base):
    """Fotografía de una línea al momento de emitir."""

    __tablename__ = "presupuesto_items"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    taller_id: Mapped[UUID] = mapped_column(nullable=False)
    presupuesto_id: Mapped[UUID] = mapped_column(ForeignKey("presupuestos.id"), nullable=False)

    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    cantidad: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), Computed("round(cantidad * precio_unitario, 2)", persisted=True)
    )
    orden_visual: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    presupuesto: Mapped[Presupuesto] = relationship(back_populates="items", lazy="raise")
