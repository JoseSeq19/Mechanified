"""Lógica de presupuestos.

Tres reglas sostienen este módulo, y las tres existen para que el acuerdo con el
cliente quede por escrito y no se pueda reescribir:

  1. **Emitir es fotografiar.** Se copian las líneas vivas de la orden a
     `presupuesto_items`. A partir de ahí el documento vive por su cuenta:
     cargar más trabajo a la orden no altera lo que el cliente ya vio.
  2. **Enviado es sellado.** Postgres impide cambiar montos de un presupuesto
     que salió del taller (`mch_presupuestos_guard`). Si hay que cambiar algo,
     se emite la versión siguiente.
  3. **El cliente responde sin cuenta.** Abre un enlace con un token opaco. Ese
     camino no pasa por RLS —no hay sesión que evaluar— así que usa el rol de
     servicio, que es uno de sus tres usos legítimos. Por eso las funciones
     públicas de este archivo abren su propia sesión y están agrupadas aparte:
     para que se vea de un vistazo cuáles son.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import obtener_configuracion
from app.core.database import sesion_servicio
from app.core.exceptions import ErrorConflicto, ErrorNoEncontrado, ErrorValidacion, extraer_sqlstate
from app.core.security import UsuarioAutenticado
from app.modules.diagnosticos.models import ManoObra
from app.modules.ordenes import service as srv_ordenes
from app.modules.ordenes.estados import TERMINALES, EstadoOrden
from app.modules.ordenes.models import OrdenServicio
from app.modules.presupuestos.models import (
    EstadoPresupuesto,
    Presupuesto,
    PresupuestoItem,
    TipoLinea,
)
from app.modules.presupuestos.schemas import (
    PresupuestoEditar,
    PresupuestoEmitir,
    RespuestaCliente,
)
from app.modules.repuestos.models import OrdenRepuesto
from app.modules.talleres.models import Taller
from app.modules.usuarios.models import Perfil
from app.modules.vehiculos.models import Vehiculo

_RELACIONES = (selectinload(Presupuesto.items), selectinload(Presupuesto.autor))

#: Estados en los que el documento ya no admite respuesta del cliente.
CERRADOS = (EstadoPresupuesto.APROBADO, EstadoPresupuesto.RECHAZADO, EstadoPresupuesto.VENCIDO)


def esta_caducado(p: Presupuesto) -> bool:
    """Pasó su fecha de validez y sigue esperando respuesta.

    Se calcula al leer en vez de marcarse con una tarea programada: mientras no
    exista el worker, un presupuesto vencido seguiría figurando como `enviado` y
    el cliente podría aprobarlo meses después.
    """
    return (
        p.estado is EstadoPresupuesto.ENVIADO
        and p.valido_hasta is not None
        and p.valido_hasta < date.today()
    )


def enlace_publico(token: str) -> str:
    base = obtener_configuracion().url_publica_web.rstrip("/")
    return f"{base}/presupuesto/{token}"


# -----------------------------------------------------------------------------
# Lo que hace el taller, con sesión y RLS
# -----------------------------------------------------------------------------


async def listar(sesion: AsyncSession, orden_id: UUID) -> list[Presupuesto]:
    await srv_ordenes.obtener(sesion, orden_id)

    filas = await sesion.scalars(
        select(Presupuesto)
        .where(Presupuesto.orden_id == orden_id)
        .options(*_RELACIONES)
        .order_by(Presupuesto.version)
    )
    return list(filas.all())


async def obtener(sesion: AsyncSession, presupuesto_id: UUID) -> Presupuesto:
    p = await sesion.scalar(
        select(Presupuesto)
        .where(Presupuesto.id == presupuesto_id)
        .options(*_RELACIONES)
        .execution_options(populate_existing=True)
    )
    if p is None:
        raise ErrorNoEncontrado(f"No existe el presupuesto {presupuesto_id}.")
    return p


async def emitir(
    sesion: AsyncSession, orden_id: UUID, datos: PresupuestoEmitir, usuario: UsuarioAutenticado
) -> Presupuesto:
    """Fotografía las líneas vivas de la orden en una versión nueva."""
    orden = await srv_ordenes.obtener(sesion, orden_id)
    if orden.estado in TERMINALES:
        raise ErrorValidacion(
            f"La orden {orden.folio} está {orden.estado.etiqueta.lower()}: ya no se cotiza."
        )

    mano_obra = list(
        (await sesion.scalars(select(ManoObra).where(ManoObra.orden_id == orden_id))).all()
    )
    repuestos = list(
        (
            await sesion.scalars(select(OrdenRepuesto).where(OrdenRepuesto.orden_id == orden_id))
        ).all()
    )

    if not mano_obra and not repuestos:
        raise ErrorValidacion(
            "La orden no tiene trabajo ni piezas cargadas: no hay nada que cotizar.",
            {"orden": orden.folio},
        )

    subtotal_mo = sum((m.subtotal for m in mano_obra), Decimal("0"))
    subtotal_rp = sum((r.subtotal for r in repuestos), Decimal("0"))

    if datos.descuento > subtotal_mo + subtotal_rp:
        raise ErrorValidacion(
            "El descuento no puede superar el importe del presupuesto.", {"campo": "descuento"}
        )

    presupuesto = Presupuesto(
        taller_id=usuario.taller_id,
        orden_id=orden_id,
        subtotal_mano_obra=subtotal_mo,
        subtotal_repuestos=subtotal_rp,
        descuento=datos.descuento,
        impuesto_pct=datos.impuesto_pct,
        valido_hasta=datos.valido_hasta,
        creado_por=await sesion.scalar(select(Perfil.id).where(Perfil.id == usuario.id)),
    )

    posicion = 0
    for m in mano_obra:
        posicion += 1
        presupuesto.items.append(
            PresupuestoItem(
                taller_id=usuario.taller_id,
                tipo=TipoLinea.MANO_OBRA.value,
                descripcion=m.descripcion,
                cantidad=m.horas,
                precio_unitario=m.tarifa_hora,
                orden_visual=posicion,
            )
        )
    for r in repuestos:
        posicion += 1
        presupuesto.items.append(
            PresupuestoItem(
                taller_id=usuario.taller_id,
                tipo=TipoLinea.REPUESTO.value,
                descripcion=r.descripcion,
                cantidad=r.cantidad,
                precio_unitario=r.precio_unitario,
                orden_visual=posicion,
            )
        )

    sesion.add(presupuesto)
    await _guardar(sesion)
    return await obtener(sesion, presupuesto.id)


async def actualizar(
    sesion: AsyncSession, presupuesto_id: UUID, datos: PresupuestoEditar
) -> Presupuesto:
    p = await obtener(sesion, presupuesto_id)
    if p.estado is not EstadoPresupuesto.BORRADOR:
        raise ErrorConflicto(
            f"El presupuesto v{p.version} ya fue enviado al cliente. "
            "Para cambiar montos hay que emitir una versión nueva.",
            {"estado": p.estado.value},
        )

    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(p, campo, valor)

    await _guardar(sesion)
    return await obtener(sesion, presupuesto_id)


async def enviar(sesion: AsyncSession, presupuesto_id: UUID) -> Presupuesto:
    """Sella el presupuesto y devuelve el enlace para el cliente."""
    p = await obtener(sesion, presupuesto_id)
    if p.estado is not EstadoPresupuesto.BORRADOR:
        raise ErrorConflicto(
            f"El presupuesto v{p.version} ya está {p.estado.etiqueta.lower()}.",
            {"estado": p.estado.value},
        )
    if not p.items:
        raise ErrorValidacion("Un presupuesto sin líneas no se puede enviar.")

    p.estado = EstadoPresupuesto.ENVIADO
    await _guardar(sesion)
    return await obtener(sesion, presupuesto_id)


async def responder(
    sesion: AsyncSession, presupuesto_id: UUID, respuesta: RespuestaCliente
) -> Presupuesto:
    """Registra la respuesta del cliente cuando la da por teléfono o en persona.

    Es el mismo desenlace que el enlace público, pero anotado por el asesor.
    """
    p = await obtener(sesion, presupuesto_id)
    await _aplicar_respuesta(sesion, p, respuesta)
    return await obtener(sesion, presupuesto_id)


# -----------------------------------------------------------------------------
# El camino público: sin sesión, resuelto por token
#
# PELIGRO: estas dos funciones usan el rol de servicio, que omite RLS. Es
# legítimo porque no hay usuario cuya identidad evaluar —quien abre el enlace es
# un cliente sin cuenta— y el token es la autorización. Por eso filtran siempre
# por `token_publico` y nunca aceptan un identificador de fila.
# -----------------------------------------------------------------------------


async def obtener_por_token(token: str) -> tuple[Presupuesto, OrdenServicio, Vehiculo, Taller]:
    async with sesion_servicio() as s:
        p = await s.scalar(
            select(Presupuesto).where(Presupuesto.token_publico == token).options(*_RELACIONES)
        )
        if p is None:
            raise ErrorNoEncontrado("Este enlace no corresponde a ningún presupuesto.")
        if p.estado is EstadoPresupuesto.BORRADOR:
            # Todavía no se le mandó a nadie: el enlace no debería circular.
            raise ErrorNoEncontrado("Este presupuesto aún no está disponible.")

        orden = await s.get(OrdenServicio, p.orden_id)
        vehiculo = await s.get(Vehiculo, orden.vehiculo_id) if orden else None
        taller = await s.get(Taller, p.taller_id)

        if orden is None or vehiculo is None or taller is None:
            raise ErrorNoEncontrado("Este enlace ya no es válido.")

        # Se desacoplan de la sesión antes de cerrarla.
        s.expunge_all()
        return p, orden, vehiculo, taller


async def responder_por_token(token: str, respuesta: RespuestaCliente) -> Presupuesto:
    async with sesion_servicio() as s:
        p = await s.scalar(
            select(Presupuesto).where(Presupuesto.token_publico == token).options(*_RELACIONES)
        )
        if p is None or p.estado is EstadoPresupuesto.BORRADOR:
            raise ErrorNoEncontrado("Este enlace no corresponde a ningún presupuesto.")

        await _aplicar_respuesta(s, p, respuesta)
        await s.refresh(p)
        s.expunge_all()
        return p


# -----------------------------------------------------------------------------


async def _aplicar_respuesta(
    sesion: AsyncSession, p: Presupuesto, respuesta: RespuestaCliente
) -> None:
    """Desenlace del presupuesto, venga del enlace público o del asesor."""
    if p.estado in CERRADOS:
        raise ErrorConflicto(
            f"Este presupuesto ya está {p.estado.etiqueta.lower()}.", {"estado": p.estado.value}
        )
    if esta_caducado(p):
        raise ErrorConflicto(
            f"El presupuesto venció el {p.valido_hasta:%d/%m/%Y}. "
            "Pide al taller que te envíe uno nuevo.",
            {"estado": "vencido"},
        )

    p.estado = EstadoPresupuesto.APROBADO if respuesta.aprobado else EstadoPresupuesto.RECHAZADO
    p.comentario_cliente = respuesta.comentario
    await _guardar(sesion)

    if respuesta.aprobado:
        await _avanzar_orden(sesion, p)


async def _avanzar_orden(sesion: AsyncSession, p: Presupuesto) -> None:
    """Mueve la orden a `aprobado` si estaba esperando esta respuesta.

    La transición la valida `mch_ordenes_guard` igual que siempre. La
    autorización por rol se salta sola: en el camino público no hay rol en los
    claims, y el trigger solo la comprueba cuando lo hay. Es exactamente el caso
    para el que se dejó esa excepción.

    Si la orden está en otro estado no se fuerza nada: puede que el asesor ya la
    hubiera movido a mano.
    """
    orden = await sesion.get(OrdenServicio, p.orden_id)
    if orden is None or orden.estado is not EstadoOrden.PRESUPUESTO_PENDIENTE:
        return

    await sesion.execute(
        text("SELECT set_config('mch.comentario_evento', :c, true)"),
        {"c": f"Presupuesto v{p.version} aprobado por el cliente"},
    )
    orden.estado = EstadoOrden.APROBADO
    await _guardar(sesion)


async def _guardar(sesion: AsyncSession) -> None:
    try:
        await sesion.flush()
    except (IntegrityError, DBAPIError) as exc:
        codigo = extraer_sqlstate(exc)
        if codigo == "23514":
            # Texto ya redactado por nuestros triggers.
            raise ErrorConflicto(str(exc).strip().splitlines()[0]) from exc
        if codigo == "23505":
            raise ErrorConflicto("Ya existe una versión con ese número.") from exc
        if codigo == "23503":
            raise ErrorValidacion("Alguna de las referencias no existe en tu taller.") from exc
        raise
