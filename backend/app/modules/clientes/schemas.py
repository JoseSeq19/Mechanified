"""Esquemas de entrada y salida de clientes.

Los tres esquemas de escritura son distintos a propósito:

- `ClienteCrear`   exige nombre y fija el resto por omisión.
- `ClienteEditar`  tiene todo opcional, para PATCH parcial.
- `ClienteRespuesta` añade lo que genera el servidor y nunca se acepta de fuera.

En particular `taller_id` **no aparece en ningún esquema de entrada**. Se toma
siempre del token. Aunque RLS rechazaría un taller ajeno, aceptar el campo
invitaría a intentarlo y convertiría un error de programación en un 403 confuso.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.clientes.models import TipoCliente

_Nombre = Annotated[str, Field(min_length=2, max_length=160)]
_Texto = Annotated[str, Field(max_length=500)]


def _limpiar(valor: str | None) -> str | None:
    """Recorta espacios y convierte la cadena vacía en NULL.

    Un formulario web envía "" cuando el usuario no llena un campo opcional.
    Guardarlo como cadena vacía rompería el índice único parcial de `documento`,
    que solo ignora los NULL: dos clientes sin documento chocarían entre sí.
    """
    if valor is None:
        return None
    limpio = valor.strip()
    return limpio or None


class ClienteBase(BaseModel):
    tipo: TipoCliente = TipoCliente.PERSONA
    documento: Annotated[str, Field(max_length=40)] | None = None
    telefono: Annotated[str, Field(max_length=40)] | None = None
    email: EmailStr | None = None
    direccion: _Texto | None = None
    notas: _Texto | None = None

    @field_validator("documento", "telefono", "direccion", "notas", mode="before")
    @classmethod
    def _normalizar(cls, v: object) -> object:
        return _limpiar(v) if isinstance(v, str) or v is None else v

    @field_validator("email", mode="before")
    @classmethod
    def _email_vacio_es_nulo(cls, v: object) -> object:
        # EmailStr rechazaría "", que es lo que manda un formulario vacío.
        return _limpiar(v) if isinstance(v, str) or v is None else v


class ClienteCrear(ClienteBase):
    nombre: _Nombre

    @field_validator("nombre", mode="before")
    @classmethod
    def _nombre_sin_espacios(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class ClienteEditar(BaseModel):
    """Todo opcional: es un PATCH.

    `model_dump(exclude_unset=True)` distingue "no lo mandaron" de "lo mandaron
    en null", que es lo que permite borrar un campo opcional a propósito.
    """

    nombre: _Nombre | None = None
    tipo: TipoCliente | None = None
    documento: Annotated[str, Field(max_length=40)] | None = None
    telefono: Annotated[str, Field(max_length=40)] | None = None
    email: EmailStr | None = None
    direccion: _Texto | None = None
    notas: _Texto | None = None
    activo: bool | None = None

    @field_validator("nombre", mode="before")
    @classmethod
    def _nombre_sin_espacios(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @field_validator("documento", "telefono", "direccion", "notas", "email", mode="before")
    @classmethod
    def _normalizar(cls, v: object) -> object:
        return _limpiar(v) if isinstance(v, str) or v is None else v


class ClienteRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    taller_id: UUID
    tipo: TipoCliente
    nombre: str
    documento: str | None
    telefono: str | None
    email: str | None
    direccion: str | None
    notas: str | None
    activo: bool
    creado_en: datetime
    actualizado_en: datetime
