"""Verificación de los tokens emitidos por Supabase Auth.

La firma se comprueba **localmente** contra la llave pública del JWKS. No hay
llamada de red a Supabase por request: PyJWKClient cachea las llaves y solo
vuelve a pedirlas cuando aparece un `kid` desconocido (rotación).

De aquí sale el `UsuarioAutenticado` que arrastra el resto de la aplicación, y
en particular `taller_id` y `rol`, que son los claims que se inyectan en la
sesión de base de datos para que RLS pueda evaluarse.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import Configuracion, obtener_configuracion
from app.core.exceptions import ErrorAutenticacion, ErrorConfiguracion
from app.core.roles import Rol


@dataclass(frozen=True, slots=True)
class UsuarioAutenticado:
    """Identidad resuelta a partir del token. Inmutable a propósito."""

    id: UUID
    taller_id: UUID
    rol: Rol
    email: str | None = None

    @property
    def claims_rls(self) -> dict[str, str]:
        """Claims que se inyectan en la sesión de Postgres.

        Son exactamente los que leen mch_taller_actual() y mch_rol_actual().
        """
        return {
            "sub": str(self.id),
            "role": "authenticated",
            "taller_id": str(self.taller_id),
            "rol": self.rol.value,
        }


@lru_cache
def _cliente_jwks(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, lifespan=3600)


def _llave_de_verificacion(token: str, cfg: Configuracion) -> Any:
    """Llave pública del JWKS, o el secreto compartido si el proyecto usa HS256."""
    encabezado = jwt.get_unverified_header(token)
    algoritmo = encabezado.get("alg", "")

    if algoritmo == "HS256":
        if not cfg.supabase_jwt_secret:
            raise ErrorConfiguracion(
                "El token está firmado con HS256 pero MCH_SUPABASE_JWT_SECRET está vacío."
            )
        return cfg.supabase_jwt_secret

    try:
        return _cliente_jwks(cfg.jwks_url).get_signing_key_from_jwt(token).key
    except Exception as exc:
        raise ErrorAutenticacion(f"No se pudo obtener la llave de firma: {exc}") from exc


def decodificar_token(token: str, cfg: Configuracion) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            key=_llave_de_verificacion(token, cfg),
            algorithms=cfg.jwt_algoritmos,
            audience=cfg.jwt_audiencia,
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ErrorAutenticacion("El token expiró. Renueva la sesión.") from exc
    except jwt.InvalidTokenError as exc:
        raise ErrorAutenticacion(f"Token inválido: {exc}") from exc


def usuario_desde_claims(claims: dict[str, Any]) -> UsuarioAutenticado:
    """Convierte los claims en identidad, exigiendo los de tenant.

    Un token válido pero sin `taller_id` significa casi siempre que el hook de
    Auth no está activo. Sin esos claims, RLS deniega absolutamente todo, así
    que conviene fallar aquí con un mensaje que apunte a la causa real en vez de
    dejar que el usuario vea listados vacíos sin explicación.
    """
    taller_id = claims.get("taller_id") or claims.get("app_metadata", {}).get("taller_id")
    rol_bruto = claims.get("rol") or claims.get("app_metadata", {}).get("rol")

    if not taller_id or not rol_bruto:
        raise ErrorAutenticacion(
            "El token no trae los claims 'taller_id' y 'rol'. Suele significar que el "
            "hook de Auth (mch_hook_access_token) no está activo en el proyecto de "
            "Supabase, o que el usuario no tiene perfil activo.",
        )

    try:
        rol = Rol(rol_bruto)
    except ValueError as exc:
        raise ErrorAutenticacion(f"Rol desconocido en el token: {rol_bruto!r}") from exc

    try:
        return UsuarioAutenticado(
            id=UUID(str(claims["sub"])),
            taller_id=UUID(str(taller_id)),
            rol=rol,
            email=claims.get("email"),
        )
    except (KeyError, ValueError) as exc:
        raise ErrorAutenticacion("El token no identifica a un usuario válido.") from exc


#: Declarar el esquema en vez de leer el encabezado a mano tiene un efecto
#: práctico: FastAPI lo publica en el OpenAPI y /docs muestra el botón
#: "Authorize", así que se puede probar la API desde el navegador pegando un
#: token. `auto_error=False` deja que el 401 lo emita nuestro manejador, con el
#: mismo formato de error que el resto de la API.
esquema_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="Supabase Auth",
    description="Token de acceso de Supabase Auth (el `access_token` del login).",
)


async def usuario_actual(
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(esquema_bearer)] = None,
    cfg: Configuracion = Depends(obtener_configuracion),
) -> UsuarioAutenticado:
    """Dependencia base: todo endpoint autenticado la usa."""
    if credenciales is None or credenciales.scheme.lower() != "bearer":
        raise ErrorAutenticacion("Falta el encabezado Authorization: Bearer <token>.")

    return usuario_desde_claims(decodificar_token(credenciales.credentials, cfg))
