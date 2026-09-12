"""Endpoints de presupuestos.

Hay dos routers en este archivo y la diferencia entre ambos es la más importante
del módulo:

  - `router` exige sesión y aplica RLS, como el resto de la API.
  - `router_publico` **no exige nada**: lo abre el cliente desde el enlace que
    recibió, sin cuenta. Su única autorización es el token opaco de la URL.

Van separados para que ninguna ruta pública herede por descuido una dependencia
de sesión, ni al revés.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import sesion_usuario
from app.core.permissions import recepcion
from app.core.security import UsuarioAutenticado, usuario_actual
from app.modules.ordenes.models import OrdenServicio
from app.modules.presupuestos import service
from app.modules.presupuestos.models import (
    EstadoPresupuesto,
    Presupuesto,
    PresupuestoItem,
    TipoLinea,
)
from app.modules.presupuestos.schemas import (
    ItemRespuesta,
    PresupuestoEditar,
    PresupuestoEmitir,
    PresupuestoPublico,
    PresupuestoRespuesta,
    PresupuestoResumen,
    RespuestaCliente,
)
from app.modules.talleres.models import Taller
from app.modules.vehiculos.models import Vehiculo

router = APIRouter(tags=["presupuestos"])
router_publico = APIRouter(prefix="/publico", tags=["público"])


def _item(i: PresupuestoItem) -> ItemRespuesta:
    tipo = TipoLinea(i.tipo)
    return ItemRespuesta(
        id=i.id,
        tipo=tipo.value,
        tipo_etiqueta=tipo.etiqueta,
        descripcion=i.descripcion,
        cantidad=i.cantidad,
        precio_unitario=i.precio_unitario,
        subtotal=i.subtotal,
        orden_visual=i.orden_visual,
    )


def _resumen(p: Presupuesto) -> dict[str, object]:
    return {
        "id": p.id,
        "orden_id": p.orden_id,
        "version": p.version,
        "estado": p.estado,
        "estado_etiqueta": p.estado.etiqueta,
        "total": p.total,
        "valido_hasta": p.valido_hasta,
        "caducado": service.esta_caducado(p),
        "enviado_en": p.enviado_en,
        "respondido_en": p.respondido_en,
        "creado_en": p.creado_en,
    }


def _ficha(p: Presupuesto) -> PresupuestoRespuesta:
    return PresupuestoRespuesta(
        **_resumen(p),  # type: ignore[arg-type]
        taller_id=p.taller_id,
        subtotal_mano_obra=p.subtotal_mano_obra,
        subtotal_repuestos=p.subtotal_repuestos,
        descuento=p.descuento,
        impuesto_pct=p.impuesto_pct,
        impuesto_monto=p.impuesto_monto,
        comentario_cliente=p.comentario_cliente,
        autor_nombre=p.autor.nombre_completo if p.autor else None,
        items=[_item(i) for i in p.items],
        # El enlace solo tiene sentido una vez enviado; antes, publicarlo
        # invitaría a mandarlo cuando el documento todavía puede cambiar.
        enlace_publico=(
            service.enlace_publico(p.token_publico)
            if p.estado is not EstadoPresupuesto.BORRADOR
            else None
        ),
    )


# -----------------------------------------------------------------------------
# Con sesión
# -----------------------------------------------------------------------------


@router.get(
    "/ordenes/{orden_id}/presupuestos",
    response_model=list[PresupuestoResumen],
    summary="Versiones de presupuesto de la orden",
)
async def listar_presupuestos(
    orden_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> list[PresupuestoResumen]:
    return [
        PresupuestoResumen(**_resumen(p))  # type: ignore[arg-type]
        for p in await service.listar(sesion, orden_id)
    ]


@router.post(
    "/ordenes/{orden_id}/presupuestos",
    response_model=PresupuestoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Emitir un presupuesto",
    description=(
        "Copia las líneas de mano de obra y repuestos que tenga la orden en ese "
        "momento. A partir de ahí el documento no cambia: cargar más trabajo no "
        "altera lo que el cliente ya vio."
    ),
)
async def emitir_presupuesto(
    orden_id: UUID,
    datos: PresupuestoEmitir,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    usuario: Annotated[UsuarioAutenticado, Depends(recepcion)],
) -> PresupuestoRespuesta:
    return _ficha(await service.emitir(sesion, orden_id, datos, usuario))


@router.get(
    "/presupuestos/{presupuesto_id}",
    response_model=PresupuestoRespuesta,
    summary="Ficha del presupuesto",
)
async def obtener_presupuesto(
    presupuesto_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(usuario_actual)],
) -> PresupuestoRespuesta:
    return _ficha(await service.obtener(sesion, presupuesto_id))


@router.patch(
    "/presupuestos/{presupuesto_id}",
    response_model=PresupuestoRespuesta,
    summary="Ajustar un borrador",
    description="Solo mientras es borrador. Después, emitir una versión nueva.",
)
async def editar_presupuesto(
    presupuesto_id: UUID,
    datos: PresupuestoEditar,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(recepcion)],
) -> PresupuestoRespuesta:
    return _ficha(await service.actualizar(sesion, presupuesto_id, datos))


@router.post(
    "/presupuestos/{presupuesto_id}/enviar",
    response_model=PresupuestoRespuesta,
    summary="Enviar al cliente",
    description="Sella los montos y devuelve el enlace público para compartir.",
)
async def enviar_presupuesto(
    presupuesto_id: UUID,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(recepcion)],
) -> PresupuestoRespuesta:
    return _ficha(await service.enviar(sesion, presupuesto_id))


@router.post(
    "/presupuestos/{presupuesto_id}/respuesta",
    response_model=PresupuestoRespuesta,
    summary="Anotar la respuesta del cliente",
    description="Para cuando contesta por teléfono o en el mostrador.",
)
async def anotar_respuesta(
    presupuesto_id: UUID,
    respuesta: RespuestaCliente,
    sesion: Annotated[AsyncSession, Depends(sesion_usuario)],
    _: Annotated[UsuarioAutenticado, Depends(recepcion)],
) -> PresupuestoRespuesta:
    return _ficha(await service.responder(sesion, presupuesto_id, respuesta))


# -----------------------------------------------------------------------------
# Sin sesión: lo abre el cliente desde su enlace
# -----------------------------------------------------------------------------


def _publico(
    p: Presupuesto, orden: OrdenServicio, vehiculo: Vehiculo, taller: Taller
) -> PresupuestoPublico:
    return PresupuestoPublico(
        taller_nombre=taller.nombre,
        taller_telefono=taller.telefono,
        moneda=taller.moneda,
        folio_orden=orden.folio,
        vehiculo=" ".join(
            filter(None, [vehiculo.marca, vehiculo.modelo, str(vehiculo.anio or "")])
        ),
        placa=vehiculo.placa,
        version=p.version,
        estado=p.estado,
        estado_etiqueta=p.estado.etiqueta,
        cerrado=p.estado in service.CERRADOS or service.esta_caducado(p),
        valido_hasta=p.valido_hasta,
        items=[_item(i) for i in p.items],
        subtotal=p.subtotal_mano_obra + p.subtotal_repuestos,
        descuento=p.descuento,
        impuesto_pct=p.impuesto_pct,
        impuesto_monto=p.impuesto_monto,
        total=p.total,
        comentario_cliente=p.comentario_cliente,
        respondido_en=p.respondido_en,
    )


@router_publico.get(
    "/presupuestos/{token}",
    response_model=PresupuestoPublico,
    summary="Ver un presupuesto desde el enlace",
    description="Sin autenticación: el token de la URL es la autorización.",
)
async def ver_presupuesto_publico(token: str) -> PresupuestoPublico:
    return _publico(*await service.obtener_por_token(token))


@router_publico.post(
    "/presupuestos/{token}/respuesta",
    response_model=PresupuestoPublico,
    summary="Aprobar o rechazar desde el enlace",
    description=(
        "Aprobar mueve la orden a `aprobado` si estaba esperando esta respuesta. "
        "Un presupuesto ya respondido o vencido devuelve 409."
    ),
)
async def responder_presupuesto_publico(
    token: str, respuesta: RespuestaCliente
) -> PresupuestoPublico:
    await service.responder_por_token(token, respuesta)
    return _publico(*await service.obtener_por_token(token))
