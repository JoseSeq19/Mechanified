"""Mapeo de la tabla `vehiculos`.

Refleja `supabase/migrations/20260907000300_clientes_vehiculos.sql`.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.clientes.models import Cliente
from app.shared.modelo import Base


class Vehiculo(Base):
    __tablename__ = "vehiculos"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    taller_id: Mapped[UUID] = mapped_column(nullable=False)
    cliente_id: Mapped[UUID] = mapped_column(ForeignKey("clientes.id"), nullable=False)

    placa: Mapped[str] = mapped_column(Text, nullable=False)
    vin: Mapped[str | None] = mapped_column(Text)
    marca: Mapped[str] = mapped_column(Text, nullable=False)
    modelo: Mapped[str] = mapped_column(Text, nullable=False)
    anio: Mapped[int | None] = mapped_column(Integer)
    color: Mapped[str | None] = mapped_column(Text)
    tipo_combustible: Mapped[str | None] = mapped_column(Text)
    transmision: Mapped[str | None] = mapped_column(Text)
    kilometraje_ultimo: Mapped[int | None] = mapped_column(Integer)
    notas: Mapped[str | None] = mapped_column(Text)

    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # `lazy="raise"` a propósito: en código asíncrono una carga perezosa
    # accidental revienta con un error difícil de leer. Así el fallo aparece al
    # escribir la consulta, no en producción, y obliga a pedir el dato con un
    # selectinload explícito.
    cliente: Mapped[Cliente] = relationship(lazy="raise")

    def __repr__(self) -> str:
        return f"<Vehiculo {self.placa!r} {self.marca} {self.modelo}>"
