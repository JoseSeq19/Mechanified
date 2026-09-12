"""Lógica de diagnósticos, hallazgos y mano de obra.

Como en el resto de los módulos, RLS pone el filtro por taller.

Dos reglas propias que conviene tener presentes:

  - La **tarifa por hora se congela** en la línea. Se copia de la configuración
    del taller al crearla, y a partir de ahí no la mueve nadie: subir la tarifa
    del taller no puede alterar lo que ya se le cotizó a un cliente.
  - Las líneas **no se tocan en una orden cerrada**. Lo impide también un
    trigger (migración 20260912000100); aquí se rechaza antes para dar un
    mensaje decente.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ErrorNoEncontrado, ErrorValidacion, extraer_sqlstate
from app.core.security import UsuarioAutenticado
from app.modules.diagnosticos.models import Diagnostico, DiagnosticoHallazgo, ManoObra
from app.modules.diagnosticos.schemas import (
    DiagnosticoCrear,
    DiagnosticoEditar,
    HallazgoCrear,
    HallazgoEditar,
    ManoObraCrear,
    ManoObraEditar,
)
from app.modules.ordenes import service as srv_ordenes
from app.modules.ordenes.estados import TERMINALES
from app.modules.talleres.models import Taller
from app.modules.usuarios.models import Perfil

_RELACIONES_DIAG = (selectinload(Diagnostico.hallazgos), selectinload(Diagnostico.tecnico))


async def _orden_editable(sesion: AsyncSession, orden_id: UUID) -> None:
    """404 si la orden no es de este taller; 422 si ya está cerrada."""
    orden = await srv_ordenes.obtener(sesion, orden_id)
    if orden.estado in TERMINALES:
        raise ErrorValidacion(
            f"La orden {orden.folio} está {orden.estado.etiqueta.lower()} y ya no admite cambios.",
            {"estado": orden.estado.value},
        )


async def _perfil_valido(sesion: AsyncSession, perfil_id: UUID | None) -> UUID | None:
    if perfil_id is None:
        return None
    return await sesion.scalar(select(Perfil.id).where(Perfil.id == perfil_id))


async def _tarifa_del_taller(sesion: AsyncSession, taller_id: UUID) -> Decimal:
    tarifa = await sesion.scalar(select(Taller.tarifa_hora_default).where(Taller.id == taller_id))
    return tarifa if tarifa is not None else Decimal("0")


# -----------------------------------------------------------------------------
# Diagnósticos
# -----------------------------------------------------------------------------


async def listar_diagnosticos(sesion: AsyncSession, orden_id: UUID) -> list[Diagnostico]:
    await srv_ordenes.obtener(sesion, orden_id)  # 404 si es de otro taller

    filas = await sesion.scalars(
        select(Diagnostico)
        .where(Diagnostico.orden_id == orden_id)
        .options(*_RELACIONES_DIAG)
        .order_by(Diagnostico.creado_en)
    )
    return list(filas.all())


async def obtener_diagnostico(sesion: AsyncSession, diagnostico_id: UUID) -> Diagnostico:
    """Lee el diagnóstico con sus hallazgos.

    `populate_existing` no es opcional aquí: este servicio consulta siempre justo
    después de escribir, y sin él SQLAlchemy devolvería el objeto que ya tiene en
    el mapa de identidad **sin refrescar** las relaciones ya cargadas. El
    resultado sería una respuesta que no incluye lo que se acaba de guardar.
    """
    diagnostico = await sesion.scalar(
        select(Diagnostico)
        .where(Diagnostico.id == diagnostico_id)
        .options(*_RELACIONES_DIAG)
        .execution_options(populate_existing=True)
    )
    if diagnostico is None:
        raise ErrorNoEncontrado(f"No existe el diagnóstico {diagnostico_id}.")
    return diagnostico


async def crear_diagnostico(
    sesion: AsyncSession, orden_id: UUID, datos: DiagnosticoCrear, usuario: UsuarioAutenticado
) -> Diagnostico:
    await _orden_editable(sesion, orden_id)

    # Si el técnico no se indica, se toma a quien lo está escribiendo, que es
    # quien tiene el vehículo delante.
    tecnico_id = await _perfil_valido(sesion, datos.tecnico_id)
    if datos.tecnico_id is not None and tecnico_id is None:
        raise ErrorValidacion(
            "El técnico indicado no pertenece a tu taller.", {"campo": "tecnico_id"}
        )
    if tecnico_id is None:
        tecnico_id = await _perfil_valido(sesion, usuario.id)

    diagnostico = Diagnostico(
        taller_id=usuario.taller_id,
        orden_id=orden_id,
        tecnico_id=tecnico_id,
        resumen=datos.resumen,
        horas_estimadas=datos.horas_estimadas,
    )
    for posicion, hallazgo in enumerate(datos.hallazgos, start=1):
        diagnostico.hallazgos.append(
            DiagnosticoHallazgo(
                taller_id=usuario.taller_id,
                sistema=hallazgo.sistema,
                descripcion=hallazgo.descripcion,
                severidad=hallazgo.severidad,
                requiere_repuesto=hallazgo.requiere_repuesto,
                orden_visual=posicion,
            )
        )

    sesion.add(diagnostico)
    await _guardar(sesion)
    return await obtener_diagnostico(sesion, diagnostico.id)


async def actualizar_diagnostico(
    sesion: AsyncSession, diagnostico_id: UUID, datos: DiagnosticoEditar
) -> Diagnostico:
    diagnostico = await obtener_diagnostico(sesion, diagnostico_id)
    await _orden_editable(sesion, diagnostico.orden_id)

    cambios = datos.model_dump(exclude_unset=True)
    if (
        cambios.get("tecnico_id") is not None
        and await _perfil_valido(sesion, cambios["tecnico_id"]) is None
    ):
        raise ErrorValidacion(
            "El técnico indicado no pertenece a tu taller.", {"campo": "tecnico_id"}
        )

    for campo, valor in cambios.items():
        setattr(diagnostico, campo, valor)

    await _guardar(sesion)
    return await obtener_diagnostico(sesion, diagnostico_id)


async def eliminar_diagnostico(sesion: AsyncSession, diagnostico_id: UUID) -> None:
    diagnostico = await obtener_diagnostico(sesion, diagnostico_id)
    await _orden_editable(sesion, diagnostico.orden_id)
    await sesion.delete(diagnostico)
    await _guardar(sesion)


# -----------------------------------------------------------------------------
# Hallazgos
# -----------------------------------------------------------------------------


async def agregar_hallazgo(
    sesion: AsyncSession, diagnostico_id: UUID, datos: HallazgoCrear
) -> Diagnostico:
    diagnostico = await obtener_diagnostico(sesion, diagnostico_id)
    await _orden_editable(sesion, diagnostico.orden_id)

    siguiente = max((h.orden_visual for h in diagnostico.hallazgos), default=0) + 1
    diagnostico.hallazgos.append(
        DiagnosticoHallazgo(
            taller_id=diagnostico.taller_id,
            sistema=datos.sistema,
            descripcion=datos.descripcion,
            severidad=datos.severidad,
            requiere_repuesto=datos.requiere_repuesto,
            orden_visual=siguiente,
        )
    )
    await _guardar(sesion)
    return await obtener_diagnostico(sesion, diagnostico_id)


async def actualizar_hallazgo(
    sesion: AsyncSession, hallazgo_id: UUID, datos: HallazgoEditar
) -> Diagnostico:
    hallazgo = await sesion.get(DiagnosticoHallazgo, hallazgo_id)
    if hallazgo is None:
        raise ErrorNoEncontrado(f"No existe el hallazgo {hallazgo_id}.")

    diagnostico = await obtener_diagnostico(sesion, hallazgo.diagnostico_id)
    await _orden_editable(sesion, diagnostico.orden_id)

    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(hallazgo, campo, valor)

    await _guardar(sesion)
    return await obtener_diagnostico(sesion, hallazgo.diagnostico_id)


async def eliminar_hallazgo(sesion: AsyncSession, hallazgo_id: UUID) -> None:
    hallazgo = await sesion.get(DiagnosticoHallazgo, hallazgo_id)
    if hallazgo is None:
        raise ErrorNoEncontrado(f"No existe el hallazgo {hallazgo_id}.")

    diagnostico = await obtener_diagnostico(sesion, hallazgo.diagnostico_id)
    await _orden_editable(sesion, diagnostico.orden_id)

    await sesion.delete(hallazgo)
    await _guardar(sesion)


# -----------------------------------------------------------------------------
# Mano de obra
# -----------------------------------------------------------------------------


async def listar_mano_obra(sesion: AsyncSession, orden_id: UUID) -> list[ManoObra]:
    await srv_ordenes.obtener(sesion, orden_id)

    filas = await sesion.scalars(
        select(ManoObra)
        .where(ManoObra.orden_id == orden_id)
        .options(selectinload(ManoObra.tecnico))
        .order_by(ManoObra.creado_en)
    )
    return list(filas.all())


async def total_mano_obra(sesion: AsyncSession, orden_id: UUID) -> tuple[Decimal, Decimal]:
    """Horas y dinero que suman las líneas de la orden."""
    fila = (
        await sesion.execute(
            select(
                func.coalesce(func.sum(ManoObra.horas), 0),
                func.coalesce(func.sum(ManoObra.subtotal), 0),
            ).where(ManoObra.orden_id == orden_id)
        )
    ).one()
    return Decimal(str(fila[0])), Decimal(str(fila[1]))


async def obtener_mano_obra(sesion: AsyncSession, linea_id: UUID) -> ManoObra:
    linea = await sesion.scalar(
        select(ManoObra).where(ManoObra.id == linea_id).options(selectinload(ManoObra.tecnico))
    )
    if linea is None:
        raise ErrorNoEncontrado(f"No existe la línea de mano de obra {linea_id}.")
    return linea


async def crear_mano_obra(
    sesion: AsyncSession, orden_id: UUID, datos: ManoObraCrear, usuario: UsuarioAutenticado
) -> ManoObra:
    await _orden_editable(sesion, orden_id)

    tecnico_id = await _perfil_valido(sesion, datos.tecnico_id)
    if datos.tecnico_id is not None and tecnico_id is None:
        raise ErrorValidacion(
            "El técnico indicado no pertenece a tu taller.", {"campo": "tecnico_id"}
        )
    if tecnico_id is None:
        tecnico_id = await _perfil_valido(sesion, usuario.id)

    tarifa = (
        datos.tarifa_hora
        if datos.tarifa_hora is not None
        else await _tarifa_del_taller(sesion, usuario.taller_id)
    )

    linea = ManoObra(
        taller_id=usuario.taller_id,
        orden_id=orden_id,
        descripcion=datos.descripcion,
        horas=datos.horas,
        tarifa_hora=tarifa,
        tecnico_id=tecnico_id,
    )
    sesion.add(linea)
    await _guardar(sesion)
    return await obtener_mano_obra(sesion, linea.id)


async def actualizar_mano_obra(
    sesion: AsyncSession, linea_id: UUID, datos: ManoObraEditar
) -> ManoObra:
    linea = await obtener_mano_obra(sesion, linea_id)
    await _orden_editable(sesion, linea.orden_id)

    cambios = datos.model_dump(exclude_unset=True)
    if (
        cambios.get("tecnico_id") is not None
        and await _perfil_valido(sesion, cambios["tecnico_id"]) is None
    ):
        raise ErrorValidacion(
            "El técnico indicado no pertenece a tu taller.", {"campo": "tecnico_id"}
        )

    for campo, valor in cambios.items():
        setattr(linea, campo, valor)

    await _guardar(sesion)
    return await obtener_mano_obra(sesion, linea_id)


async def eliminar_mano_obra(sesion: AsyncSession, linea_id: UUID) -> None:
    linea = await obtener_mano_obra(sesion, linea_id)
    await _orden_editable(sesion, linea.orden_id)
    await sesion.delete(linea)
    await _guardar(sesion)


# -----------------------------------------------------------------------------


async def _guardar(sesion: AsyncSession) -> None:
    """Vuelca los cambios traduciendo los rechazos de la base.

    El 23514 lo levantan nuestros triggers con un texto ya redactado para una
    persona; el 23503 aparece cuando una referencia apunta fuera del taller.
    """
    try:
        await sesion.flush()
    except (IntegrityError, DBAPIError) as exc:
        codigo = extraer_sqlstate(exc)
        if codigo == "23514":
            raise ErrorValidacion(str(exc).strip().splitlines()[0]) from exc
        if codigo == "23503":
            raise ErrorValidacion("Alguna de las referencias no existe en tu taller.") from exc
        raise
