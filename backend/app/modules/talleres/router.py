"""Endpoints de la configuración del taller.

Hay un solo recurso y no lleva id: el taller es el de la sesión, y pedirlo en la
ruta solo daría la ocasión de escribir el de otro. Por eso `/taller` en singular
y sin parámetro.

La lectura es para todo el taller y la escritura solo para administración, igual
que las políticas `talleres_select` y `talleres_update` de la migración 000200.
Se declara aquí para responder un 403 que explica qué rol hace falta, en vez del
silencio con el que RLS deja un UPDATE sin filas.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import sesion_usuario
from app.core.permissions import solo_admin
from app.core.security import UsuarioAutenticado, usuario_actual
from app.modules.talleres import service
from app.modules.talleres.schemas import TallerEditar, TallerRespuesta

router = APIRouter(prefix="/taller", tags=["taller"])


@router.get(
    "",
    response_model=TallerRespuesta,
    summary="Configuración del taller de la sesión",
    description=(
        "La leen todos los roles: la moneda, la tarifa por hora y el impuesto "
        "son lo que la interfaz necesita para mostrar cifras sin ambigüedad y "
        "anticipar lo que el servidor va a aplicar por omisión."
    ),
)
async def obtener_taller(
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> TallerRespuesta:
    return TallerRespuesta.model_validate(await service.obtener(sesion))


@router.patch(
    "",
    response_model=TallerRespuesta,
    summary="Cambiar la configuración del taller",
    description=(
        "Cambio parcial: solo se toca lo que venga en el cuerpo.\n\n"
        "Nada de esto reescribe historia. La tarifa queda congelada en cada "
        "línea de mano de obra y el impuesto en cada presupuesto emitido, así "
        "que subir precios no altera ningún documento que el cliente ya vio. "
        "Cambiar el prefijo de folio tampoco renumera las órdenes existentes: "
        "el contador sigue donde estaba y solo las nuevas lo estrenan."
    ),
)
async def editar_taller(
    datos: TallerEditar,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(solo_admin)],
) -> TallerRespuesta:
    return TallerRespuesta.model_validate(await service.actualizar(sesion, datos))
