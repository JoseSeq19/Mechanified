"""Esquemas de usuarios del taller."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.roles import Rol


class UsuarioRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre_completo: str
    rol: Rol
    rol_etiqueta: str
    telefono: str | None
    activo: bool
