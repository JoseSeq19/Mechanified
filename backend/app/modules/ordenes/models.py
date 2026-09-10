"""Mapeo de `ordenes_servicio` y `orden_eventos`.

Refleja `supabase/migrations/20260907000400_ordenes.sql`.

Dos columnas no se escriben nunca desde aquí, porque las pone la base:

  - `folio`, que asigna un trigger tomando el siguiente número de la secuencia
    del taller, con bloqueo de fila para que dos altas simultáneas no choquen.
  - `total`, que es una columna generada a partir de los dos subtotales, y esos
    los mantiene al día otro trigger cada vez que cambia una línea.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Computed,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.clientes.models import Cliente
from app.modules.ordenes.estados import EstadoOrden
from app.modules.usuarios.models import Perfil
from app.modules.vehiculos.models import Vehiculo
from app.shared.modelo import Base

_estado_sql = Enum(
    EstadoOrden,
    name="estado_orden",
    native_enum=True,
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class OrdenServicio(Base):
    __tablename__ = "ordenes_servicio"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    taller_id: Mapped[UUID] = mapped_column(nullable=False)

    #: Legible y único por taller ("DLT-00042"). Lo asigna el trigger
    #: mch_ordenes_guard tomando el correlativo del taller. `FetchedValue` le
    #: dice a SQLAlchemy que no lo incluya en el INSERT y que lo lea después.
    folio: Mapped[str] = mapped_column(Text, server_default=FetchedValue())

    cliente_id: Mapped[UUID] = mapped_column(ForeignKey("clientes.id"), nullable=False)
    vehiculo_id: Mapped[UUID] = mapped_column(ForeignKey("vehiculos.id"), nullable=False)
    asesor_id: Mapped[UUID | None] = mapped_column(ForeignKey("perfiles.id"))
    tecnico_id: Mapped[UUID | None] = mapped_column(ForeignKey("perfiles.id"))

    estado: Mapped[EstadoOrden] = mapped_column(_estado_sql, nullable=False)

    motivo_ingreso: Mapped[str] = mapped_column(Text, nullable=False)
    kilometraje_ingreso: Mapped[int | None] = mapped_column(Integer)
    nivel_combustible: Mapped[int | None] = mapped_column(Integer)
    inventario_ingreso: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    fecha_ingreso: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fecha_promesa: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fecha_entrega: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Los mantiene al día un trigger cada vez que cambia una línea de mano de
    # obra o de repuestos. Declarar el `server_default` es lo que impide que
    # SQLAlchemy los incluya como NULL en el INSERT.
    total_mano_obra: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    total_repuestos: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    #: Columna generada en Postgres. Sin `Computed`, SQLAlchemy la mete en el
    #: INSERT y Postgres responde "cannot insert a non-DEFAULT value into
    #: column total".
    total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), Computed("total_mano_obra + total_repuestos", persisted=True)
    )

    notas_internas: Mapped[str | None] = mapped_column(Text)
    motivo_cancelacion: Mapped[str | None] = mapped_column(Text)
    creado_por: Mapped[UUID | None] = mapped_column(ForeignKey("perfiles.id"))

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    cliente: Mapped[Cliente] = relationship(lazy="raise")
    vehiculo: Mapped[Vehiculo] = relationship(lazy="raise")
    asesor: Mapped[Perfil | None] = relationship(lazy="raise", foreign_keys=[asesor_id])
    tecnico: Mapped[Perfil | None] = relationship(lazy="raise", foreign_keys=[tecnico_id])

    def __repr__(self) -> str:
        return f"<OrdenServicio {self.folio} {self.estado}>"


class OrdenEvento(Base):
    """Bitácora de transiciones. Solo lectura: la escribe un trigger.

    De aquí salen las métricas de tiempo del dashboard, así que no se edita ni
    se borra: no hay política RLS que lo permita.
    """

    __tablename__ = "orden_eventos"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    taller_id: Mapped[UUID] = mapped_column(nullable=False)
    orden_id: Mapped[UUID] = mapped_column(ForeignKey("ordenes_servicio.id"), nullable=False)

    estado_anterior: Mapped[EstadoOrden | None] = mapped_column(_estado_sql)
    estado_nuevo: Mapped[EstadoOrden] = mapped_column(_estado_sql, nullable=False)

    #: NULL cuando quien hizo el cambio ya no tiene perfil en el taller.
    #: Ver la migración 20260909000200.
    usuario_id: Mapped[UUID | None] = mapped_column(ForeignKey("perfiles.id"))
    comentario: Mapped[str | None] = mapped_column(Text)

    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    usuario: Mapped[Perfil | None] = relationship(lazy="raise")
