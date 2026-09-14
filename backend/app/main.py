"""Punto de entrada de la API de Mechanified.

Los routers de cada entidad se registran conforme avanzan las fases.
"""

import logging
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import obtener_configuracion
from app.core.database import comprobar_conexion
from app.core.exceptions import registrar_manejadores
from app.modules.calidad.router import router as router_calidad
from app.modules.clientes.router import router as router_clientes
from app.modules.diagnosticos.router import router as router_diagnosticos
from app.modules.ordenes.router import router as router_ordenes
from app.modules.presupuestos.router import router as router_presupuestos
from app.modules.presupuestos.router import router_publico as router_publico
from app.modules.repuestos.router import router as router_repuestos
from app.modules.usuarios.router import router as router_usuarios
from app.modules.vehiculos.router import router as router_vehiculos

cfg = obtener_configuracion()

logging.basicConfig(
    level=getattr(logging, cfg.log_nivel.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-8s %(name)s :: %(message)s",
)

app = FastAPI(
    title="Mechanified API",
    description=(
        "API de gestión integral para talleres mecánicos.\n\n"
        "Todos los endpoints de datos exigen `Authorization: Bearer <token>` con un "
        "token de Supabase Auth. El aislamiento entre talleres lo aplica PostgreSQL "
        "mediante Row Level Security, no esta capa."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.origenes_cors,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

registrar_manejadores(app)

app.include_router(router_clientes)
app.include_router(router_vehiculos)
app.include_router(router_ordenes)
app.include_router(router_usuarios)
app.include_router(router_diagnosticos)
app.include_router(router_repuestos)
app.include_router(router_presupuestos)
app.include_router(router_publico)
app.include_router(router_calidad)


@app.get("/salud", tags=["sistema"])
async def salud() -> dict[str, str]:
    """Sonda de disponibilidad. No toca la base de datos."""
    return {"estado": "ok", "servicio": "mechanified-api"}


if not cfg.es_produccion:

    @app.get("/salud/base-datos", tags=["sistema"])
    async def salud_base_datos() -> dict[str, Any]:
        """Diagnóstico de la conexión y del contexto RLS.

        Expone versión y roles del servidor, así que solo se publica fuera de
        producción.
        """
        return await comprobar_conexion()
