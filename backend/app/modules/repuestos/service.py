"""Lógica del catálogo de repuestos y de las piezas de una orden.

Como en el resto de los módulos, RLS pone el filtro por taller.

Lo propio de este módulo es lo mismo que en mano de obra: **el precio se
congela**. Al agregar una pieza del catálogo se copian su nombre y su precio de
venta a la línea, y a partir de ahí la línea vive por su cuenta. Cambiar la
lista de precios del taller no puede reescribir una orden ya cotizada.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ErrorConflicto, ErrorNoEncontrado, ErrorValidacion, extraer_sqlstate
from app.core.security import UsuarioAutenticado
from app.modules.ordenes import service as srv_ordenes
from app.modules.ordenes.estados import TERMINALES
from app.modules.repuestos.models import EstadoItemRepuesto, OrdenRepuesto, Repuesto
from app.modules.repuestos.schemas import ItemCrear, ItemEditar, RepuestoCrear, RepuestoEditar
from app.modules.usuarios.models import Perfil
from app.shared.paginacion import ParametrosPagina

MINIMO_BUSQUEDA = 3

#: Piezas que todavía no están en el taller. Es lo que frena la reparación.
PENDIENTES = (
    EstadoItemRepuesto.SOLICITADO,
    EstadoItemRepuesto.COTIZADO,
    EstadoItemRepuesto.APROBADO,
)

_RELACIONES_ITEM = (
    selectinload(OrdenRepuesto.repuesto),
    selectinload(OrdenRepuesto.solicitante),
)


async def _orden_editable(sesion: AsyncSession, orden_id: UUID) -> None:
    orden = await srv_ordenes.obtener(sesion, orden_id)
    if orden.estado in TERMINALES:
        raise ErrorValidacion(
            f"La orden {orden.folio} está {orden.estado.etiqueta.lower()} y ya no admite cambios.",
            {"estado": orden.estado.value},
        )


# -----------------------------------------------------------------------------
# Catálogo
# -----------------------------------------------------------------------------


def _filtros_catalogo(stmt: Select, busqueda: str | None, solo_activos: bool) -> Select:
    if solo_activos:
        stmt = stmt.where(Repuesto.activo.is_(True))

    termino = (busqueda or "").strip()
    if len(termino) >= MINIMO_BUSQUEDA:
        patron = f"%{termino}%"
        stmt = stmt.where(
            or_(
                Repuesto.sku.ilike(patron),
                Repuesto.nombre.ilike(patron),
                Repuesto.categoria.ilike(patron),
            )
        )
    return stmt


async def listar_catalogo(
    sesion: AsyncSession,
    *,
    busqueda: str | None = None,
    solo_activos: bool = True,
    solo_bajo_minimo: bool = False,
    pagina: ParametrosPagina,
) -> tuple[list[Repuesto], int]:
    base = _filtros_catalogo(select(Repuesto), busqueda, solo_activos)
    if solo_bajo_minimo:
        base = base.where(Repuesto.stock <= Repuesto.stock_minimo)

    total = await sesion.scalar(select(func.count()).select_from(base.subquery())) or 0

    filas = await sesion.scalars(
        base.order_by(Repuesto.nombre).limit(pagina.limite).offset(pagina.desplazamiento)
    )
    return list(filas.all()), total


async def obtener_repuesto(sesion: AsyncSession, repuesto_id: UUID) -> Repuesto:
    repuesto = await sesion.get(Repuesto, repuesto_id)
    if repuesto is None:
        raise ErrorNoEncontrado(f"No existe el repuesto {repuesto_id}.")
    return repuesto


async def crear_repuesto(
    sesion: AsyncSession, datos: RepuestoCrear, usuario: UsuarioAutenticado
) -> Repuesto:
    repuesto = Repuesto(**datos.model_dump(), taller_id=usuario.taller_id)
    sesion.add(repuesto)
    await _guardar(sesion, sku=datos.sku)
    await sesion.refresh(repuesto)
    return repuesto


async def actualizar_repuesto(
    sesion: AsyncSession, repuesto_id: UUID, datos: RepuestoEditar
) -> Repuesto:
    repuesto = await obtener_repuesto(sesion, repuesto_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(repuesto, campo, valor)

    await _guardar(sesion, sku=datos.sku)
    await sesion.refresh(repuesto)
    return repuesto


async def eliminar_repuesto(sesion: AsyncSession, repuesto_id: UUID) -> None:
    """Borrado real.

    La referencia desde `orden_repuestos` es `on delete set null`, así que
    borrar una pieza del catálogo **no** rompe las órdenes que la usaron: sus
    líneas conservan la descripción y el precio que se copiaron al cargarlas.
    """
    repuesto = await obtener_repuesto(sesion, repuesto_id)
    await sesion.delete(repuesto)
    await _guardar(sesion)


# -----------------------------------------------------------------------------
# Piezas de una orden
# -----------------------------------------------------------------------------


async def listar_items(sesion: AsyncSession, orden_id: UUID) -> list[OrdenRepuesto]:
    await srv_ordenes.obtener(sesion, orden_id)

    filas = await sesion.scalars(
        select(OrdenRepuesto)
        .where(OrdenRepuesto.orden_id == orden_id)
        .options(*_RELACIONES_ITEM)
        .order_by(OrdenRepuesto.creado_en)
    )
    return list(filas.all())


async def resumen_items(sesion: AsyncSession, orden_id: UUID) -> tuple[Decimal, int]:
    fila = (
        await sesion.execute(
            select(
                func.coalesce(func.sum(OrdenRepuesto.subtotal), 0),
                func.count().filter(OrdenRepuesto.estado.in_(list(PENDIENTES))),
            ).where(OrdenRepuesto.orden_id == orden_id)
        )
    ).one()
    return Decimal(str(fila[0])), int(fila[1])


async def obtener_item(sesion: AsyncSession, item_id: UUID) -> OrdenRepuesto:
    item = await sesion.scalar(
        select(OrdenRepuesto).where(OrdenRepuesto.id == item_id).options(*_RELACIONES_ITEM)
    )
    if item is None:
        raise ErrorNoEncontrado(f"No existe la línea de repuesto {item_id}.")
    return item


async def agregar_item(
    sesion: AsyncSession, orden_id: UUID, datos: ItemCrear, usuario: UsuarioAutenticado
) -> OrdenRepuesto:
    await _orden_editable(sesion, orden_id)

    descripcion = datos.descripcion
    precio = datos.precio_unitario

    if datos.repuesto_id is not None:
        # RLS hace invisible el catálogo de otro taller, así que un id ajeno
        # simplemente no aparece.
        repuesto = await sesion.get(Repuesto, datos.repuesto_id)
        if repuesto is None:
            raise ErrorValidacion(
                "El repuesto indicado no existe en tu catálogo.", {"campo": "repuesto_id"}
            )
        # Lo que se escribió a mano manda sobre el catálogo: a veces se ajusta
        # el precio de una pieza concreta al cotizar.
        descripcion = descripcion or repuesto.nombre
        precio = precio if precio is not None else repuesto.precio_venta

    solicitante = await sesion.scalar(select(Perfil.id).where(Perfil.id == usuario.id))

    item = OrdenRepuesto(
        taller_id=usuario.taller_id,
        orden_id=orden_id,
        repuesto_id=datos.repuesto_id,
        descripcion=descripcion,
        cantidad=datos.cantidad,
        precio_unitario=precio,
        estado=datos.estado,
        notas=datos.notas,
        solicitado_por=solicitante,
    )
    sesion.add(item)
    await _guardar(sesion)
    return await obtener_item(sesion, item.id)


async def actualizar_item(sesion: AsyncSession, item_id: UUID, datos: ItemEditar) -> OrdenRepuesto:
    item = await obtener_item(sesion, item_id)
    await _orden_editable(sesion, item.orden_id)

    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(item, campo, valor)

    await _guardar(sesion)
    return await obtener_item(sesion, item_id)


async def eliminar_item(sesion: AsyncSession, item_id: UUID) -> None:
    item = await obtener_item(sesion, item_id)
    await _orden_editable(sesion, item.orden_id)
    await sesion.delete(item)
    await _guardar(sesion)


# -----------------------------------------------------------------------------


async def _guardar(sesion: AsyncSession, *, sku: str | None = None) -> None:
    try:
        await sesion.flush()
    except (IntegrityError, DBAPIError) as exc:
        codigo = extraer_sqlstate(exc)
        if codigo == "23505":
            raise ErrorConflicto(
                f"Ya hay un repuesto con el código {sku!r} en el catálogo."
                if sku
                else "Ya existe un repuesto con esos datos.",
                {"campo": "sku"},
            ) from exc
        if codigo == "23514":
            # Texto ya redactado por nuestros triggers.
            raise ErrorValidacion(str(exc).strip().splitlines()[0]) from exc
        if codigo == "23503":
            raise ErrorValidacion("Alguna de las referencias no existe en tu taller.") from exc
        raise
