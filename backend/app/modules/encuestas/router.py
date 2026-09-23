"""Endpoints de encuestas de satisfacción.

Como en presupuestos, hay dos routers y la diferencia entre ambos es lo
importante del archivo:

  - `router` exige sesión y aplica RLS.
  - `router_publico` **no exige nada**: lo abre el cliente desde el enlace que
    recibió. Su única autorización es el token opaco de la URL.

Van separados para que ninguna ruta pública herede por descuido una dependencia
de sesión, ni al revés.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import sesion_usuario
from app.core.permissions import recepcion
from app.core.security import UsuarioAutenticado, usuario_actual
from app.modules.encuestas import service
from app.modules.encuestas.models import Encuesta
from app.modules.encuestas.schemas import (
    EncuestaEnviada,
    EncuestaFila,
    EncuestaPublica,
    EncuestaRespuesta,
    RespuestaCliente,
    ResumenEncuestas,
)
from app.modules.notificaciones.service import descripcion_vehiculo
from app.modules.ordenes.models import OrdenServicio
from app.modules.talleres.models import Taller
from app.modules.vehiculos.models import Vehiculo
from app.shared.paginacion import Pagina, ParametrosPagina, parametros_pagina

router = APIRouter(tags=["encuestas"])
router_publico = APIRouter(prefix="/publico", tags=["público"])


def _campos(e: Encuesta) -> dict[str, object]:
    return {
        "id": e.id,
        "orden_id": e.orden_id,
        "enviada_en": e.enviada_en,
        "respondida_en": e.respondida_en,
        "respondida": e.respondida,
        "puntaje_atencion": e.puntaje_atencion,
        "puntaje_tiempo": e.puntaje_tiempo,
        "puntaje_calidad": e.puntaje_calidad,
        "recomendaria": e.recomendaria,
        "comentario": e.comentario,
        "creado_en": e.creado_en,
        "enlace_publico": service.enlace(e),
    }


def _ficha(e: Encuesta) -> EncuestaRespuesta:
    return EncuestaRespuesta(**_campos(e))


# -----------------------------------------------------------------------------
# Con sesión
# -----------------------------------------------------------------------------


@router.get(
    "/encuestas",
    response_model=Pagina[EncuestaFila],
    summary="Encuestas del taller",
)
async def listar_encuestas(
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    pagina: Annotated[ParametrosPagina, Depends(parametros_pagina)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
    solo_respondidas: Annotated[bool, Query(description="Oculta las que aún no contestan")] = False,
) -> Pagina[EncuestaFila]:
    filas, total = await service.listar(sesion, solo_respondidas=solo_respondidas, pagina=pagina)
    return Pagina[EncuestaFila](
        items=[
            EncuestaFila(
                **_campos(e),
                folio=o.folio,
                placa=v.placa,
                vehiculo=descripcion_vehiculo(v),
                cliente_nombre=c.nombre,
                fecha_entrega=o.fecha_entrega,
            )
            for e, o, v, c in filas
        ],
        total=total,
        limite=pagina.limite,
        desplazamiento=pagina.desplazamiento,
    )


@router.get(
    "/encuestas/resumen",
    response_model=ResumenEncuestas,
    summary="Indicadores de satisfacción",
    description="Promedios, tasa de respuesta y NPS de todas las encuestas del taller.",
)
async def resumen_encuestas(
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> ResumenEncuestas:
    return await service.resumen(sesion)


@router.get(
    "/ordenes/{orden_id}/encuesta",
    response_model=EncuestaRespuesta | None,
    summary="Encuesta de la orden",
    description="Devuelve `null` mientras el vehículo no se haya entregado.",
)
async def encuesta_de_orden(
    orden_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> EncuestaRespuesta | None:
    encuesta = await service.obtener_de_orden(sesion, orden_id)
    return _ficha(encuesta) if encuesta else None


@router.post(
    "/ordenes/{orden_id}/encuesta",
    response_model=EncuestaEnviada,
    summary="Enviar o reenviar la encuesta",
    description=(
        "La encuesta se crea sola al entregar el vehículo; esto sirve para "
        "reenviarla, o para crearla en órdenes entregadas antes de que existiera. "
        "Si el cliente no tiene correo, `encolada_a` viene en `null` y queda el "
        "enlace para compartirlo a mano."
    ),
)
async def enviar_encuesta(
    orden_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(recepcion)],
) -> EncuestaEnviada:
    encuesta, destinatario = await service.enviar(sesion, orden_id)
    return EncuestaEnviada(**_campos(encuesta), encolada_a=destinatario)


# -----------------------------------------------------------------------------
# Sin sesión: lo abre el cliente desde su enlace
# -----------------------------------------------------------------------------


def _publico(
    e: Encuesta, orden: OrdenServicio, vehiculo: Vehiculo, taller: Taller
) -> EncuestaPublica:
    return EncuestaPublica(
        taller_nombre=taller.nombre,
        taller_telefono=taller.telefono,
        folio_orden=orden.folio,
        vehiculo=descripcion_vehiculo(vehiculo),
        placa=vehiculo.placa,
        fecha_entrega=orden.fecha_entrega,
        respondida=e.respondida,
        respondida_en=e.respondida_en,
        puntaje_atencion=e.puntaje_atencion,
        puntaje_tiempo=e.puntaje_tiempo,
        puntaje_calidad=e.puntaje_calidad,
        recomendaria=e.recomendaria,
        comentario=e.comentario,
    )


@router_publico.get(
    "/encuestas/{token}",
    response_model=EncuestaPublica,
    summary="Abrir la encuesta desde el enlace",
    description="Sin autenticación: el token de la URL es la autorización.",
)
async def ver_encuesta_publica(token: str) -> EncuestaPublica:
    return _publico(*await service.obtener_por_token(token))


@router_publico.post(
    "/encuestas/{token}/respuesta",
    response_model=EncuestaPublica,
    summary="Responder la encuesta",
    description="Se contesta una sola vez; volver a enviarla devuelve 409.",
)
async def responder_encuesta_publica(token: str, respuesta: RespuestaCliente) -> EncuestaPublica:
    return _publico(*await service.responder_por_token(token, respuesta))
