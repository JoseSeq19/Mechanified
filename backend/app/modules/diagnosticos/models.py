"""Mapeo del diagnóstico y de la mano de obra.

Refleja `supabase/migrations/20260907000500_diagnosticos.sql`.

Por qué están en el mismo módulo: las dos cosas son lo que el técnico registra
cuando abre el capó. El diagnóstico dice qué encontró; la mano de obra, cuánto
trabajo cuesta arreglarlo. En la práctica se capturan en la misma pantalla.

La mano de obra cuelga de la **orden**, no del diagnóstico: un trabajo puede
existir sin que nadie haya escrito un diagnóstico formal (un cambio de aceite no
lo necesita), y al revés, un diagnóstico puede no generar trabajo si el cliente
rechaza el presupuesto.
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
    Integer,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.usuarios.models import Perfil
from app.shared.modelo import Base


class SeveridadHallazgo(StrEnum):
    """Refleja el enum `public.severidad_hallazgo`."""

    LEVE = "leve"
    MODERADA = "moderada"
    CRITICA = "critica"

    @property
    def etiqueta(self) -> str:
        return {"leve": "Leve", "moderada": "Moderada", "critica": "Crítica"}[self.value]


_severidad_sql = Enum(
    SeveridadHallazgo,
    name="severidad_hallazgo",
    native_enum=True,
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class Diagnostico(Base):
    """Cabecera. Se admite más de uno por orden.

    Cuando aparece trabajo adicional con el vehículo ya abierto, se registra un
    diagnóstico nuevo en vez de editar el original, que ya respalda un
    presupuesto que el cliente aprobó.
    """

    __tablename__ = "diagnosticos"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    taller_id: Mapped[UUID] = mapped_column(nullable=False)
    orden_id: Mapped[UUID] = mapped_column(ForeignKey("ordenes_servicio.id"), nullable=False)
    tecnico_id: Mapped[UUID | None] = mapped_column(ForeignKey("perfiles.id"))

    resumen: Mapped[str] = mapped_column(Text, nullable=False)
    horas_estimadas: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, server_default=text("0")
    )

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    tecnico: Mapped[Perfil | None] = relationship(lazy="raise")
    hallazgos: Mapped[list["DiagnosticoHallazgo"]] = relationship(
        back_populates="diagnostico",
        lazy="raise",
        cascade="all, delete-orphan",
        order_by="DiagnosticoHallazgo.orden_visual",
    )

    def __repr__(self) -> str:
        return f"<Diagnostico orden={self.orden_id}>"


class DiagnosticoHallazgo(Base):
    """Cada cosa encontrada, por separado.

    No es un campo de texto libre porque cada hallazgo se cotiza y se aprueba
    por su cuenta: el cliente puede aceptar cambiar las pastillas y rechazar el
    amortiguador.
    """

    __tablename__ = "diagnostico_hallazgos"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    taller_id: Mapped[UUID] = mapped_column(nullable=False)
    diagnostico_id: Mapped[UUID] = mapped_column(ForeignKey("diagnosticos.id"), nullable=False)

    sistema: Mapped[str] = mapped_column(Text, nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    severidad: Mapped[SeveridadHallazgo] = mapped_column(
        _severidad_sql, nullable=False, server_default=text("'moderada'")
    )
    requiere_repuesto: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    orden_visual: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    diagnostico: Mapped[Diagnostico] = relationship(back_populates="hallazgos", lazy="raise")


class ManoObra(Base):
    """Una línea de trabajo cobrable.

    `subtotal` lo calcula Postgres (horas × tarifa), y un trigger mantiene al día
    los totales de la orden cada vez que esta tabla cambia.
    """

    __tablename__ = "orden_mano_obra"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    taller_id: Mapped[UUID] = mapped_column(nullable=False)
    orden_id: Mapped[UUID] = mapped_column(ForeignKey("ordenes_servicio.id"), nullable=False)

    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    horas: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    #: Se copia de talleres.tarifa_hora_default al crear la línea y queda fija:
    #: subir la tarifa del taller no debe alterar órdenes ya cotizadas.
    tarifa_hora: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), Computed("round(horas * tarifa_hora, 2)", persisted=True)
    )

    tecnico_id: Mapped[UUID | None] = mapped_column(ForeignKey("perfiles.id"))

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    tecnico: Mapped[Perfil | None] = relationship(lazy="raise")

    def __repr__(self) -> str:
        return f"<ManoObra {self.descripcion!r} {self.horas}h>"
