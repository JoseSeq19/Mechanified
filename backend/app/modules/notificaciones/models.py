"""Mapeo de la cola de notificaciones.

Refleja `supabase/migrations/20260907000900_encuestas_notificaciones.sql` y la
política de encolado de `20260914000100`.

La idea de fondo: enviar correo no ocurre dentro de la transacción que mueve la
orden. Se deja una fila aquí y un worker la procesa. Si el proveedor de correo
está caído, la orden ya quedó guardada y el reintento es problema del worker, no
del asesor que estaba en el mostrador.

`datos` guarda **referencias**, no texto: qué presupuesto, qué encuesta. El
cuerpo del mensaje lo arma el worker leyendo la base al momento de enviar. Esa
separación es lo que hace que la política de RLS pueda dejar encolar a todo el
taller sin convertir la cola en un relé de correo abierto.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.modelo import Base


class CanalNotificacion(StrEnum):
    """Refleja el enum `public.canal_notificacion`."""

    EMAIL = "email"
    WEBHOOK = "webhook"


class EstadoNotificacion(StrEnum):
    """Refleja el enum `public.estado_notificacion`."""

    PENDIENTE = "pendiente"
    ENVIADA = "enviada"
    FALLIDA = "fallida"

    @property
    def etiqueta(self) -> str:
        return {"pendiente": "En cola", "enviada": "Entregado", "fallida": "No se pudo enviar"}[
            self.value
        ]


class PlantillaCorreo(StrEnum):
    """Los tres avisos que el taller manda al cliente.

    La lista está repetida en el CHECK de la tabla (migración 20260914000100), a
    propósito: si alguien encola una plantilla que el worker no sabe redactar, es
    mejor que Postgres lo rechace en el INSERT que descubrirlo al enviar.
    """

    PRESUPUESTO_ENVIADO = "presupuesto_enviado"
    VEHICULO_LISTO = "vehiculo_listo"
    ENCUESTA_SATISFACCION = "encuesta_satisfaccion"

    @property
    def etiqueta(self) -> str:
        return {
            "presupuesto_enviado": "Presupuesto para aprobar",
            "vehiculo_listo": "Vehículo listo para retirar",
            "encuesta_satisfaccion": "Encuesta de satisfacción",
        }[self.value]


_canal_sql = Enum(
    CanalNotificacion,
    name="canal_notificacion",
    native_enum=True,
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)

_estado_sql = Enum(
    EstadoNotificacion,
    name="estado_notificacion",
    native_enum=True,
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class Notificacion(Base):
    __tablename__ = "notificaciones"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    taller_id: Mapped[UUID] = mapped_column(nullable=False)
    #: La política de encolado exige que no sea nulo: sin orden no hay cliente
    #: contra el que validar el destinatario.
    orden_id: Mapped[UUID | None] = mapped_column(ForeignKey("ordenes_servicio.id"))

    canal: Mapped[CanalNotificacion] = mapped_column(
        _canal_sql, nullable=False, server_default=text("'email'")
    )
    destinatario: Mapped[str] = mapped_column(Text, nullable=False)
    #: Valor de `PlantillaCorreo`. En la base es `text` con CHECK, no un enum,
    #: porque sumar un aviso no debería obligar a alterar un tipo.
    plantilla: Mapped[str] = mapped_column(Text, nullable=False)
    datos: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    estado: Mapped[EstadoNotificacion] = mapped_column(
        _estado_sql, nullable=False, server_default=text("'pendiente'")
    )
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    ultimo_error: Mapped[str | None] = mapped_column(Text)

    #: Cuándo puede tomarla el worker. Al reclamarla se empuja hacia adelante,
    #: y eso mismo hace de arrendamiento: si el proceso muere a mitad del envío,
    #: la fila vuelve a estar disponible sola al vencer el plazo.
    programada_para: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    enviada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Notificacion {self.plantilla} {self.estado} -> {self.destinatario}>"
