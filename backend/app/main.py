"""Punto de entrada de la API de Mechanified.

Los routers de cada módulo se registran en la Fase 2.
"""

from fastapi import FastAPI

app = FastAPI(
    title="Mechanified API",
    description="API de gestión integral para talleres mecánicos.",
    version="0.1.0",
)


@app.get("/salud", tags=["sistema"])
async def salud() -> dict[str, str]:
    """Sonda de disponibilidad."""
    return {"estado": "ok", "servicio": "mechanified-api"}
