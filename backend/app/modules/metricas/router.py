"""Endpoint del panel del taller.

Un solo endpoint y una sola respuesta, a propósito: el panel se mira entero o no
se mira. Partirlo en siete llamadas haría que la pantalla se pintara a trozos y
que un fallo dejara medio tablero en blanco sin decir por qué.

Es para administración. No es una barrera de seguridad —los números salen de
datos que RLS ya deja leer a todo el taller— sino una decisión de producto:
facturación, ticket medio y productividad por técnico son cosas que el dueño del
taller decide con quién comparte.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import sesion_usuario
from app.core.permissions import solo_admin
from app.core.security import UsuarioAutenticado
from app.modules.metricas import service
from app.modules.metricas.schemas import PanelMetricas

router = APIRouter(tags=["metricas"])


@router.get(
    "/metricas/panel",
    response_model=PanelMetricas,
    summary="Panel del taller",
    description=(
        "Trabajo vivo, producción del periodo, tiempos por etapa, presupuestos, "
        "calidad, satisfacción y productividad por técnico. El trabajo vivo es "
        "de ahora mismo; el resto se acota al periodo pedido."
    ),
)
async def panel(
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(solo_admin)],
    dias: Annotated[
        int, Query(ge=service.DIAS_MINIMO, le=service.DIAS_MAXIMO, description="Días hacia atrás")
    ] = 30,
) -> PanelMetricas:
    return await service.panel(sesion, dias)
