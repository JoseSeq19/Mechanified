"""Errores de dominio y su traducción a respuestas HTTP.

Buena parte de las reglas de Mechanified viven en la base de datos: la máquina
de estados, la inmutabilidad del presupuesto, la coherencia de tenant. Cuando
una de ellas se rompe, Postgres levanta una excepción con un mensaje que ya está
redactado para una persona ("Transición de estado inválida: recibido ->
entregado").

Este módulo convierte esos errores en respuestas HTTP con el código correcto en
lugar de dejar que salgan como un 500 genérico. Sin esta traducción, el trabajo
de escribir buenos mensajes en los triggers se perdería.
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

# SQLSTATE -> (HTTP, si el mensaje de Postgres es apto para mostrarse)
#
# Los errores levantados por nuestros triggers usan 23514 (check_violation),
# 42501 (insufficient_privilege) y 23503 (foreign_key_violation) con textos
# escritos a propósito, así que se propagan tal cual. Los de integridad que
# genera Postgres solo (23505 en un índice único) llevan detalles internos como
# el nombre del índice, así que se sustituyen.
_SQLSTATE_HTTP: dict[str, tuple[int, bool]] = {
    "23514": (status.HTTP_422_UNPROCESSABLE_CONTENT, True),  # check_violation
    "23503": (status.HTTP_422_UNPROCESSABLE_CONTENT, True),  # foreign_key_violation
    "42501": (status.HTTP_403_FORBIDDEN, True),  # insufficient_privilege
    "23505": (status.HTTP_409_CONFLICT, False),  # unique_violation
    "23502": (status.HTTP_422_UNPROCESSABLE_CONTENT, False),  # not_null_violation
    "22P02": (status.HTTP_422_UNPROCESSABLE_CONTENT, False),  # invalid_text_representation
}

_MENSAJE_GENERICO: dict[str, str] = {
    "23505": "Ya existe un registro con esos datos.",
    "23502": "Falta un campo obligatorio.",
    "22P02": "Alguno de los valores enviados tiene un formato inválido.",
}


class ErrorMechanified(Exception):
    """Raíz de los errores de dominio."""

    http_status = status.HTTP_400_BAD_REQUEST
    codigo = "error"

    def __init__(self, mensaje: str, detalles: dict[str, Any] | None = None) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalles = detalles or {}


class ErrorAutenticacion(ErrorMechanified):
    http_status = status.HTTP_401_UNAUTHORIZED
    codigo = "no_autenticado"


class ErrorPermiso(ErrorMechanified):
    http_status = status.HTTP_403_FORBIDDEN
    codigo = "sin_permiso"


class ErrorNoEncontrado(ErrorMechanified):
    http_status = status.HTTP_404_NOT_FOUND
    codigo = "no_encontrado"


class ErrorConflicto(ErrorMechanified):
    http_status = status.HTTP_409_CONFLICT
    codigo = "conflicto"


class ErrorValidacion(ErrorMechanified):
    http_status = status.HTTP_422_UNPROCESSABLE_CONTENT
    codigo = "invalido"


class ErrorConfiguracion(ErrorMechanified):
    """Falta o está mal una variable de entorno. Es un fallo del despliegue."""

    http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
    codigo = "configuracion"


def _respuesta(
    status_code: int, codigo: str, mensaje: str, detalles: dict[str, Any]
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"codigo": codigo, "mensaje": mensaje, "detalles": detalles}},
    )


def extraer_sqlstate(exc: BaseException) -> str | None:
    """Busca el SQLSTATE dentro de la cadena de excepciones de SQLAlchemy.

    SQLAlchemy envuelve el error de asyncpg, que a su vez expone el código en
    `sqlstate`. Hay que recorrer las causas para encontrarlo.
    """
    actual: BaseException | None = exc
    vistas = 0
    while actual is not None and vistas < 10:
        codigo = getattr(actual, "sqlstate", None) or getattr(actual, "pgcode", None)
        if codigo:
            return str(codigo)
        actual = actual.__cause__ or actual.__context__
        vistas += 1
    return None


def _limpiar_mensaje_postgres(texto: str) -> str:
    """Se queda con la primera línea, sin el prefijo del driver."""
    primera = texto.strip().splitlines()[0]
    for prefijo in ("asyncpg.exceptions.", "sqlalchemy.exc."):
        if primera.startswith(prefijo):
            primera = primera.split(":", 1)[-1].strip()
    return primera


def registrar_manejadores(app: FastAPI) -> None:
    """Conecta los manejadores de error a la aplicación."""

    @app.exception_handler(ErrorMechanified)
    async def _dominio(_: Request, exc: ErrorMechanified) -> JSONResponse:
        return _respuesta(exc.http_status, exc.codigo, exc.mensaje, exc.detalles)

    @app.exception_handler(Exception)
    async def _inesperado(_: Request, exc: Exception) -> JSONResponse:
        sqlstate = extraer_sqlstate(exc)
        if sqlstate is None:
            raise exc  # que lo maneje Starlette y quede en el log como 500

        http_status, propagar = _SQLSTATE_HTTP.get(
            sqlstate, (status.HTTP_500_INTERNAL_SERVER_ERROR, False)
        )
        if http_status == status.HTTP_500_INTERNAL_SERVER_ERROR:
            raise exc

        mensaje = (
            _limpiar_mensaje_postgres(str(exc))
            if propagar
            else _MENSAJE_GENERICO.get(sqlstate, "La operación no es válida.")
        )
        return _respuesta(http_status, f"sql_{sqlstate}", mensaje, {"sqlstate": sqlstate})
