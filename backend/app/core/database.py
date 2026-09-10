"""Acceso a Postgres con RLS aplicado de verdad.

Aquí se materializa la decisión de arquitectura del proyecto. El backend se
conecta con un rol que omite RLS, así que si simplemente lanzáramos consultas la
multi-tenancy dependería de que ningún `WHERE taller_id` se nos olvide jamás.

En vez de eso, cada transacción de usuario empieza con:

    SET LOCAL ROLE authenticated;
    SELECT set_config('request.jwt.claims', '<claims del usuario>', true);

A partir de ahí Postgres evalúa las políticas exactamente igual que si la
consulta viniera del navegador. Si a un servicio se le olvida filtrar por
taller, la base devuelve cero filas en lugar de las de otro taller.

Las dos sentencias son `LOCAL`: valen hasta el fin de la transacción y se
deshacen solas al devolver la conexión al pool. No hay estado que limpiar ni
riesgo de que una conexión reciclada arrastre la identidad del usuario anterior.
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import obtener_configuracion
from app.core.security import UsuarioAutenticado, usuario_actual


@lru_cache
def obtener_motor() -> AsyncEngine:
    cfg = obtener_configuracion()
    return create_async_engine(
        cfg.database_url,
        echo=cfg.db_echo,
        pool_size=cfg.db_pool_tamano,
        max_overflow=cfg.db_pool_desborde,
        # El pooler de Supabase corta conexiones ociosas; sin pre_ping la
        # primera consulta después de un rato falla con la conexión muerta.
        pool_pre_ping=True,
        pool_recycle=1800,
    )


@lru_cache
def obtener_fabrica() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(obtener_motor(), expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def sesion_rls(usuario: UsuarioAutenticado) -> AsyncIterator[AsyncSession]:
    """Transacción que corre bajo la identidad del usuario, con RLS activo."""
    async with obtener_fabrica()() as sesion, sesion.begin():
        await sesion.execute(text("SET LOCAL ROLE authenticated"))
        await sesion.execute(
            text("SELECT set_config('request.jwt.claims', :claims, true)"),
            {"claims": json.dumps(usuario.claims_rls)},
        )
        yield sesion


async def sesion_usuario(
    usuario: UsuarioAutenticado = Depends(usuario_actual),
) -> AsyncIterator[AsyncSession]:
    """Dependencia estándar de los endpoints. Es la que deben usar los routers."""
    async with sesion_rls(usuario) as sesion:
        yield sesion


@asynccontextmanager
async def sesion_servicio() -> AsyncIterator[AsyncSession]:
    """Transacción SIN RLS, con el rol de conexión.

    PELIGRO: ve y modifica los datos de todos los talleres. Su uso legítimo se
    limita a tres casos, y ninguno ocurre dentro de un request de usuario:

      1. Worker de notificaciones, que avanza la cola.
      2. Endpoints públicos por token (aprobar presupuesto, responder encuesta),
         donde no hay sesión y el token del enlace es la autorización.
      3. Alta de un taller nuevo con su primer administrador.

    Cualquier otro uso es un error de diseño: significa que se está esquivando
    la barrera en lugar de darle al usuario el permiso que necesita.
    """
    async with obtener_fabrica()() as sesion, sesion.begin():
        yield sesion


async def comprobar_conexion() -> dict[str, Any]:
    """Diagnóstico de la conexión y del cambio de rol.

    Verifica lo que de verdad importa: que el rol `authenticated` se puede
    asumir y que los claims llegan a `current_setting`. Si esto falla, ninguna
    política podrá evaluarse.
    """
    claims = {
        "sub": "00000000-0000-0000-0000-000000000000",
        "role": "authenticated",
        "taller_id": "00000000-0000-0000-0000-000000000000",
        "rol": "admin_taller",
    }
    async with obtener_fabrica()() as sesion, sesion.begin():
        version = (await sesion.execute(text("SHOW server_version"))).scalar_one()
        rol_conexion = (await sesion.execute(text("SELECT current_user"))).scalar_one()

        await sesion.execute(text("SET LOCAL ROLE authenticated"))
        await sesion.execute(
            text("SELECT set_config('request.jwt.claims', :c, true)"), {"c": json.dumps(claims)}
        )
        rol_efectivo = (await sesion.execute(text("SELECT current_user"))).scalar_one()
        taller = (await sesion.execute(text("SELECT public.mch_taller_actual()"))).scalar_one()
        rol_mch = (await sesion.execute(text("SELECT public.mch_rol_actual()"))).scalar_one()

    return {
        "postgres": version,
        "rol_conexion": rol_conexion,
        "rol_efectivo": rol_efectivo,
        "mch_taller_actual": str(taller),
        "mch_rol_actual": rol_mch,
        "rls_operativo": rol_efectivo == "authenticated" and str(taller) == claims["taller_id"],
    }
