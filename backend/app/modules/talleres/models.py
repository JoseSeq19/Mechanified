"""Mapeo de la tabla `talleres`.

El taller es el tenant: todo dato de negocio cuelga de una de estas filas. Esa
misma fila guarda la configuración con la que el resto del sistema calcula —
tarifa por hora, porcentaje de impuesto, días de validez del presupuesto— y los
datos de contacto que el cliente ve en el presupuesto que recibe por enlace.

Refleja `supabase/migrations/20260907000200_talleres_perfiles.sql`.
No lo define: si aquí y allá difieren, manda la migración.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Integer, Numeric, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.modelo import Base


class Taller(Base):
    __tablename__ = "talleres"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    #: Identificador único y global del taller. No se edita: es la clave por la
    #: que se le nombra desde fuera, y cambiarla no aporta nada hoy.
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    identificacion_fiscal: Mapped[str | None] = mapped_column(Text)
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
    logo_url: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Taller {self.nombre!r}>"
