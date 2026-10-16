"""Mapeo de la tabla `adjuntos`.

Aquí solo viven los **metadatos**. El archivo está en el bucket privado
`mch-evidencias` de Supabase Storage, y esta fila guarda dónde, quién lo subió y
a qué momento de la orden pertenece.

Está partido así porque son dos sistemas con dos barreras distintas que tienen
que decir lo mismo: la fila la protege RLS por `taller_id`, y el objeto lo
protege la política del bucket comparando la primera carpeta de su ruta contra
el taller de quien pide. El trigger `mch_adjuntos_ruta_guard` es el que impide
que las dos se contradigan.

Refleja `supabase/migrations/20260907001000_adjuntos.sql`.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.usuarios.models import Perfil
from app.shared.modelo import Base


class ContextoAdjunto(StrEnum):
    """Refleja el enum `public.contexto_adjunto`.

    Es el momento de la orden al que pertenece el archivo, y sirve para lo que
    de verdad se hace con las fotos: comparar el estado del vehículo al recibirlo
    con el de la entrega.
    """

    INGRESO = "ingreso"
    DIAGNOSTICO = "diagnostico"
    REPARACION = "reparacion"
    CALIDAD = "calidad"
    ENTREGA = "entrega"

    @property
    def etiqueta(self) -> str:
        return {
            "ingreso": "Recepción",
            "diagnostico": "Diagnóstico",
            "reparacion": "Reparación",
            "calidad": "Control de calidad",
            "entrega": "Entrega",
        }[self.value]


_contexto_sql = Enum(
    ContextoAdjunto,
    name="contexto_adjunto",
    native_enum=True,
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class Adjunto(Base):
    __tablename__ = "adjuntos"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    taller_id: Mapped[UUID] = mapped_column(nullable=False)
    orden_id: Mapped[UUID] = mapped_column(
        ForeignKey("ordenes_servicio.id", ondelete="CASCADE"), nullable=False
    )

    contexto: Mapped[ContextoAdjunto] = mapped_column(
        _contexto_sql, nullable=False, server_default=text("'ingreso'")
    )
    #: `{taller_id}/{orden_id}/{uuid}-{nombre}`. La convención no es decorativa:
    #: la primera carpeta es lo que compara la política del bucket.
    ruta_storage: Mapped[str] = mapped_column(Text, nullable=False)
    nombre_archivo: Mapped[str] = mapped_column(Text, nullable=False)
    mime: Mapped[str | None] = mapped_column(Text)
    tamano_bytes: Mapped[int | None] = mapped_column(BigInteger)
    descripcion: Mapped[str | None] = mapped_column(Text)

    subido_por: Mapped[UUID | None] = mapped_column(ForeignKey("perfiles.id", ondelete="SET NULL"))
    autor: Mapped[Perfil | None] = relationship(Perfil, lazy="raise")

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Adjunto {self.nombre_archivo!r} orden={self.orden_id}>"
