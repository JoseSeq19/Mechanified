"""Mapeo del catálogo de repuestos y de las piezas cargadas a una orden.

Refleja `supabase/migrations/20260907000600_repuestos.sql`.

`OrdenRepuesto.repuesto_id` es opcional a propósito: en un taller real buena
parte de las piezas se compran para un trabajo puntual y no vale la pena darlas
de alta en el catálogo. Cuando es NULL, la línea se sostiene con su propia
descripción y precio.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.usuarios.models import Perfil
from app.shared.modelo import Base


class EstadoItemRepuesto(StrEnum):
    """Refleja el enum `public.estado_item_repuesto`.

    El recorrido habitual es solicitado → cotizado → aprobado → recibido →
    instalado, pero **no se aplica como máquina de estados**, a diferencia de la
    orden. Una pieza puede llegar equivocada del proveedor y volver a
    `solicitado`, o cotizarse dos veces. Imponer un orden aquí daría más peleas
    que garantías.
    """

    SOLICITADO = "solicitado"
    COTIZADO = "cotizado"
    APROBADO = "aprobado"
    RECIBIDO = "recibido"
    INSTALADO = "instalado"

    @property
    def etiqueta(self) -> str:
        return {
            "solicitado": "Solicitado",
            "cotizado": "Cotizado",
            "aprobado": "Aprobado",
            "recibido": "Recibido",
            "instalado": "Instalado",
        }[self.value]


_estado_sql = Enum(
    EstadoItemRepuesto,
    name="estado_item_repuesto",
    native_enum=True,
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class Repuesto(Base):
    """Una pieza del catálogo del taller."""

    __tablename__ = "repuestos"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    taller_id: Mapped[UUID] = mapped_column(nullable=False)

    sku: Mapped[str] = mapped_column(Text, nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    categoria: Mapped[str | None] = mapped_column(Text)
    unidad: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'unidad'"))

    costo: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    precio_venta: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    #: Informativo. Mechanified no lleva movimientos de inventario todavía: el
    #: stock no se descuenta solo al instalar una pieza.
    stock: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    stock_minimo: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    proveedor: Mapped[str | None] = mapped_column(Text)

    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @property
    def bajo_minimo(self) -> bool:
        return self.stock <= self.stock_minimo

    def __repr__(self) -> str:
        return f"<Repuesto {self.sku} {self.nombre!r}>"


class OrdenRepuesto(Base):
    """Una pieza cargada a una orden.

    `precio_unitario` se copia del catálogo al agregarla y queda fijo: cambiar
    la lista de precios no puede alterar lo que ya se cotizó.
    """

    __tablename__ = "orden_repuestos"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    taller_id: Mapped[UUID] = mapped_column(nullable=False)
    orden_id: Mapped[UUID] = mapped_column(ForeignKey("ordenes_servicio.id"), nullable=False)
    repuesto_id: Mapped[UUID | None] = mapped_column(ForeignKey("repuestos.id"))

    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    cantidad: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), Computed("round(cantidad * precio_unitario, 2)", persisted=True)
    )

    estado: Mapped[EstadoItemRepuesto] = mapped_column(
        _estado_sql, nullable=False, server_default=text("'solicitado'")
    )
    notas: Mapped[str | None] = mapped_column(Text)
    solicitado_por: Mapped[UUID | None] = mapped_column(ForeignKey("perfiles.id"))

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    repuesto: Mapped[Repuesto | None] = relationship(lazy="raise")
    solicitante: Mapped[Perfil | None] = relationship(lazy="raise")

    def __repr__(self) -> str:
        return f"<OrdenRepuesto {self.descripcion!r} x{self.cantidad}>"
