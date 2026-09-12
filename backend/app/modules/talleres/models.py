"""Mapeo de la tabla `talleres`.

El módulo completo de talleres (configuración, alta) todavía no existe. El
modelo sí hace falta: al crear una línea de mano de obra hay que tomar la tarifa
por hora del taller si quien la registra no indica otra.

Refleja `supabase/migrations/20260907000200_talleres_perfiles.sql`.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, Integer, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.modelo import Base


class Taller(Base):
    __tablename__ = "talleres"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    #: Se muestran al cliente en el presupuesto que recibe por enlace, para que
    #: sepa a quién llamar si tiene dudas.
    telefono: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    direccion: Mapped[str | None] = mapped_column(Text)
    zona_horaria: Mapped[str] = mapped_column(Text, nullable=False)
    moneda: Mapped[str] = mapped_column(Text, nullable=False)

    tarifa_hora_default: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    impuesto_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("0")
    )
    prefijo_orden: Mapped[str] = mapped_column(Text, nullable=False)
    dias_validez_presupuesto: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("15")
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    def __repr__(self) -> str:
        return f"<Taller {self.nombre!r}>"
