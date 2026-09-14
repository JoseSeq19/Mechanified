"""Mapeo del checklist configurable y de los controles de calidad.

Refleja `supabase/migrations/20260907000800_calidad.sql`.

Como en los presupuestos, ejecutar un control **copia** los puntos de la
plantilla a `control_calidad_respuestas` en vez de referenciarlos. Así, editar
la plantilla más adelante no reescribe inspecciones ya hechas: una orden
entregada en marzo conserva la lista que se revisó en marzo.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.usuarios.models import Perfil
from app.shared.modelo import Base


class ResultadoCheck(StrEnum):
    """Refleja el enum `public.resultado_check`."""

    OK = "ok"
    NO_OK = "no_ok"
    NO_APLICA = "no_aplica"

    @property
    def etiqueta(self) -> str:
        return {"ok": "Conforme", "no_ok": "No conforme", "no_aplica": "No aplica"}[self.value]


class ResultadoControl(StrEnum):
    """Desenlace de una inspección. En la base es un `text` con CHECK."""

    PENDIENTE = "pendiente"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"

    @property
    def etiqueta(self) -> str:
        return {"pendiente": "En revisión", "aprobado": "Aprobado", "rechazado": "Rechazado"}[
            self.value
        ]


_resultado_sql = Enum(
    ResultadoCheck,
    name="resultado_check",
    native_enum=True,
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class Plantilla(Base):
    __tablename__ = "checklist_plantillas"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    taller_id: Mapped[UUID] = mapped_column(nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    puntos: Mapped[list["PlantillaItem"]] = relationship(
        back_populates="plantilla",
        lazy="raise",
        cascade="all, delete-orphan",
        order_by="PlantillaItem.orden_visual",
    )

    def __repr__(self) -> str:
        return f"<Plantilla {self.nombre!r}>"


class PlantillaItem(Base):
    __tablename__ = "checklist_plantilla_items"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    taller_id: Mapped[UUID] = mapped_column(nullable=False)
    plantilla_id: Mapped[UUID] = mapped_column(
        ForeignKey("checklist_plantillas.id"), nullable=False
    )

    categoria: Mapped[str | None] = mapped_column(Text)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    #: Un punto obligatorio sin conformidad impide aprobar el control. Lo
    #: comprueba mch_controles_calidad_cierre, no la aplicación.
    obligatorio: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    orden_visual: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    plantilla: Mapped[Plantilla] = relationship(back_populates="puntos", lazy="raise")


class Control(Base):
    __tablename__ = "controles_calidad"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    taller_id: Mapped[UUID] = mapped_column(nullable=False)
    orden_id: Mapped[UUID] = mapped_column(ForeignKey("ordenes_servicio.id"), nullable=False)
    plantilla_id: Mapped[UUID | None] = mapped_column(ForeignKey("checklist_plantillas.id"))
    inspector_id: Mapped[UUID | None] = mapped_column(ForeignKey("perfiles.id"))

    resultado: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pendiente'"))
    observaciones: Mapped[str | None] = mapped_column(Text)

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    cerrado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    inspector: Mapped[Perfil | None] = relationship(lazy="raise")
    respuestas: Mapped[list["Respuesta"]] = relationship(
        back_populates="control",
        lazy="raise",
        cascade="all, delete-orphan",
        order_by="Respuesta.orden_visual",
    )

    def __repr__(self) -> str:
        return f"<Control orden={self.orden_id} {self.resultado}>"


class Respuesta(Base):
    """Un punto revisado. Copia de la plantilla, no referencia viva."""

    __tablename__ = "control_calidad_respuestas"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    taller_id: Mapped[UUID] = mapped_column(nullable=False)
    control_id: Mapped[UUID] = mapped_column(ForeignKey("controles_calidad.id"), nullable=False)
    #: Se conserva para poder saber si el punto era obligatorio; puede quedar en
    #: NULL si alguien borra el punto de la plantilla después.
    item_id: Mapped[UUID | None] = mapped_column(ForeignKey("checklist_plantilla_items.id"))

    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    resultado: Mapped[ResultadoCheck] = mapped_column(
        _resultado_sql, nullable=False, server_default=text("'no_aplica'")
    )
    comentario: Mapped[str | None] = mapped_column(Text)
    evidencia_url: Mapped[str | None] = mapped_column(Text)
    orden_visual: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    control: Mapped[Control] = relationship(back_populates="respuestas", lazy="raise")
    #: Se consulta para saber si el punto era obligatorio. Queda en None si
    #: alguien borró el punto de la plantilla después de la inspección, y en ese
    #: caso deja de bloquear la aprobación: el mismo criterio que usa el trigger.
    item: Mapped[PlantillaItem | None] = relationship(lazy="raise")
