"""Esquemas de usuarios del taller.

La contraseña aparece en exactamente un sitio de todo el proyecto: en la
respuesta del alta y en la del restablecimiento, para enseñarla una vez a quien
tiene que entregarla. No se guarda, no se vuelve a consultar y no hay endpoint
que la devuelva.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.roles import Rol

_Nombre = Annotated[str, Field(min_length=2, max_length=120)]
_Telefono = Annotated[str, Field(max_length=40)]


def _limpiar(v: object) -> object:
    if isinstance(v, str):
        return v.strip() or None
    return v


class UsuarioCrear(BaseModel):
    """Alta de una persona del taller: cuenta de acceso y perfil, de una vez."""

    nombre_completo: _Nombre
    email: EmailStr
    rol: Rol
    telefono: _Telefono | None = None

    @field_validator("nombre_completo", mode="before")
    @classmethod
    def _nombre_limpio(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @field_validator("telefono", mode="before")
    @classmethod
    def _telefono_limpio(cls, v: object) -> object:
        return _limpiar(v)


class UsuarioEditar(BaseModel):
    """Todo opcional: es un PATCH.

    El correo no está aquí: cambiarlo toca también la cuenta de acceso y tiene
    su propio endpoint, para que no se cuele en un guardado de rutina.
    """

    nombre_completo: _Nombre | None = None
    telefono: _Telefono | None = None
    rol: Rol | None = None
    activo: bool | None = None

    @field_validator("telefono", mode="before")
    @classmethod
    def _telefono_limpio(cls, v: object) -> object:
        return _limpiar(v)


class CorreoNuevo(BaseModel):
    email: EmailStr


class UsuarioRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre_completo: str
    #: Copia del correo de la cuenta. Ver la migración 20260916000100.
    email: str | None
    rol: Rol
    rol_etiqueta: str
    telefono: str | None
    activo: bool
    creado_en: datetime | None = None


class UsuarioCreado(UsuarioRespuesta):
    """El alta, con la contraseña temporal que solo se muestra esta vez."""

    clave_temporal: str


class ClaveTemporal(BaseModel):
    clave_temporal: str
