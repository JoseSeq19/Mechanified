"""Alta y consulta de la cola de avisos al cliente.

Tres decisiones sostienen este módulo:

  1. **Encolar ocurre dentro de la transacción que provoca el aviso.** Si la
     orden no llega a moverse, el correo tampoco se encola; y al revés, no hay
     forma de que el cliente reciba "tu vehículo está listo" por un cambio que
     después se deshizo.

  2. **La fila no lleva texto, lleva referencias.** `datos` solo dice qué
     presupuesto o qué encuesta. El mensaje se redacta al enviarlo, leyendo la
     base. Eso es lo que permite que la política RLS deje encolar a todo el
     taller sin que nadie pueda dictar el contenido de un correo que sale con el
     remitente del producto.

  3. **El destinatario no se elige, se deduce.** Siempre es el correo del cliente
     de esa orden. La política de Postgres comprueba exactamente eso mismo, así
     que saltarse esta capa no sirve de nada.
"""

import json
import logging
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ErrorConflicto, ErrorNoEncontrado, ErrorValidacion
from app.modules.clientes.models import Cliente
from app.modules.encuestas.models import Encuesta
from app.modules.notificaciones.models import EstadoNotificacion, Notificacion, PlantillaCorreo
from app.modules.notificaciones.plantillas import Contexto, Correo, renderizar
from app.modules.ordenes.models import OrdenServicio
from app.modules.presupuestos.models import Presupuesto
from app.modules.talleres.models import Taller
from app.modules.vehiculos.models import Vehiculo
from app.shared.enlaces import enlace_encuesta, enlace_presupuesto

_log = logging.getLogger(__name__)


def descripcion_vehiculo(v: Vehiculo) -> str:
    return " ".join(filter(None, [v.marca, v.modelo, str(v.anio or "")]))


async def encolar(
    sesion: AsyncSession,
    orden: OrdenServicio,
    plantilla: PlantillaCorreo,
    datos: dict[str, Any] | None = None,
) -> str | None:
    """Deja el aviso en la cola. Devuelve el destinatario, o None si no hay.

    Que un cliente no tenga correo registrado no es un error: mucha gente deja
    el vehículo dejando solo un teléfono. En ese caso no se encola nada y quien
    llamó decide qué hacer —normalmente, copiar el enlace y mandarlo por otra
    vía—. Lanzar aquí impediría enviar un presupuesto por no tener un dato que
    nunca fue obligatorio.
    """
    correo = await sesion.scalar(select(Cliente.email).where(Cliente.id == orden.cliente_id))
    if not correo or not correo.strip():
        return None
    correo = correo.strip()

    if await _hay_pendiente(sesion, orden.id, plantilla):
        # Reenviar dos veces seguidas no manda dos correos: el que sigue en cola
        # todavía no ha salido, y saldrá con los datos frescos igualmente.
        _log.info("Aviso %s ya en cola para la orden %s", plantilla.value, orden.folio)
        return correo

    # SQL a mano, y sin RETURNING, a propósito: con RETURNING Postgres exige que
    # la fila nueva pase también la política de SELECT, y esa deja leer la cola
    # solo a administración y asesoría. Un técnico que aprueba el control de
    # calidad vería rechazado su propio INSERT por no poder releerlo.
    await sesion.execute(
        text("""
            insert into public.notificaciones
                   (id, taller_id, orden_id, destinatario, plantilla, datos)
            values (:id, :taller_id, :orden_id, :destinatario, :plantilla, cast(:datos as jsonb))
        """),
        {
            "id": uuid4(),
            "taller_id": orden.taller_id,
            "orden_id": orden.id,
            "destinatario": correo,
            "plantilla": plantilla.value,
            "datos": json.dumps(datos or {}),
        },
    )
    return correo


async def _hay_pendiente(sesion: AsyncSession, orden_id: UUID, plantilla: PlantillaCorreo) -> bool:
    """Si ya hay uno esperando salir para esa orden y ese motivo.

    Para quien no puede leer la cola —un técnico— esto siempre responde que no,
    y encolará igual. Es aceptable: los avisos que dispara un técnico salen de
    una transición de estado que solo ocurre una vez.
    """
    return (
        await sesion.scalar(
            select(Notificacion.id)
            .where(
                Notificacion.orden_id == orden_id,
                Notificacion.plantilla == plantilla.value,
                Notificacion.estado == EstadoNotificacion.PENDIENTE,
            )
            .limit(1)
        )
    ) is not None


async def listar_de_orden(sesion: AsyncSession, orden_id: UUID) -> list[Notificacion]:
    filas = await sesion.scalars(
        select(Notificacion)
        .where(Notificacion.orden_id == orden_id)
        .order_by(Notificacion.creado_en.desc())
    )
    return list(filas.all())


async def obtener(sesion: AsyncSession, notificacion_id: UUID) -> Notificacion:
    n = await sesion.scalar(
        select(Notificacion)
        .where(Notificacion.id == notificacion_id)
        .execution_options(populate_existing=True)
    )
    if n is None:
        raise ErrorNoEncontrado(f"No existe el aviso {notificacion_id}.")
    return n


async def reintentar(sesion: AsyncSession, notificacion_id: UUID) -> str:
    """Vuelve a encolar un aviso que falló.

    No se reabre la fila vieja: el avance de la cola es del worker, y la política
    de RLS no deja que una sesión de usuario le cambie el estado a una
    notificación. Se encola una nueva, que además recalcula el destinatario con
    el correo que el cliente tenga ahora, que suele ser justo lo que había que
    corregir.
    """
    n = await obtener(sesion, notificacion_id)
    if n.estado is not EstadoNotificacion.FALLIDA:
        raise ErrorConflicto(
            f"Este aviso está {n.estado.etiqueta.lower()}: no hay nada que reintentar.",
            {"estado": n.estado.value},
        )

    orden = await sesion.get(OrdenServicio, n.orden_id) if n.orden_id else None
    if orden is None:
        raise ErrorNoEncontrado("La orden de este aviso ya no existe.")

    destinatario = await encolar(sesion, orden, PlantillaCorreo(n.plantilla), dict(n.datos))
    if destinatario is None:
        raise ErrorValidacion(
            "El cliente no tiene correo registrado. Añádeselo en su ficha y vuelve a intentarlo.",
            {"campo": "email"},
        )
    return destinatario


# -----------------------------------------------------------------------------
# Redacción
# -----------------------------------------------------------------------------


async def construir_contexto(sesion: AsyncSession, n: Notificacion) -> Contexto:
    """Reúne lo que necesita la plantilla, leyendo la base.

    Lanza `ValueError` si algo que el aviso referencia ya no existe o no es del
    mismo taller. El worker lo trata como fallo definitivo: no es un problema de
    red que se arregle reintentando.

    Las comprobaciones de taller son redundantes cuando esto corre con la sesión
    del usuario (RLS ya filtró), pero no lo son en el worker, que corre con el
    rol de servicio y ve todos los talleres. Se hacen siempre, en un solo sitio.
    """
    plantilla = PlantillaCorreo(n.plantilla)

    orden = await sesion.get(OrdenServicio, n.orden_id) if n.orden_id else None
    if orden is None or orden.taller_id != n.taller_id:
        raise ValueError("La orden del aviso ya no existe.")

    cliente = await sesion.get(Cliente, orden.cliente_id)
    vehiculo = await sesion.get(Vehiculo, orden.vehiculo_id)
    taller = await sesion.get(Taller, n.taller_id)
    if cliente is None or vehiculo is None or taller is None:
        raise ValueError("Faltan datos del taller, el cliente o el vehículo.")

    base = Contexto(
        taller_nombre=taller.nombre,
        taller_telefono=taller.telefono,
        taller_email=taller.email,
        taller_direccion=taller.direccion,
        moneda=taller.moneda,
        cliente_nombre=cliente.nombre,
        folio=orden.folio,
        vehiculo=descripcion_vehiculo(vehiculo),
        placa=vehiculo.placa,
    )

    if plantilla is PlantillaCorreo.PRESUPUESTO_ENVIADO:
        p = await _referencia(sesion, n, Presupuesto, "presupuesto_id", orden.id)
        return replace(
            base,
            enlace=enlace_presupuesto(p.token_publico),
            total=p.total,
            version=p.version,
            valido_hasta=p.valido_hasta,
        )

    if plantilla is PlantillaCorreo.ENCUESTA_SATISFACCION:
        e = await _referencia(sesion, n, Encuesta, "encuesta_id", orden.id)
        return replace(base, enlace=enlace_encuesta(e.token_publico))

    return base


async def _referencia[T: (Presupuesto, Encuesta)](
    sesion: AsyncSession, n: Notificacion, modelo: type[T], clave: str, orden_id: UUID
) -> T:
    """Resuelve el documento al que apunta el aviso, comprobando que es suyo."""
    crudo = n.datos.get(clave)
    if not crudo:
        raise ValueError(f"El aviso no dice a qué {clave.removesuffix('_id')} se refiere.")

    fila = await sesion.get(modelo, UUID(str(crudo)))
    if fila is None or fila.orden_id != orden_id or fila.taller_id != n.taller_id:
        raise ValueError(f"El {clave.removesuffix('_id')} del aviso ya no existe.")
    return fila


async def redactar(sesion: AsyncSession, n: Notificacion) -> Correo:
    """Contexto + plantilla. Lo usan el worker y la vista previa de la ficha."""
    return renderizar(PlantillaCorreo(n.plantilla), await construir_contexto(sesion, n))


async def vista_previa(sesion: AsyncSession, notificacion_id: UUID) -> tuple[Notificacion, Correo]:
    """El correo tal cual, para poder mirarlo desde la ficha de la orden."""
    n = await obtener(sesion, notificacion_id)
    try:
        return n, await redactar(sesion, n)
    except ValueError as exc:
        raise ErrorValidacion(f"No se puede redactar este aviso: {exc}") from exc
