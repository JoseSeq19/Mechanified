"""Lógica de negocio de vehículos.

Como en clientes, ninguna consulta filtra por `taller_id`: lo añade RLS. Ver la
nota extensa en `app/modules/clientes/service.py`.

Lo propio de este módulo es traducir los tres choques que la base puede
devolver, porque cada uno significa algo distinto para quien está en recepción:

  - placa repetida  -> ese vehículo ya está registrado
  - VIN repetido    -> idem, pero detectado por número de chasis
  - cliente ajeno   -> el propietario indicado no es de este taller
"""

from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ErrorConflicto, ErrorNoEncontrado, ErrorValidacion, extraer_sqlstate
from app.core.security import UsuarioAutenticado
from app.modules.vehiculos.models import Vehiculo
from app.modules.vehiculos.schemas import VehiculoCrear, VehiculoEditar
from app.shared.paginacion import ParametrosPagina

MINIMO_BUSQUEDA = 3


def _conflicto_de_unicidad(exc: Exception) -> ErrorConflicto:
    """Distingue qué índice único se violó, por el nombre del índice.

    Se buscan los nombres completos y no las palabras "placa" o "vin" sueltas:
    el texto de la excepción arrastra la sentencia INSERT entera, cuya lista de
    columnas contiene ambas, así que cualquier choque parecería de placa.
    """
    texto = str(exc)
    if "vehiculos_taller_placa_uidx" in texto:
        return ErrorConflicto("Ya hay un vehículo con esa placa en el taller.", {"campo": "placa"})
    if "vehiculos_taller_vin_uidx" in texto:
        return ErrorConflicto("Ya hay un vehículo con ese VIN en el taller.", {"campo": "vin"})
    return ErrorConflicto("Ya existe un vehículo con esos datos.")


def _aplicar_filtros(
    stmt: Select, busqueda: str | None, cliente_id: UUID | None, solo_activos: bool
) -> Select:
    if solo_activos:
        stmt = stmt.where(Vehiculo.activo.is_(True))
    if cliente_id is not None:
        stmt = stmt.where(Vehiculo.cliente_id == cliente_id)

    termino = (busqueda or "").strip()
    if len(termino) >= MINIMO_BUSQUEDA:
        patron = f"%{termino}%"
        stmt = stmt.where(
            or_(
                Vehiculo.placa.ilike(patron),
                Vehiculo.vin.ilike(patron),
                Vehiculo.marca.ilike(patron),
                Vehiculo.modelo.ilike(patron),
            )
        )
    return stmt


async def listar(
    sesion: AsyncSession,
    *,
    busqueda: str | None = None,
    cliente_id: UUID | None = None,
    solo_activos: bool = True,
    pagina: ParametrosPagina,
) -> tuple[list[Vehiculo], int]:
    base = _aplicar_filtros(select(Vehiculo), busqueda, cliente_id, solo_activos)

    total = await sesion.scalar(select(func.count()).select_from(base.subquery())) or 0

    filas = await sesion.scalars(
        base.options(selectinload(Vehiculo.cliente))
        .order_by(Vehiculo.placa)
        .limit(pagina.limite)
        .offset(pagina.desplazamiento)
    )
    return list(filas.all()), total


async def obtener(sesion: AsyncSession, vehiculo_id: UUID) -> Vehiculo:
    """Un vehículo de otro taller es invisible por RLS, así que sale 404."""
    vehiculo = await sesion.scalar(
        select(Vehiculo).where(Vehiculo.id == vehiculo_id).options(selectinload(Vehiculo.cliente))
    )
    if vehiculo is None:
        raise ErrorNoEncontrado(f"No existe el vehículo {vehiculo_id}.")
    return vehiculo


async def crear(
    sesion: AsyncSession, datos: VehiculoCrear, usuario: UsuarioAutenticado
) -> Vehiculo:
    vehiculo = Vehiculo(**datos.model_dump(), taller_id=usuario.taller_id)
    sesion.add(vehiculo)

    try:
        await sesion.flush()
    except IntegrityError as exc:
        if extraer_sqlstate(exc) == "23505":
            raise _conflicto_de_unicidad(exc) from exc
        if extraer_sqlstate(exc) == "23503":
            raise ErrorValidacion(
                "El cliente indicado no existe en tu taller.", {"campo": "cliente_id"}
            ) from exc
        raise
    except DBAPIError as exc:
        # El trigger mch_vehiculos_guard usa foreign_key_violation cuando el
        # cliente pertenece a otro taller. No siempre llega como IntegrityError.
        if extraer_sqlstate(exc) == "23503":
            raise ErrorValidacion(
                "El cliente indicado no existe en tu taller.", {"campo": "cliente_id"}
            ) from exc
        raise

    await sesion.refresh(vehiculo, attribute_names=["cliente"])
    return vehiculo


async def actualizar(sesion: AsyncSession, vehiculo_id: UUID, datos: VehiculoEditar) -> Vehiculo:
    vehiculo = await obtener(sesion, vehiculo_id)

    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(vehiculo, campo, valor)

    try:
        await sesion.flush()
    except IntegrityError as exc:
        if extraer_sqlstate(exc) == "23505":
            raise _conflicto_de_unicidad(exc) from exc
        raise
    except DBAPIError as exc:
        if extraer_sqlstate(exc) == "23503":
            raise ErrorValidacion(
                "El cliente indicado no existe en tu taller.", {"campo": "cliente_id"}
            ) from exc
        raise

    await sesion.refresh(vehiculo, attribute_names=["cliente"])
    return vehiculo


async def eliminar(sesion: AsyncSession, vehiculo_id: UUID) -> None:
    """Borrado real. Falla si el vehículo ya pasó por el taller.

    La FK desde `ordenes_servicio` es RESTRICT: borrar el vehículo dejaría
    órdenes apuntando al vacío y perdería el historial por placa, que es
    justamente lo que da valor al registro.
    """
    vehiculo = await obtener(sesion, vehiculo_id)
    await sesion.delete(vehiculo)

    try:
        await sesion.flush()
    except IntegrityError as exc:
        if extraer_sqlstate(exc) == "23503":
            raise ErrorConflicto(
                "El vehículo tiene órdenes de servicio y no se puede borrar. "
                "Desactívalo en su lugar.",
                {"sugerencia": "PATCH con activo=false"},
            ) from exc
        raise
