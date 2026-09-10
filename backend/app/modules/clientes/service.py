"""Lógica de negocio de clientes.

Nota sobre lo que **no** hay aquí: ninguna consulta filtra por `taller_id`.

No es un olvido. La sesión llega con `SET LOCAL ROLE authenticated` y los claims
del usuario, así que Postgres añade `taller_id = mch_taller_actual()` a cada
SELECT, UPDATE y DELETE por política. Repetir el filtro en Python daría una
falsa sensación de que es lo que protege, cuando la protección real está abajo y
sigue en pie aunque alguien consulte por otra vía.

Lo verifica `tests/integration/test_clientes.py::test_no_ve_clientes_de_otro_taller`.

La excepción es `crear`: al insertar hay que *decidir* el taller, y se toma del
token, nunca del cuerpo de la petición.
"""

from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ErrorConflicto, ErrorNoEncontrado, extraer_sqlstate
from app.core.security import UsuarioAutenticado
from app.modules.clientes.models import Cliente
from app.modules.clientes.schemas import ClienteCrear, ClienteEditar
from app.shared.paginacion import ParametrosPagina

#: Por debajo de 3 caracteres el índice de trigramas no ayuda y la búsqueda
#: devolvería medio padrón. Se ignora el término en ese caso.
MINIMO_BUSQUEDA = 3


def _aplicar_filtros(stmt: Select, busqueda: str | None, solo_activos: bool) -> Select:
    if solo_activos:
        stmt = stmt.where(Cliente.activo.is_(True))

    termino = (busqueda or "").strip()
    if len(termino) >= MINIMO_BUSQUEDA:
        patron = f"%{termino}%"
        stmt = stmt.where(
            or_(
                Cliente.nombre.ilike(patron),
                Cliente.documento.ilike(patron),
                Cliente.telefono.ilike(patron),
                Cliente.email.ilike(patron),
            )
        )
    return stmt


async def listar(
    sesion: AsyncSession,
    *,
    busqueda: str | None = None,
    solo_activos: bool = True,
    pagina: ParametrosPagina,
) -> tuple[list[Cliente], int]:
    """Devuelve el tramo pedido y el total que cumple los filtros."""
    base = _aplicar_filtros(select(Cliente), busqueda, solo_activos)

    total = await sesion.scalar(select(func.count()).select_from(base.subquery())) or 0

    filas = await sesion.scalars(
        base.order_by(Cliente.nombre).limit(pagina.limite).offset(pagina.desplazamiento)
    )
    return list(filas.all()), total


async def obtener(sesion: AsyncSession, cliente_id: UUID) -> Cliente:
    """Busca un cliente por id.

    Un cliente de otro taller es invisible por RLS, así que `get` devuelve None
    y esto responde 404. Es lo correcto: un 403 confirmaría que el registro
    existe, y eso ya sería filtrar información entre talleres.
    """
    cliente = await sesion.get(Cliente, cliente_id)
    if cliente is None:
        raise ErrorNoEncontrado(f"No existe el cliente {cliente_id}.")
    return cliente


async def crear(sesion: AsyncSession, datos: ClienteCrear, usuario: UsuarioAutenticado) -> Cliente:
    cliente = Cliente(**datos.model_dump(), taller_id=usuario.taller_id)
    sesion.add(cliente)

    try:
        await sesion.flush()
    except IntegrityError as exc:
        if extraer_sqlstate(exc) == "23505":
            raise ErrorConflicto(
                f"Ya hay un cliente registrado con el documento {datos.documento!r}.",
                {"campo": "documento"},
            ) from exc
        raise

    await sesion.refresh(cliente)
    return cliente


async def actualizar(sesion: AsyncSession, cliente_id: UUID, datos: ClienteEditar) -> Cliente:
    cliente = await obtener(sesion, cliente_id)

    # exclude_unset distingue "no vino el campo" de "vino en null". Sin esto, un
    # PATCH que solo cambia el teléfono borraría todo lo demás.
    cambios = datos.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        setattr(cliente, campo, valor)

    try:
        await sesion.flush()
    except IntegrityError as exc:
        if extraer_sqlstate(exc) == "23505":
            raise ErrorConflicto(
                "Ya hay otro cliente con ese documento.", {"campo": "documento"}
            ) from exc
        raise

    await sesion.refresh(cliente)
    return cliente


async def eliminar(sesion: AsyncSession, cliente_id: UUID) -> None:
    """Borrado real. Falla si el cliente tiene vehículos.

    La llave foránea de `vehiculos` es RESTRICT a propósito: borrar un cliente
    con historial destruiría la trazabilidad de sus órdenes. Para dar de baja a
    alguien que ya no viene, lo correcto es `activo = false` vía PATCH.
    """
    cliente = await obtener(sesion, cliente_id)
    await sesion.delete(cliente)

    try:
        await sesion.flush()
    except IntegrityError as exc:
        if extraer_sqlstate(exc) == "23503":
            raise ErrorConflicto(
                "El cliente tiene vehículos registrados y no se puede borrar. "
                "Desactívalo en su lugar.",
                {"sugerencia": "PATCH con activo=false"},
            ) from exc
        raise
