"""Cálculo del panel del taller.

Ninguna consulta filtra por `taller_id`: lo hace RLS, igual que en el resto del
backend. Eso importa más aquí que en ningún otro módulo, porque son consultas de
agregación: un `sum()` sin filtrar sumaría los talleres de todos los clientes y
el error no se vería —saldría un número, solo que mal—.

Los tiempos por etapa salen de `orden_eventos`, la bitácora que escribe el
trigger de la máquina de estados. Por eso esa tabla es de solo lectura y sin
borrado: es la única fuente de cuánto tardó cada paso, y una fila editada a mano
falsearía el histórico sin dejar rastro.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calidad.models import Control, ResultadoControl
from app.modules.encuestas import service as srv_encuestas
from app.modules.metricas.schemas import (
    Calidad,
    ConteoEstado,
    EtapaTiempo,
    PanelMetricas,
    Presupuestos,
    Produccion,
    TecnicoProductivo,
    TrabajoVivo,
)
from app.modules.ordenes.estados import ORDEN_TABLERO, TERMINALES, EstadoOrden
from app.modules.ordenes.models import OrdenServicio
from app.modules.presupuestos.models import EstadoPresupuesto, Presupuesto
from app.modules.repuestos.models import Repuesto
from app.modules.usuarios.models import Perfil

#: Periodos que ofrece la interfaz. Cualquier otro valor se acota a este rango.
DIAS_MINIMO = 7
DIAS_MAXIMO = 365

#: Cuántos técnicos entran en el cuadro de honor. Con más, deja de ser un
#: resumen y se convierte en un listado que nadie lee.
TOPE_TECNICOS = 5


def _horas(intervalo: timedelta | None) -> float | None:
    """Convierte un intervalo de Postgres a horas con un decimal.

    En horas y no en días porque una orden que tarda treinta horas se entiende
    de un vistazo; "1,25 días" hay que traducirlo mentalmente.
    """
    return round(intervalo.total_seconds() / 3600, 1) if intervalo is not None else None


async def panel(sesion: AsyncSession, dias: int) -> PanelMetricas:
    """Arma el panel entero. Una llamada, una pantalla."""
    dias = max(DIAS_MINIMO, min(dias, DIAS_MAXIMO))
    desde = datetime.now(UTC) - timedelta(days=dias)

    return PanelMetricas(
        dias=dias,
        desde=desde,
        trabajo_vivo=await trabajo_vivo(sesion),
        produccion=await produccion(sesion, desde),
        etapas=await tiempos_por_etapa(sesion, desde),
        presupuestos=await presupuestos(sesion, desde),
        calidad=await calidad(sesion, desde),
        satisfaccion=await srv_encuestas.resumen(sesion, desde=desde),
        tecnicos=await tecnicos(sesion, desde),
    )


async def trabajo_vivo(sesion: AsyncSession) -> TrabajoVivo:
    """Lo que hay en el taller ahora. No depende del periodo elegido."""
    abiertas = select(OrdenServicio).where(OrdenServicio.estado.notin_(list(TERMINALES)))

    filas = await sesion.execute(
        select(OrdenServicio.estado, func.count())
        .where(OrdenServicio.estado.notin_(list(TERMINALES)))
        .group_by(OrdenServicio.estado)
    )
    conteo: dict[EstadoOrden, int] = dict.fromkeys(
        [e for e in ORDEN_TABLERO if e not in TERMINALES], 0
    )
    for estado, cantidad in filas.all():
        conteo[estado] = cantidad

    atrasadas = (
        await sesion.scalar(
            select(func.count()).select_from(
                abiertas.where(OrdenServicio.fecha_promesa < func.now()).subquery()
            )
        )
    ) or 0

    bajo_minimo = (
        await sesion.scalar(
            select(func.count())
            .select_from(Repuesto)
            .where(Repuesto.activo.is_(True), Repuesto.stock <= Repuesto.stock_minimo)
        )
    ) or 0

    return TrabajoVivo(
        abiertas=sum(conteo.values()),
        atrasadas=atrasadas,
        por_estado=[
            ConteoEstado(estado=e.value, etiqueta=e.etiqueta, cantidad=c) for e, c in conteo.items()
        ],
        repuestos_bajo_minimo=bajo_minimo,
    )


async def produccion(sesion: AsyncSession, desde: datetime) -> Produccion:
    entregadas_en_periodo = (
        OrdenServicio.estado == EstadoOrden.ENTREGADO,
        OrdenServicio.fecha_entrega >= desde,
    )

    async def _contar(stmt: Select) -> int:
        return (await sesion.scalar(select(func.count()).select_from(stmt.subquery()))) or 0

    recibidas = await _contar(select(OrdenServicio).where(OrdenServicio.fecha_ingreso >= desde))
    canceladas = await _contar(
        select(OrdenServicio).where(
            OrdenServicio.estado == EstadoOrden.CANCELADO,
            OrdenServicio.actualizado_en >= desde,
        )
    )

    # El ciclo se mide del ingreso a la entrega, que es lo que percibe el
    # cliente: el vehículo estuvo fuera de su casa ese tiempo, esté la orden
    # esperando su aprobación o esperando una pieza.
    ciclo = func.age(OrdenServicio.fecha_entrega, OrdenServicio.fecha_ingreso)

    fila = (
        await sesion.execute(
            select(
                func.count(),
                func.coalesce(func.sum(OrdenServicio.total), 0),
                func.coalesce(func.sum(OrdenServicio.total_mano_obra), 0),
                func.coalesce(func.sum(OrdenServicio.total_repuestos), 0),
                func.avg(ciclo),
                func.percentile_cont(0.5).within_group(ciclo),
            ).where(*entregadas_en_periodo)
        )
    ).one()

    entregadas, facturado, mano_obra, repuestos, ciclo_medio, ciclo_mediano = fila

    return Produccion(
        recibidas=recibidas,
        entregadas=entregadas,
        canceladas=canceladas,
        facturado=facturado,
        ticket_promedio=(round(Decimal(facturado) / entregadas, 2) if entregadas else None),
        mano_obra=mano_obra,
        repuestos=repuestos,
        horas_ciclo_promedio=_horas(ciclo_medio),
        horas_ciclo_mediana=_horas(ciclo_mediano),
    )


#: Cuánto dura cada estado, calculado sobre la bitácora.
#:
#: `lead()` toma la marca de tiempo del evento siguiente de la misma orden: la
#: diferencia es lo que la orden pasó en ese estado. Las órdenes que siguen en su
#: estado actual no tienen evento siguiente y quedan fuera, que es lo correcto —
#: todavía no han terminado esa etapa y contarlas la acortaría.
_ETAPAS = text("""
    select estado_nuevo,
           count(*) as transiciones,
           avg(siguiente - creado_en) as duracion
      from (
            select orden_id, estado_nuevo, creado_en,
                   lead(creado_en) over (partition by orden_id order by creado_en, id) as siguiente
              from public.orden_eventos
           ) etapas
     where siguiente is not null
       and creado_en >= :desde
     group by estado_nuevo
""")


async def tiempos_por_etapa(sesion: AsyncSession, desde: datetime) -> list[EtapaTiempo]:
    filas = (await sesion.execute(_ETAPAS, {"desde": desde})).all()
    medido = {f.estado_nuevo: (f.transiciones, f.duracion) for f in filas}

    # Se devuelven en el orden del tablero, no en el que los dé la base: el panel
    # los pinta como un recorrido y desordenados no se leen.
    etapas = []
    for estado in ORDEN_TABLERO:
        if estado in TERMINALES or estado.value not in medido:
            continue
        transiciones, duracion = medido[estado.value]
        horas = _horas(duracion)
        if horas is None:
            continue
        etapas.append(
            EtapaTiempo(
                estado=estado.value,
                etiqueta=estado.etiqueta,
                horas_promedio=horas,
                transiciones=transiciones,
            )
        )
    return etapas


async def presupuestos(sesion: AsyncSession, desde: datetime) -> Presupuestos:
    fila = (
        await sesion.execute(
            select(
                func.count(),
                func.count().filter(Presupuesto.estado == EstadoPresupuesto.APROBADO),
                func.count().filter(Presupuesto.estado == EstadoPresupuesto.RECHAZADO),
                func.avg(func.age(Presupuesto.respondido_en, Presupuesto.enviado_en)),
            ).where(Presupuesto.creado_en >= desde)
        )
    ).one()

    emitidos, aprobados, rechazados, respuesta = fila
    respondidos = aprobados + rechazados

    return Presupuestos(
        emitidos=emitidos,
        aprobados=aprobados,
        rechazados=rechazados,
        tasa_aprobacion=round(aprobados * 100 / respondidos, 1) if respondidos else None,
        horas_respuesta_promedio=_horas(respuesta),
    )


async def calidad(sesion: AsyncSession, desde: datetime) -> Calidad:
    fila = (
        await sesion.execute(
            select(
                func.count(),
                func.count().filter(Control.resultado == ResultadoControl.APROBADO.value),
                func.count().filter(Control.resultado == ResultadoControl.RECHAZADO.value),
            ).where(Control.creado_en >= desde)
        )
    ).one()

    controles, aprobados, rechazados = fila
    cerrados = aprobados + rechazados

    return Calidad(
        controles=controles,
        aprobados=aprobados,
        rechazados=rechazados,
        tasa_rechazo=round(rechazados * 100 / cerrados, 1) if cerrados else None,
    )


async def tecnicos(sesion: AsyncSession, desde: datetime) -> list[TecnicoProductivo]:
    """Quién sacó adelante el trabajo entregado en el periodo.

    Solo cuenta lo entregado, no lo asignado: una orden que lleva tres semanas
    abierta no es producción de nadie todavía.
    """
    filas = (
        await sesion.execute(
            select(
                OrdenServicio.tecnico_id,
                Perfil.nombre_completo,
                func.count(),
                func.coalesce(func.sum(OrdenServicio.total), 0),
            )
            .join(Perfil, Perfil.id == OrdenServicio.tecnico_id)
            .where(
                OrdenServicio.estado == EstadoOrden.ENTREGADO,
                OrdenServicio.fecha_entrega >= desde,
            )
            .group_by(OrdenServicio.tecnico_id, Perfil.nombre_completo)
            .order_by(func.count().desc())
            .limit(TOPE_TECNICOS)
        )
    ).all()

    return [
        TecnicoProductivo(
            tecnico_id=str(tecnico_id),
            nombre=nombre,
            entregadas=entregadas,
            facturado=facturado,
        )
        for tecnico_id, nombre, entregadas, facturado in filas
    ]
