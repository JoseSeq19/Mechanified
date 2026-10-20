"""Esquemas de la organización y de la cuenta del sitio.

Las validaciones repiten a propósito los `check` de la migración, por la misma
razón que en `talleres/schemas.py`: que quien llena el formulario reciba "el
nombre es demasiado corto" y no el nombre de una restricción de Postgres.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.roles import Rol
from app.modules.organizaciones.models import EstadoSolicitud

Nombre = Annotated[str, Field(min_length=2, max_length=120)]


def _limpiar(valor: object) -> object:
    """Recorta espacios y convierte la cadena vacía en None."""
    if isinstance(valor, str):
        return valor.strip() or None
    return valor


class OrganizacionRespuesta(BaseModel):
    """La organización de la sesión: lo que necesita la aplicación para
    presentarse con el nombre del cliente y no con el del producto."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre: str
    slug: str


class OrganizacionNueva(BaseModel):
    """Alta por cuenta propia: la organización, su primera sede y quien la
    administra, que es quien la está creando.

    Lo de dinero es opcional y se puede cambiar después en Configuración. Se
    ofrece aquí porque es lo primero que se nota mal configurado: un presupuesto
    en la moneda equivocada.
    """

    nombre: Nombre
    #: La primera sede. Si no se indica, se llama como la organización, que es
    #: lo natural para un taller independiente.
    sede: Nombre | None = None
    #: De quien la crea, que queda como su administrador.
    nombre_completo: Nombre
    telefono: Annotated[str, Field(max_length=40)] | None = None

    moneda: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] = "USD"
    tarifa_hora_default: Annotated[Decimal, Field(ge=0, le=Decimal("9999999999.99"))] = Decimal(0)
    impuesto_pct: Annotated[Decimal, Field(ge=0, le=100)] = Decimal(0)

    @field_validator("nombre", "nombre_completo", mode="before")
    @classmethod
    def _sin_espacios(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @field_validator("sede", "telefono", mode="before")
    @classmethod
    def _opcionales(cls, v: object) -> object:
        return _limpiar(v)

    @field_validator("moneda", mode="before")
    @classmethod
    def _moneda(cls, v: object) -> object:
        return v.strip().upper() if isinstance(v, str) else v


class SolicitudNueva(BaseModel):
    """Pedir que la cree el equipo. El correo no se pide: es el de la cuenta."""

    nombre_organizacion: Nombre
    nombre_contacto: Nombre
    telefono: Annotated[str, Field(max_length=40)] | None = None
    #: Cuántas sedes tiene. Orienta al equipo sobre el tamaño del alta.
    sedes: Annotated[int, Field(ge=1, le=999)] | None = None
    mensaje: Annotated[str, Field(max_length=2000)] | None = None

    @field_validator("nombre_organizacion", "nombre_contacto", mode="before")
    @classmethod
    def _sin_espacios(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @field_validator("telefono", "mensaje", mode="before")
    @classmethod
    def _opcionales(cls, v: object) -> object:
        return _limpiar(v)


class SolicitudRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre_organizacion: str
    estado: EstadoSolicitud
    creado_en: datetime
    atendida_en: datetime | None


class PertenenciaCuenta(BaseModel):
    """Dónde está la cuenta: su organización, su sede y su rol."""

    organizacion_id: UUID
    organizacion_nombre: str
    taller_id: UUID
    taller_nombre: str
    rol: Rol
    #: False si la administración la dio de baja. Entonces la aplicación no le
    #: acepta nada, aunque la cuenta siga existiendo.
    activo: bool


class EstadoCuenta(BaseModel):
    """Lo que el sitio necesita para decidir qué ofrecerle a alguien.

    Sin organización y sin solicitud: crearla o pedirla. Con solicitud
    pendiente: esperar al equipo. Con organización: descargar y entrar.
    """

    email: str | None
    organizacion: PertenenciaCuenta | None
    #: La última que mandó, si mandó alguna.
    solicitud: SolicitudRespuesta | None
