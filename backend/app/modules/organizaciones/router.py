"""Endpoints de la organización y de la cuenta del sitio.

Dos routers, y la diferencia entre ambos es lo importante del archivo:

  - `router` (`/organizacion`) es de la aplicación de una sede: exige taller en
    el token, como el resto de la API.
  - `router_cuenta` (`/cuenta`) es del sitio de Mechanified: exige sesión pero
    no taller, porque quien entra puede no pertenecer todavía a ninguna
    organización. Sus sesiones de base de datos van sin claims de tenant.

Van separados para que una ruta de la cuenta no herede por descuido el
requisito de taller, ni una de la aplicación pierda el suyo.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import sesion_cuenta, sesion_usuario
from app.core.security import (
    CuentaAutenticada,
    UsuarioAutenticado,
    cuenta_actual,
    usuario_actual,
)
from app.modules.organizaciones import service
from app.modules.organizaciones.schemas import (
    EstadoCuenta,
    OrganizacionNueva,
    OrganizacionRespuesta,
    SolicitudNueva,
)

router = APIRouter(prefix="/organizacion", tags=["organización"])
router_cuenta = APIRouter(prefix="/cuenta", tags=["cuenta"])


@router.get(
    "",
    response_model=OrganizacionRespuesta,
    summary="Organización de la sesión",
    description=(
        "La de la sede del token. Su nombre es el que lleva el producto para la "
        "gente de esa organización. La leen todos los roles."
    ),
)
async def obtener_organizacion(
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> OrganizacionRespuesta:
    return OrganizacionRespuesta.model_validate(await service.obtener(sesion))


@router_cuenta.get(
    "",
    response_model=EstadoCuenta,
    summary="Estado de la cuenta",
    description=(
        "Si la cuenta pertenece a una organización (y con qué sede y rol) y la "
        "última solicitud de alta que mandó. Funciona también sin taller en el "
        "token, que es el caso de quien acaba de registrarse."
    ),
)
async def obtener_estado(
    sesion: Annotated[AsyncSession, Depends(sesion_cuenta)],
    cuenta: Annotated[CuentaAutenticada, Depends(cuenta_actual)],
) -> EstadoCuenta:
    return await service.estado_cuenta(sesion, cuenta)


@router_cuenta.post(
    "/organizacion",
    response_model=EstadoCuenta,
    status_code=status.HTTP_201_CREATED,
    summary="Crear mi organización",
    description=(
        "Funda la organización con su primera sede y deja a la cuenta como su "
        "administrador. Una cuenta pertenece a una sola organización: si ya "
        "tiene una, responde 409.\n\n"
        "El token con el que se llama todavía no lleva taller. Para entrar como "
        "administrador hay que renovar la sesión: el token siguiente ya lo trae."
    ),
)
async def crear_organizacion(
    datos: OrganizacionNueva,
    sesion: Annotated[AsyncSession, Depends(sesion_cuenta)],
    cuenta: Annotated[CuentaAutenticada, Depends(cuenta_actual)],
) -> EstadoCuenta:
    return await service.crear_propia(sesion, cuenta, datos)


@router_cuenta.post(
    "/solicitud",
    response_model=EstadoCuenta,
    status_code=status.HTTP_201_CREATED,
    summary="Pedir que el equipo cree la organización",
    description=(
        "Deja la petición al equipo de Mechanified, que contesta al correo de la "
        "cuenta. Hay como mucho una pendiente por cuenta."
    ),
)
async def solicitar_organizacion(
    datos: SolicitudNueva,
    sesion: Annotated[AsyncSession, Depends(sesion_cuenta)],
    cuenta: Annotated[CuentaAutenticada, Depends(cuenta_actual)],
) -> EstadoCuenta:
    return await service.solicitar(sesion, cuenta, datos)
