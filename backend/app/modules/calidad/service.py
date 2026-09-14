"""Lógica del checklist configurable y de los controles de calidad.

Como en el resto de los módulos, RLS pone el filtro por taller.

Tres reglas propias:

  1. **Iniciar un control copia la plantilla.** Los puntos se duplican en
     `control_calidad_respuestas`, así que editar la plantilla después no
     reescribe inspecciones ya hechas.
  2. **Un punto obligatorio tiene que quedar conforme** para aprobar. Lo impide
     el trigger `mch_controles_calidad_cierre`; aquí se adelanta el rechazo con
     la lista de lo que falta. Ojo: "no aplica" en un punto obligatorio también
     bloquea. Si un punto puede no aplicar a algunos vehículos, no debería ser
     obligatorio en la plantilla.
  3. **Cerrar el control mueve la orden.** Aprobarlo la pasa a
     `listo_para_entrega`; rechazarlo la devuelve a `en_reparacion`, que es
     justo para lo que existe esa transición. Se hace en la misma transacción:
     si la orden no puede moverse, el control tampoco queda cerrado.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ErrorConflicto, ErrorNoEncontrado, ErrorValidacion, extraer_sqlstate
from app.core.security import UsuarioAutenticado
from app.modules.calidad.models import (
    Control,
    Plantilla,
    PlantillaItem,
    Respuesta,
    ResultadoCheck,
    ResultadoControl,
)
from app.modules.calidad.schemas import (
    CerrarControl,
    ControlEditar,
    ControlIniciar,
    PlantillaCrear,
    PlantillaEditar,
    PuntoCrear,
    PuntoEditar,
    RespuestaEditar,
)
from app.modules.ordenes import service as srv_ordenes
from app.modules.ordenes.estados import TERMINALES, EstadoOrden
from app.modules.ordenes.schemas import CambioEstado
from app.modules.usuarios.models import Perfil

_REL_PLANTILLA = (selectinload(Plantilla.puntos),)
_REL_CONTROL = (
    selectinload(Control.respuestas).selectinload(Respuesta.item),
    selectinload(Control.inspector),
)


def pendientes(control: Control) -> list[Respuesta]:
    """Puntos obligatorios que todavía no están conformes.

    Mismo criterio que el trigger: si el punto de la plantilla ya no existe, no
    se sabe si era obligatorio, y deja de bloquear.
    """
    return [
        r
        for r in control.respuestas
        if r.item is not None and r.item.obligatorio and r.resultado is not ResultadoCheck.OK
    ]


async def _perfil(sesion: AsyncSession, perfil_id: UUID | None) -> UUID | None:
    if perfil_id is None:
        return None
    return await sesion.scalar(select(Perfil.id).where(Perfil.id == perfil_id))


# -----------------------------------------------------------------------------
# Plantillas
# -----------------------------------------------------------------------------


async def listar_plantillas(sesion: AsyncSession, *, solo_activas: bool = True) -> list[Plantilla]:
    consulta = select(Plantilla).options(*_REL_PLANTILLA).order_by(Plantilla.nombre)
    if solo_activas:
        consulta = consulta.where(Plantilla.activo.is_(True))
    return list((await sesion.scalars(consulta)).all())


async def obtener_plantilla(sesion: AsyncSession, plantilla_id: UUID) -> Plantilla:
    plantilla = await sesion.scalar(
        select(Plantilla)
        .where(Plantilla.id == plantilla_id)
        .options(*_REL_PLANTILLA)
        .execution_options(populate_existing=True)
    )
    if plantilla is None:
        raise ErrorNoEncontrado(f"No existe la plantilla {plantilla_id}.")
    return plantilla


async def crear_plantilla(
    sesion: AsyncSession, datos: PlantillaCrear, usuario: UsuarioAutenticado
) -> Plantilla:
    plantilla = Plantilla(
        taller_id=usuario.taller_id, nombre=datos.nombre, descripcion=datos.descripcion
    )
    for posicion, punto in enumerate(datos.puntos, start=1):
        plantilla.puntos.append(
            PlantillaItem(
                taller_id=usuario.taller_id,
                categoria=punto.categoria,
                descripcion=punto.descripcion,
                obligatorio=punto.obligatorio,
                orden_visual=posicion,
            )
        )

    sesion.add(plantilla)
    await _guardar(sesion, nombre=datos.nombre)
    return await obtener_plantilla(sesion, plantilla.id)


async def actualizar_plantilla(
    sesion: AsyncSession, plantilla_id: UUID, datos: PlantillaEditar
) -> Plantilla:
    plantilla = await obtener_plantilla(sesion, plantilla_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(plantilla, campo, valor)

    await _guardar(sesion, nombre=datos.nombre)
    return await obtener_plantilla(sesion, plantilla_id)


async def eliminar_plantilla(sesion: AsyncSession, plantilla_id: UUID) -> None:
    """Borrado real.

    No rompe controles ya hechos —sus respuestas son copias—, pero sí les quita
    la referencia a qué puntos eran obligatorios. Para retirar una plantilla que
    ya se usó, lo recomendable es desactivarla.
    """
    plantilla = await obtener_plantilla(sesion, plantilla_id)
    await sesion.delete(plantilla)
    await _guardar(sesion)


async def agregar_punto(sesion: AsyncSession, plantilla_id: UUID, datos: PuntoCrear) -> Plantilla:
    plantilla = await obtener_plantilla(sesion, plantilla_id)
    siguiente = max((p.orden_visual for p in plantilla.puntos), default=0) + 1
    plantilla.puntos.append(
        PlantillaItem(
            taller_id=plantilla.taller_id,
            categoria=datos.categoria,
            descripcion=datos.descripcion,
            obligatorio=datos.obligatorio,
            orden_visual=siguiente,
        )
    )
    await _guardar(sesion)
    return await obtener_plantilla(sesion, plantilla_id)


async def actualizar_punto(sesion: AsyncSession, punto_id: UUID, datos: PuntoEditar) -> Plantilla:
    punto = await sesion.get(PlantillaItem, punto_id)
    if punto is None:
        raise ErrorNoEncontrado(f"No existe el punto {punto_id}.")

    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(punto, campo, valor)

    await _guardar(sesion)
    return await obtener_plantilla(sesion, punto.plantilla_id)


async def eliminar_punto(sesion: AsyncSession, punto_id: UUID) -> None:
    punto = await sesion.get(PlantillaItem, punto_id)
    if punto is None:
        raise ErrorNoEncontrado(f"No existe el punto {punto_id}.")
    await sesion.delete(punto)
    await _guardar(sesion)


# -----------------------------------------------------------------------------
# Controles
# -----------------------------------------------------------------------------


async def listar_controles(sesion: AsyncSession, orden_id: UUID) -> list[Control]:
    await srv_ordenes.obtener(sesion, orden_id)  # 404 si es de otro taller

    filas = await sesion.scalars(
        select(Control)
        .where(Control.orden_id == orden_id)
        .options(*_REL_CONTROL)
        .order_by(Control.creado_en)
    )
    return list(filas.all())


async def obtener_control(sesion: AsyncSession, control_id: UUID) -> Control:
    control = await sesion.scalar(
        select(Control)
        .where(Control.id == control_id)
        .options(*_REL_CONTROL)
        .execution_options(populate_existing=True)
    )
    if control is None:
        raise ErrorNoEncontrado(f"No existe el control de calidad {control_id}.")
    return control


async def _control_abierto(sesion: AsyncSession, control_id: UUID) -> Control:
    control = await obtener_control(sesion, control_id)
    if control.resultado != ResultadoControl.PENDIENTE.value:
        etiqueta = ResultadoControl(control.resultado).etiqueta.lower()
        raise ErrorConflicto(
            f"El control ya está {etiqueta} y no admite cambios.",
            {"resultado": control.resultado},
        )
    return control


async def iniciar_control(
    sesion: AsyncSession, orden_id: UUID, datos: ControlIniciar, usuario: UsuarioAutenticado
) -> Control:
    orden = await srv_ordenes.obtener(sesion, orden_id)
    if orden.estado in TERMINALES:
        raise ErrorValidacion(
            f"La orden {orden.folio} está {orden.estado.etiqueta.lower()}: ya no se inspecciona."
        )

    abierto = await sesion.scalar(
        select(Control.id).where(
            Control.orden_id == orden_id, Control.resultado == ResultadoControl.PENDIENTE.value
        )
    )
    if abierto is not None:
        # Dos inspecciones a medias sobre la misma orden terminan en dos
        # resultados contradictorios. Se termina la que hay antes de abrir otra.
        raise ErrorConflicto(
            "Ya hay un control de calidad en curso para esta orden.", {"control_id": str(abierto)}
        )

    plantilla = await obtener_plantilla(sesion, datos.plantilla_id)
    if not plantilla.activo:
        raise ErrorValidacion("La plantilla está desactivada.", {"campo": "plantilla_id"})
    if not plantilla.puntos:
        raise ErrorValidacion(
            "La plantilla no tiene puntos que revisar.", {"campo": "plantilla_id"}
        )

    inspector = await _perfil(sesion, datos.inspector_id)
    if datos.inspector_id is not None and inspector is None:
        raise ErrorValidacion(
            "El inspector indicado no pertenece a tu taller.", {"campo": "inspector_id"}
        )
    if inspector is None:
        inspector = await _perfil(sesion, usuario.id)

    control = Control(
        taller_id=usuario.taller_id,
        orden_id=orden_id,
        plantilla_id=plantilla.id,
        inspector_id=inspector,
    )
    for punto in plantilla.puntos:
        control.respuestas.append(
            Respuesta(
                taller_id=usuario.taller_id,
                item_id=punto.id,
                descripcion=punto.descripcion,
                resultado=ResultadoCheck.NO_APLICA,
                orden_visual=punto.orden_visual,
            )
        )

    sesion.add(control)
    await _guardar(sesion)
    return await obtener_control(sesion, control.id)


async def actualizar_control(
    sesion: AsyncSession, control_id: UUID, datos: ControlEditar
) -> Control:
    control = await _control_abierto(sesion, control_id)

    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("inspector_id") is not None and (
        await _perfil(sesion, cambios["inspector_id"]) is None
    ):
        raise ErrorValidacion(
            "El inspector indicado no pertenece a tu taller.", {"campo": "inspector_id"}
        )

    for campo, valor in cambios.items():
        setattr(control, campo, valor)

    await _guardar(sesion)
    return await obtener_control(sesion, control_id)


async def actualizar_respuesta(
    sesion: AsyncSession, respuesta_id: UUID, datos: RespuestaEditar
) -> Control:
    respuesta = await sesion.get(Respuesta, respuesta_id)
    if respuesta is None:
        raise ErrorNoEncontrado(f"No existe el punto revisado {respuesta_id}.")

    await _control_abierto(sesion, respuesta.control_id)

    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(respuesta, campo, valor)

    await _guardar(sesion)
    return await obtener_control(sesion, respuesta.control_id)


async def cerrar_control(
    sesion: AsyncSession, control_id: UUID, datos: CerrarControl, usuario: UsuarioAutenticado
) -> Control:
    """Aprueba o rechaza la inspección y mueve la orden en consecuencia."""
    control = await _control_abierto(sesion, control_id)

    if datos.observaciones is not None:
        control.observaciones = datos.observaciones

    if datos.aprobado:
        faltan = pendientes(control)
        if faltan:
            # El trigger lo rechazaría igual; aquí se dice qué falta, que es lo
            # que la persona necesita para poder corregirlo.
            raise ErrorValidacion(
                f"No se puede aprobar: {len(faltan)} "
                f"{'punto obligatorio' if len(faltan) == 1 else 'puntos obligatorios'} "
                "sin conformidad.",
                {"pendientes": [r.descripcion for r in faltan]},
            )
        control.resultado = ResultadoControl.APROBADO.value
    else:
        if not control.observaciones:
            # Devolver un vehículo a reparación sin decir por qué obliga al
            # técnico a adivinar qué tiene que corregir.
            raise ErrorValidacion(
                "Rechazar el control exige anotar qué hay que corregir en las observaciones.",
                {"campo": "observaciones"},
            )
        control.resultado = ResultadoControl.RECHAZADO.value

    await _guardar(sesion)
    await _mover_orden(sesion, control, datos.aprobado, usuario)
    return await obtener_control(sesion, control_id)


async def _mover_orden(
    sesion: AsyncSession, control: Control, aprobado: bool, usuario: UsuarioAutenticado
) -> None:
    """Lleva la orden al estado que corresponde al resultado de la inspección.

    Solo si la orden está en `control_calidad`. Si alguien llenó el checklist
    antes de pasarla a ese estado, no se fuerza nada: la mueve quien corresponda.
    Se usa el servicio de órdenes para que la transición pase por la misma
    validación y deje su rastro en la bitácora con el motivo.
    """
    orden = await srv_ordenes.obtener(sesion, control.orden_id)
    if orden.estado is not EstadoOrden.CONTROL_CALIDAD:
        return

    if aprobado:
        cambio = CambioEstado(
            estado=EstadoOrden.LISTO_PARA_ENTREGA, comentario="Control de calidad aprobado"
        )
    else:
        cambio = CambioEstado(
            estado=EstadoOrden.EN_REPARACION,
            comentario=f"Control de calidad rechazado: {control.observaciones}",
        )
    await srv_ordenes.cambiar_estado(sesion, orden.id, cambio, usuario)


# -----------------------------------------------------------------------------


async def _guardar(sesion: AsyncSession, *, nombre: str | None = None) -> None:
    try:
        await sesion.flush()
    except (IntegrityError, DBAPIError) as exc:
        codigo = extraer_sqlstate(exc)
        if codigo == "23514":
            # Texto ya redactado por mch_controles_calidad_cierre.
            raise ErrorValidacion(str(exc).strip().splitlines()[0]) from exc
        if codigo == "23505":
            raise ErrorConflicto(
                f"Ya hay una plantilla llamada {nombre!r}." if nombre else "Registro duplicado.",
                {"campo": "nombre"} if nombre else {},
            ) from exc
        if codigo == "23503":
            raise ErrorValidacion("Alguna de las referencias no existe en tu taller.") from exc
        raise
