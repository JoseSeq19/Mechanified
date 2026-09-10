"""Lógica de negocio de las órdenes de servicio.

Como en el resto de los módulos, ninguna consulta filtra por `taller_id`: lo
añade RLS.

Lo propio de este módulo es el cambio de estado, y ahí hay una repartición de
responsabilidades que conviene tener clara:

  - `estados.validar()` rechaza antes de tocar la base, con un mensaje legible.
  - `mch_ordenes_guard` en Postgres vuelve a comprobarlo y es la barrera real.
  - `mch_ordenes_bitacora` escribe el evento. La aplicación no puede escribir en
    `orden_eventos`: es append-only y solo la toca ese trigger.

El comentario del evento llega al trigger por un ajuste local de transacción
(`mch.comentario_evento`), que es la única vía para pasarle contexto a algo que
la aplicación no puede escribir directamente. Ver la migración 20260909000400.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, func, or_, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ErrorConflicto, ErrorNoEncontrado, ErrorValidacion, extraer_sqlstate
from app.core.security import UsuarioAutenticado
from app.modules.clientes.models import Cliente
from app.modules.ordenes import estados as maquina
from app.modules.ordenes.estados import ORDEN_TABLERO, TERMINALES, EstadoOrden
from app.modules.ordenes.models import OrdenEvento, OrdenServicio
from app.modules.ordenes.schemas import CambioEstado, OrdenCrear, OrdenEditar
from app.modules.usuarios.models import Perfil
from app.modules.vehiculos.models import Vehiculo
from app.shared.paginacion import ParametrosPagina

MINIMO_BUSQUEDA = 3

_RELACIONES = (
    selectinload(OrdenServicio.cliente),
    selectinload(OrdenServicio.vehiculo),
    selectinload(OrdenServicio.asesor),
    selectinload(OrdenServicio.tecnico),
)


async def _perfil_del_taller(sesion: AsyncSession, perfil_id: UUID | None) -> UUID | None:
    """Confirma que el perfil existe y es visible para este usuario.

    RLS solo deja ver los perfiles del propio taller, así que si la consulta no
    devuelve nada, o no existe o es de otro taller. En ambos casos asignarlo
    fallaría después con un error de llave foránea que no dice nada útil.
    """
    if perfil_id is None:
        return None
    return await sesion.scalar(select(Perfil.id).where(Perfil.id == perfil_id))


async def _validar_asignaciones(
    sesion: AsyncSession, asesor_id: UUID | None, tecnico_id: UUID | None
) -> None:
    if asesor_id is not None and await _perfil_del_taller(sesion, asesor_id) is None:
        raise ErrorValidacion(
            "El asesor indicado no pertenece a tu taller.", {"campo": "asesor_id"}
        )
    if tecnico_id is not None and await _perfil_del_taller(sesion, tecnico_id) is None:
        raise ErrorValidacion(
            "El técnico indicado no pertenece a tu taller.", {"campo": "tecnico_id"}
        )


def _aplicar_filtros(
    stmt: Select,
    *,
    busqueda: str | None,
    estados: Sequence[EstadoOrden] | None,
    tecnico_id: UUID | None,
    cliente_id: UUID | None,
    vehiculo_id: UUID | None,
    incluir_cerradas: bool,
) -> Select:
    if estados:
        stmt = stmt.where(OrdenServicio.estado.in_(list(estados)))
    elif not incluir_cerradas:
        # Por omisión el listado es el trabajo vivo del taller. Las entregadas y
        # canceladas se piden a propósito.
        stmt = stmt.where(OrdenServicio.estado.notin_(list(TERMINALES)))

    if tecnico_id is not None:
        stmt = stmt.where(OrdenServicio.tecnico_id == tecnico_id)
    if cliente_id is not None:
        stmt = stmt.where(OrdenServicio.cliente_id == cliente_id)
    if vehiculo_id is not None:
        stmt = stmt.where(OrdenServicio.vehiculo_id == vehiculo_id)

    termino = (busqueda or "").strip()
    if len(termino) >= MINIMO_BUSQUEDA:
        patron = f"%{termino}%"
        # Se busca por folio, por placa y por nombre del cliente: son las tres
        # formas en que alguien identifica una orden en el mostrador.
        stmt = (
            stmt.join(Vehiculo, Vehiculo.id == OrdenServicio.vehiculo_id)
            .join(Cliente, Cliente.id == OrdenServicio.cliente_id)
            .where(
                or_(
                    OrdenServicio.folio.ilike(patron),
                    Vehiculo.placa.ilike(patron),
                    Cliente.nombre.ilike(patron),
                )
            )
        )
    return stmt


async def listar(
    sesion: AsyncSession,
    *,
    busqueda: str | None = None,
    estados: Sequence[EstadoOrden] | None = None,
    tecnico_id: UUID | None = None,
    cliente_id: UUID | None = None,
    vehiculo_id: UUID | None = None,
    incluir_cerradas: bool = False,
    pagina: ParametrosPagina,
) -> tuple[list[OrdenServicio], int]:
    base = _aplicar_filtros(
        select(OrdenServicio),
        busqueda=busqueda,
        estados=estados,
        tecnico_id=tecnico_id,
        cliente_id=cliente_id,
        vehiculo_id=vehiculo_id,
        incluir_cerradas=incluir_cerradas,
    )

    total = await sesion.scalar(select(func.count()).select_from(base.subquery())) or 0

    filas = await sesion.scalars(
        base.options(*_RELACIONES)
        .order_by(OrdenServicio.fecha_ingreso.desc())
        .limit(pagina.limite)
        .offset(pagina.desplazamiento)
    )
    return list(filas.all()), total


async def obtener(sesion: AsyncSession, orden_id: UUID) -> OrdenServicio:
    orden = await sesion.scalar(
        select(OrdenServicio).where(OrdenServicio.id == orden_id).options(*_RELACIONES)
    )
    if orden is None:
        raise ErrorNoEncontrado(f"No existe la orden {orden_id}.")
    return orden


async def resumen_tablero(sesion: AsyncSession) -> dict[EstadoOrden, int]:
    """Cuántas órdenes hay en cada estado, para las cabeceras del tablero.

    Un GROUP BY en vez de una consulta por columna: nueve estados serían nueve
    viajes a la base para pintar una sola pantalla.
    """
    filas = await sesion.execute(
        select(OrdenServicio.estado, func.count()).group_by(OrdenServicio.estado)
    )
    conteo = dict.fromkeys(ORDEN_TABLERO, 0)
    for estado, cantidad in filas.all():
        conteo[estado] = cantidad
    return conteo


async def crear(
    sesion: AsyncSession, datos: OrdenCrear, usuario: UsuarioAutenticado
) -> OrdenServicio:
    """Da de alta una orden. Nace en `recibido` y el folio lo pone la base."""
    await _validar_asignaciones(sesion, datos.asesor_id, datos.tecnico_id)

    # El autor solo se registra si tiene perfil vigente. Un token cuyo perfil se
    # dio de baja seguiría siendo válido hasta una hora, y con la referencia a
    # ciegas el alta fallaría con un error de llave foránea ilegible.
    autor = await _perfil_del_taller(sesion, usuario.id)

    valores = datos.model_dump()
    # Si quien la abre es el asesor y no indicó otro, se asigna a sí mismo: es
    # lo que va a pasar en el mostrador el 99% de las veces.
    if valores.get("asesor_id") is None and usuario.rol.value == "asesor_servicio":
        valores["asesor_id"] = autor

    orden = OrdenServicio(
        **valores,
        taller_id=usuario.taller_id,
        estado=EstadoOrden.RECIBIDO,
        creado_por=autor,
    )
    sesion.add(orden)

    try:
        await sesion.flush()
    except (IntegrityError, DBAPIError) as exc:
        codigo = extraer_sqlstate(exc)
        if codigo == "23503":
            raise ErrorValidacion(
                "El cliente o el vehículo indicados no existen en tu taller.",
                {"campos": ["cliente_id", "vehiculo_id"]},
            ) from exc
        if codigo == "23514":
            # Lo levanta mch_ordenes_guard, con un texto ya redactado: el
            # vehículo no es de ese cliente, o el taller no coincide.
            raise ErrorValidacion(str(exc).strip().splitlines()[0]) from exc
        raise

    # Se relee la fila entera en vez de refrescar solo las relaciones: el folio
    # y los totales los pone la base, y quedarían sin cargar.
    return await obtener(sesion, orden.id)


async def actualizar(sesion: AsyncSession, orden_id: UUID, datos: OrdenEditar) -> OrdenServicio:
    orden = await obtener(sesion, orden_id)

    cambios = datos.model_dump(exclude_unset=True)
    if "asesor_id" in cambios or "tecnico_id" in cambios:
        await _validar_asignaciones(
            sesion,
            cambios.get("asesor_id") if "asesor_id" in cambios else None,
            cambios.get("tecnico_id") if "tecnico_id" in cambios else None,
        )

    for campo, valor in cambios.items():
        setattr(orden, campo, valor)

    try:
        await sesion.flush()
    except (IntegrityError, DBAPIError) as exc:
        if extraer_sqlstate(exc) == "23503":
            raise ErrorValidacion("Alguna de las referencias no existe en tu taller.") from exc
        raise

    # Se relee la fila entera en vez de refrescar solo las relaciones: el folio
    # y los totales los pone la base, y quedarían sin cargar.
    return await obtener(sesion, orden.id)


async def cambiar_estado(
    sesion: AsyncSession, orden_id: UUID, cambio: CambioEstado, usuario: UsuarioAutenticado
) -> OrdenServicio:
    """Mueve la orden por el flujo, dejando rastro en la bitácora."""
    orden = await obtener(sesion, orden_id)

    # Rechazo temprano con un mensaje presentable. La base lo comprobará otra
    # vez y es la que manda.
    maquina.validar(orden.estado, cambio.estado, usuario.rol)

    # El comentario del evento viaja al trigger por un ajuste local de
    # transacción: `orden_eventos` no admite escritura desde la aplicación.
    await sesion.execute(
        text("SELECT set_config('mch.comentario_evento', :c, true)"),
        {"c": cambio.comentario or ""},
    )

    orden.estado = cambio.estado
    if cambio.estado is EstadoOrden.CANCELADO:
        orden.motivo_cancelacion = cambio.comentario

    try:
        await sesion.flush()
    except (IntegrityError, DBAPIError) as exc:
        codigo = extraer_sqlstate(exc)
        if codigo in {"23514", "42501"}:
            # La base rechazó la transición o el permiso. Que llegue aquí
            # significa que esta copia de la máquina de estados y la de Postgres
            # se han separado, así que se propaga su mensaje tal cual.
            raise ErrorConflicto(str(exc).strip().splitlines()[0]) from exc
        raise

    # Se relee la fila entera en vez de refrescar solo las relaciones: el folio
    # y los totales los pone la base, y quedarían sin cargar.
    return await obtener(sesion, orden.id)


async def historial(sesion: AsyncSession, orden_id: UUID) -> list[OrdenEvento]:
    """Bitácora de la orden, del evento más antiguo al más reciente."""
    await obtener(sesion, orden_id)  # 404 si es de otro taller

    filas = await sesion.scalars(
        select(OrdenEvento)
        .where(OrdenEvento.orden_id == orden_id)
        .options(selectinload(OrdenEvento.usuario))
        .order_by(OrdenEvento.creado_en, OrdenEvento.id)
    )
    return list(filas.all())
