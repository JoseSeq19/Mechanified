"""Alta y baja de cuentas en Supabase Auth.

Es el único sitio del backend que usa la llave de servicio dentro de una
petición de usuario, y conviene ser explícito sobre por qué se puede: **no toca
ninguna tabla de negocio**. Habla con la API de administración de Auth, que vive
fuera de Postgres y por lo tanto fuera del alcance de RLS. Crear una cuenta es
literalmente imposible sin ella —nadie más puede escribir en `auth.users`— y el
perfil, que sí es dato de negocio, se inserta aparte con la sesión del
administrador y bajo sus políticas.

Está detrás de un `Protocol` por dos razones. La primera, que las pruebas puedan
sustituirlo. La segunda, más de fondo: si algún día el proyecto deja de
autenticar con Supabase, este archivo es lo único que habría que reescribir.

Sobre las contraseñas: el backend **no las guarda**. Genera una temporal, se la
devuelve una sola vez a quien dio el alta para que se la entregue a la persona,
y a partir de ahí solo existe cifrada dentro de Supabase.
"""

import logging
import secrets
from typing import Any, Protocol
from uuid import UUID

import httpx

from app.core.config import Configuracion, obtener_configuracion
from app.core.exceptions import ErrorConfiguracion, ErrorConflicto, ErrorValidacion

_log = logging.getLogger(__name__)

#: Alfabeto sin caracteres que se confunden al dictar: ni O/0, ni l/1/I. Una
#: clave temporal se transcribe a mano más veces de las que parece.
_ALFABETO = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"

#: Cuatro grupos de cuatro: entropía de sobra para algo que se usa una vez, y se
#: lee en voz alta sin errores.
_GRUPOS = 4
_LARGO_GRUPO = 4

_TIEMPO_LIMITE = 20


def generar_clave() -> str:
    """Contraseña temporal, pensada para dictarse una vez y cambiarse después."""
    return "-".join(
        "".join(secrets.choice(_ALFABETO) for _ in range(_LARGO_GRUPO)) for _ in range(_GRUPOS)
    )


class AdministradorDeCuentas(Protocol):
    """Lo que el servicio de usuarios necesita del proveedor de identidad."""

    async def crear(self, correo: str, clave: str) -> UUID: ...

    async def borrar(self, cuenta_id: UUID) -> None: ...

    async def cambiar_clave(self, cuenta_id: UUID, clave: str) -> None: ...

    async def cambiar_correo(self, cuenta_id: UUID, correo: str) -> None: ...


class CuentasSupabase:
    """Implementación real contra `/auth/v1/admin/users`."""

    def __init__(self, cfg: Configuracion | None = None) -> None:
        self.cfg = cfg or obtener_configuracion()
        if not self.cfg.supabase_service_role_key:
            raise ErrorConfiguracion(
                "Falta MCH_SUPABASE_SERVICE_ROLE_KEY: sin ella no se pueden crear cuentas."
            )
        self.base = f"{self.cfg.supabase_url.rstrip('/')}/auth/v1/admin/users"

    @property
    def _cabeceras(self) -> dict[str, str]:
        llave = self.cfg.supabase_service_role_key
        return {"apikey": llave, "Authorization": f"Bearer {llave}"}

    async def _pedir(self, metodo: str, ruta: str = "", **kw: Any) -> httpx.Response:
        async with httpx.AsyncClient(timeout=_TIEMPO_LIMITE) as cliente:
            return await cliente.request(
                metodo, f"{self.base}{ruta}", headers=self._cabeceras, **kw
            )

    async def crear(self, correo: str, clave: str) -> UUID:
        respuesta = await self._pedir(
            "POST",
            json={
                "email": correo,
                "password": clave,
                # Sin esto, Supabase intentaría mandar un correo de confirmación
                # y la persona no podría entrar hasta pulsarlo. Aquí la cuenta la
                # crea su administrador, que responde por ella: la dirección ya
                # está verificada en el sentido que importa.
                "email_confirm": True,
            },
        )

        if respuesta.status_code in (200, 201):
            return UUID(respuesta.json()["id"])

        detalle = _mensaje(respuesta)
        if respuesta.status_code in (409, 422) and "already" in detalle.lower():
            raise ErrorConflicto(
                f"Ya existe una cuenta con el correo {correo}.", {"campo": "email"}
            )
        if respuesta.status_code == 422:
            # Casi siempre: contraseña por debajo del mínimo del proyecto, o
            # correo con formato que Supabase rechaza.
            raise ErrorValidacion(f"Supabase rechazó el alta: {detalle}")

        _log.error("Alta de cuenta fallida (%s): %s", respuesta.status_code, detalle)
        raise ErrorConfiguracion(
            "No se pudo crear la cuenta en Supabase. Revisa la llave de servicio y el proyecto."
        )

    async def borrar(self, cuenta_id: UUID) -> None:
        respuesta = await self._pedir("DELETE", f"/{cuenta_id}")
        if respuesta.status_code not in (200, 204, 404):
            _log.error(
                "No se pudo borrar la cuenta %s (%s): %s",
                cuenta_id,
                respuesta.status_code,
                _mensaje(respuesta),
            )

    async def cambiar_clave(self, cuenta_id: UUID, clave: str) -> None:
        await self._actualizar(cuenta_id, {"password": clave})

    async def cambiar_correo(self, cuenta_id: UUID, correo: str) -> None:
        await self._actualizar(cuenta_id, {"email": correo, "email_confirm": True})

    async def _actualizar(self, cuenta_id: UUID, cambios: dict[str, Any]) -> None:
        respuesta = await self._pedir("PUT", f"/{cuenta_id}", json=cambios)
        if respuesta.status_code == 200:
            return

        detalle = _mensaje(respuesta)
        if respuesta.status_code in (409, 422) and "already" in detalle.lower():
            raise ErrorConflicto("Ya existe una cuenta con ese correo.", {"campo": "email"})
        if respuesta.status_code == 404:
            raise ErrorValidacion("Esa cuenta ya no existe en Supabase Auth.")
        if respuesta.status_code == 422:
            raise ErrorValidacion(f"Supabase rechazó el cambio: {detalle}")

        _log.error(
            "Cambio en la cuenta %s fallido (%s): %s", cuenta_id, respuesta.status_code, detalle
        )
        raise ErrorConfiguracion("No se pudo actualizar la cuenta en Supabase.")


def _mensaje(respuesta: httpx.Response) -> str:
    """El texto que trae Supabase, sin reventar si no viene en JSON."""
    try:
        cuerpo = respuesta.json()
    except ValueError:
        return respuesta.text[:200]
    if isinstance(cuerpo, dict):
        for clave in ("msg", "message", "error_description", "error"):
            if isinstance(cuerpo.get(clave), str):
                return cuerpo[clave]
    return str(cuerpo)[:200]


def administrador_de_cuentas() -> AdministradorDeCuentas:
    """Dependencia de FastAPI. Se construye por petición: no guarda estado."""
    return CuentasSupabase()
