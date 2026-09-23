"""Mapeo de la tabla `perfiles`.

Un perfil es una persona del taller: su nombre, su rol y si sigue de alta. La
cuenta con la que entra vive en `auth.users` y comparte identificador, así que
la relación es 1 a 1 y el `id` es el mismo en las dos.

Refleja `supabase/migrations/20260907000200_talleres_perfiles.sql` y la columna
`email` que añade `20260916000100_perfiles_email.sql`.
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
    #: Copia del correo de `auth.users`, para poder listarlo bajo RLS: las
    #: políticas de este proyecto no alcanzan el esquema de Auth. Lo mantiene el
    #: backend al crear al usuario y al cambiarle el correo de acceso.
    email: Mapped[str | None] = mapped_column(Text)
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
