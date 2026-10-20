"""Mapeo de `organizaciones` y `solicitudes_organizacion`.

Refleja `supabase/migrations/20261020000100_organizaciones.sql`.
No lo define: si aquí y allá difieren, manda la migración.

La organización es el cliente de Mechanified y le da nombre al producto. No es
unidad de aislamiento: eso sigue siendo el taller, y por eso nada de este
módulo cuelga de `taller_id`.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, Enum, FetchedValue, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.modelo import Base


class Organizacion(Base):
    __tablename__ = "organizaciones"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=FetchedValue())
    #: El nombre con el que se presenta el producto a la gente de la organización.
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    creada_por: Mapped[UUID | None] = mapped_column()
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Organizacion {self.nombre!r}>"


class EstadoSolicitud(StrEnum):
    """Refleja el enum `public.estado_solicitud`."""

    PENDIENTE = "pendiente"
    ATENDIDA = "atendida"
    DESCARTADA = "descartada"


_estado_sql = Enum(
    EstadoSolicitud,
    name="estado_solicitud",
    native_enum=True,
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class SolicitudOrganizacion(Base):
    """Petición de alta que atiende el equipo de Mechanified.

    Tres columnas las pone siempre la base, la mande quien la mande: `email`
    (el de la cuenta, no uno escrito en el formulario), `estado` (nace
    pendiente) y `organizacion_id` (nace vacía). Por eso van como
    `FetchedValue` y el servicio no las escribe.
    """

    __tablename__ = "solicitudes_organizacion"
    #: Lo que pone la base se trae en el mismo INSERT, con RETURNING. Sin esto,
    #: leerlo después dispararía una consulta perezosa, que en asíncrono falla.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=FetchedValue())
    cuenta_id: Mapped[UUID] = mapped_column(nullable=False)
    email: Mapped[str] = mapped_column(Text, server_default=FetchedValue())
    nombre_contacto: Mapped[str] = mapped_column(Text, nullable=False)
    nombre_organizacion: Mapped[str] = mapped_column(Text, nullable=False)
    telefono: Mapped[str | None] = mapped_column(Text)
    sedes: Mapped[int | None] = mapped_column(Integer)
    mensaje: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[EstadoSolicitud] = mapped_column(_estado_sql, server_default=FetchedValue())
    organizacion_id: Mapped[UUID | None] = mapped_column(server_default=FetchedValue())
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atendida_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<SolicitudOrganizacion {self.nombre_organizacion!r} {self.estado}>"
