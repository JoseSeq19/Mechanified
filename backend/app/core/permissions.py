"""Autorización por rol para los endpoints.

Aclaración importante sobre el alcance de este módulo: **no es la barrera de
seguridad**. Quien impide de verdad que un técnico borre un cliente son las
políticas RLS de Postgres, que se aplican aunque alguien escriba directo contra
la base saltándose esta API.

Lo que hace este módulo es rechazar antes y con un mensaje entendible lo que la
base rechazaría después con un `42501` seco. Es una capa de experiencia de uso
sobre una barrera que ya existe, no la barrera.

Por eso los grupos de abajo son deliberadamente gruesos: cubren el acceso a
nivel de recurso, no las reglas finas. Las finas —qué transición de estado puede
hacer cada rol, si un presupuesto ya enviado admite cambios— viven en la base,
en un solo sitio, y no se duplican aquí para que no puedan desincronizarse.
"""

from collections.abc import Callable

from fastapi import Depends

from app.core.exceptions import ErrorPermiso
from app.core.roles import TODOS, Rol
from app.core.security import UsuarioAutenticado, usuario_actual

__all__ = ["TODOS", "Rol", "inventario", "recepcion", "requiere_rol", "solo_admin", "taller"]


def requiere_rol(*roles: Rol) -> Callable[..., object]:
    """Construye una dependencia que exige uno de los roles indicados."""
    permitidos = frozenset(roles)

    async def verificar(
        usuario: UsuarioAutenticado = Depends(usuario_actual),
    ) -> UsuarioAutenticado:
        if usuario.rol not in permitidos:
            esperados = ", ".join(sorted(r.etiqueta for r in permitidos))
            raise ErrorPermiso(
                f"Esta acción es para: {esperados}. Tu rol es {usuario.rol.etiqueta}.",
                {
                    "rol_actual": usuario.rol.value,
                    "roles_requeridos": sorted(r.value for r in permitidos),
                },
            )
        return usuario

    return verificar


#: Atajos para los agrupamientos que se repiten en los routers.
solo_admin = requiere_rol(Rol.ADMIN_TALLER)
recepcion = requiere_rol(Rol.ADMIN_TALLER, Rol.ASESOR_SERVICIO)
taller = requiere_rol(Rol.ADMIN_TALLER, Rol.ASESOR_SERVICIO, Rol.TECNICO)
inventario = requiere_rol(Rol.ADMIN_TALLER, Rol.ENCARGADO_REPUESTOS)
