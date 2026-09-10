"""Configuración compartida de las pruebas."""

from collections.abc import AsyncIterator

import pytest_asyncio

from app.core.database import obtener_motor


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _cerrar_motor() -> AsyncIterator[None]:
    """Cierra el pool al terminar la sesión de pruebas.

    Sin esto, las conexiones quedan abiertas cuando el bucle de eventos se
    cierra y asyncpg deja avisos de corrutinas sin esperar.
    """
    yield
    await obtener_motor().dispose()
