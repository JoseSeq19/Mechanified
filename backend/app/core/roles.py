"""El enum de roles, aislado en su propio módulo.

Vive aparte de `permissions` y de `security` porque ambos lo necesitan y cada
uno depende del otro: `security` construye la identidad (que incluye el rol) y
`permissions` declara dependencias que resuelven esa identidad. Con el enum
aquí, la dependencia queda en árbol y no en ciclo.
"""

from enum import StrEnum


class Rol(StrEnum):
    """Refleja el enum `public.rol_usuario` de la base de datos.

    Los valores tienen que coincidir carácter por carácter: se comparan contra
    el claim `rol` del token, que Postgres emite desde ese mismo enum.
    """

    ADMIN_TALLER = "admin_taller"
    ASESOR_SERVICIO = "asesor_servicio"
    TECNICO = "tecnico"
    ENCARGADO_REPUESTOS = "encargado_repuestos"

    @property
    def etiqueta(self) -> str:
        """Nombre para mostrar, en minúscula, para intercalar en mensajes."""
        return _ETIQUETAS[self]


_ETIQUETAS: dict[Rol, str] = {
    Rol.ADMIN_TALLER: "administrador del taller",
    Rol.ASESOR_SERVICIO: "asesor de servicio",
    Rol.TECNICO: "técnico",
    Rol.ENCARGADO_REPUESTOS: "encargado de repuestos",
}

TODOS: frozenset[Rol] = frozenset(Rol)
