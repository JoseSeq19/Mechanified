"""Esquemas del panel del taller.

Este módulo no tiene `models.py` y es la única excepción del proyecto: no posee
ninguna tabla. Lee lo que ya escribieron los demás —órdenes, su bitácora,
presupuestos, controles de calidad, encuestas— y lo resume. Inventarle un modelo
sería inventarle un dueño a datos que no son suyos.

Todo lo que sale de aquí viaja en una sola respuesta. Un panel que pide siete
endpoints se pinta a trozos y se queda a medias en cuanto uno falla.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.modules.encuestas.schemas import ResumenEncuestas


class ConteoEstado(BaseModel):
    estado: str
    etiqueta: str
    cantidad: int


class TrabajoVivo(BaseModel):
    """La foto de ahora mismo: qué hay en el taller sin terminar."""

    abiertas: int
    #: Con fecha prometida ya pasada y todavía sin entregar.
    atrasadas: int
    por_estado: list[ConteoEstado]
    repuestos_bajo_minimo: int


class Produccion(BaseModel):
    """Lo que pasó por el taller durante el periodo."""

    recibidas: int
    entregadas: int
    canceladas: int
    facturado: Decimal
    #: None cuando no se entregó nada: dividir entre cero daría un cero que se
    #: leería como "el ticket medio se hundió".
    ticket_promedio: Decimal | None
    mano_obra: Decimal
    repuestos: Decimal
    #: Del ingreso a la entrega. La mediana acompaña al promedio porque una
    #: sola orden atascada dos meses desplaza el promedio y no dice nada del día
    #: a día.
    horas_ciclo_promedio: float | None
    horas_ciclo_mediana: float | None


class EtapaTiempo(BaseModel):
    """Cuánto se queda una orden en cada estado antes de pasar al siguiente."""

    estado: str
    etiqueta: str
    horas_promedio: float
    #: Cuántas transiciones sostienen ese promedio. Con dos o tres, no dice nada.
    transiciones: int


class Presupuestos(BaseModel):
    emitidos: int
    aprobados: int
    rechazados: int
    #: Aprobados sobre los que tuvieron respuesta. None si nadie respondió.
    tasa_aprobacion: float | None
    #: Lo que tarda el cliente en contestar desde que se le envía.
    horas_respuesta_promedio: float | None


class Calidad(BaseModel):
    controles: int
    aprobados: int
    rechazados: int
    #: Porcentaje de inspecciones que mandaron el vehículo de vuelta al taller.
    #: Es la medida de retrabajo.
    tasa_rechazo: float | None


class TecnicoProductivo(BaseModel):
    tecnico_id: str
    nombre: str
    entregadas: int
    facturado: Decimal


class PanelMetricas(BaseModel):
    """Todo el panel, en una respuesta."""

    dias: int
    desde: datetime
    trabajo_vivo: TrabajoVivo
    produccion: Produccion
    etapas: list[EtapaTiempo]
    presupuestos: Presupuestos
    calidad: Calidad
    satisfaccion: ResumenEncuestas
    tecnicos: list[TecnicoProductivo]
