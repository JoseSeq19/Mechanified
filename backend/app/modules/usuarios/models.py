"""Mapeo de la tabla `perfiles`.

El módulo de usuarios (alta, invitaciones, cambio de rol) todavía no existe,
pero el modelo sí hace falta: las órdenes referencian al asesor y al técnico
asignados, y la interfaz necesita mostrar sus nombres en vez de sus UUID.

Refleja `supabase/migrations/20260907000200_talleres_perfiles.sql`.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.roles import Rol
from app.shared.modelo import Base


class Perfil(Base):
    __tablename__ = "perfiles"

    #: Es también el id del usuario en `auth.users`: la relación es 1 a 1.
    id: Mapped[UUID] = mapped_column(primary_key=True)
    taller_id: Mapped[UUID] = mapped_column(nullable=False)

    nombre_completo: Mapped[str] = mapped_column(Text, nullable=False)
    telefono: Mapped[str | None] = mapped_column(Text)
    rol: Mapped[Rol] = mapped_column(
        Enum(
            Rol,
            name="rol_usuario",
            native_enum=True,
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Perfil {self.nombre_completo!r} {self.rol}>"
