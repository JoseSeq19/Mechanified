"""Mapeo de la tabla `encuestas`.

Refleja `supabase/migrations/20260907000900_encuestas_notificaciones.sql`.

Dos cosas las decide Postgres y por eso no se escriben desde aquí:

  - `token_publico`, el identificador opaco del enlace que recibe el cliente.
  - `respondida_en`, que sella un trigger la primera vez que llega una nota. Que
    lo ponga la base y no la aplicación es lo que hace que la fecha de respuesta
    sea la de la respuesta, y no la de la última vez que alguien tocó la fila.

Hay como mucho una encuesta por orden (índice único). Reenviarla no crea otra:
el enlace es el mismo y lo que cambia es `enviada_en`.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, FetchedValue, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.modelo import Base


class Encuesta(Base):
    __tablename__ = "encuestas"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=FetchedValue())
    taller_id: Mapped[UUID] = mapped_column(nullable=False)
    orden_id: Mapped[UUID] = mapped_column(ForeignKey("ordenes_servicio.id"), nullable=False)

    #: No se expone nunca por la API con sesión: es la llave del enlace público.
    token_publico: Mapped[str] = mapped_column(Text, server_default=FetchedValue())

    #: Cuándo salió el correo de verdad. Lo marca el worker al entregarlo, no el
    #: servicio al encolarlo: una encuesta encolada y nunca enviada no es enviada.
    enviada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    respondida_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    puntaje_atencion: Mapped[int | None] = mapped_column(Integer)
    puntaje_tiempo: Mapped[int | None] = mapped_column(Integer)
    puntaje_calidad: Mapped[int | None] = mapped_column(Integer)
    #: 0 a 10, la pregunta clásica de recomendación. De aquí sale el NPS.
    recomendaria: Mapped[int | None] = mapped_column(Integer)
    comentario: Mapped[str | None] = mapped_column(Text)

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @property
    def respondida(self) -> bool:
        return self.respondida_en is not None

    def __repr__(self) -> str:
        return f"<Encuesta orden={self.orden_id} respondida={self.respondida}>"
