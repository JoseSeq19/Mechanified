"""Mapeo de la tabla `clientes`.

Refleja lo que ya define `supabase/migrations/20260907000300_clientes_vehiculos.sql`.
No lo define: si aquí y allá difieren, manda la migración.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.modelo import Base


class TipoCliente(StrEnum):
    """Refleja el enum `public.tipo_cliente`.

    Vive en `models` y no en `schemas` porque su contrato lo fija la base de
    datos: los valores tienen que coincidir carácter por carácter con los del
    enum de Postgres.
    """

    PERSONA = "persona"
    EMPRESA = "empresa"


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))

    # No se expone para escritura en ningún esquema de entrada: siempre se toma
    # del token. Ver el comentario en service.crear().
    taller_id: Mapped[UUID] = mapped_column(nullable=False)

    tipo: Mapped[TipoCliente] = mapped_column(
        Enum(
            TipoCliente,
            name="tipo_cliente",
            native_enum=True,
            create_type=False,
            # Sin esto SQLAlchemy enviaría los NOMBRES del enum de Python
            # ('PERSONA') en lugar de sus valores ('persona'), y Postgres
            # rechazaría el INSERT.
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=text("'persona'"),
    )

    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    documento: Mapped[str | None] = mapped_column(Text)
    telefono: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    direccion: Mapped[str | None] = mapped_column(Text)
    notas: Mapped[str | None] = mapped_column(Text)

    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Cliente {self.nombre!r} taller={self.taller_id}>"
