"""Máquina de estados de la orden de servicio.

Este módulo es **un espejo** de lo que ya aplica Postgres en las funciones
`mch_transicion_valida` y `mch_rol_puede_transicionar` de la migración 000400.

Que esté duplicado es deliberado, y conviene entender por qué:

  - La base es la barrera real. Bloquea un salto inválido aunque alguien escriba
    directo contra Postgres, y no se puede esquivar desde la aplicación.
  - Esta copia existe para dar buenos mensajes *antes* de tocar la base y, sobre
    todo, para poder responder "¿qué puede hacer este usuario ahora?", que es lo
    que la interfaz necesita para dibujar los botones. Preguntárselo a la base
    exigiría intentar cada transición y ver cuál falla.

El riesgo de toda duplicación es que las dos copias se separen. Lo cubre
`tests/unit/test_maquina_estados.py`, que verifica la coherencia interna, y las
pruebas de integración, que ejercitan el flujo completo contra Postgres: si la
base y esta tabla discrepan, fallan.

Sin SQLAlchemy ni FastAPI a propósito: es lógica pura y se prueba como tal.
"""

from enum import StrEnum

from app.core.exceptions import ErrorPermiso, ErrorValidacion
from app.core.roles import Rol


class EstadoOrden(StrEnum):
    """Refleja el enum `public.estado_orden`."""

    RECIBIDO = "recibido"
    EN_DIAGNOSTICO = "en_diagnostico"
    PRESUPUESTO_PENDIENTE = "presupuesto_pendiente"
    APROBADO = "aprobado"
    EN_REPARACION = "en_reparacion"
    CONTROL_CALIDAD = "control_calidad"
    LISTO_PARA_ENTREGA = "listo_para_entrega"
    ENTREGADO = "entregado"
    CANCELADO = "cancelado"

    @property
    def etiqueta(self) -> str:
        return _ETIQUETAS[self]


_ETIQUETAS: dict[EstadoOrden, str] = {
    EstadoOrden.RECIBIDO: "Recibido",
    EstadoOrden.EN_DIAGNOSTICO: "En diagnóstico",
    EstadoOrden.PRESUPUESTO_PENDIENTE: "Presupuesto pendiente",
    EstadoOrden.APROBADO: "Aprobado",
    EstadoOrden.EN_REPARACION: "En reparación",
    EstadoOrden.CONTROL_CALIDAD: "Control de calidad",
    EstadoOrden.LISTO_PARA_ENTREGA: "Listo para entrega",
    EstadoOrden.ENTREGADO: "Entregado",
    EstadoOrden.CANCELADO: "Cancelado",
}

#: Estados en los que la orden ya no se mueve.
TERMINALES: frozenset[EstadoOrden] = frozenset({EstadoOrden.ENTREGADO, EstadoOrden.CANCELADO})

#: Orden de las columnas del tablero. Los terminales van al final.
ORDEN_TABLERO: tuple[EstadoOrden, ...] = (
    EstadoOrden.RECIBIDO,
    EstadoOrden.EN_DIAGNOSTICO,
    EstadoOrden.PRESUPUESTO_PENDIENTE,
    EstadoOrden.APROBADO,
    EstadoOrden.EN_REPARACION,
    EstadoOrden.CONTROL_CALIDAD,
    EstadoOrden.LISTO_PARA_ENTREGA,
    EstadoOrden.ENTREGADO,
    EstadoOrden.CANCELADO,
)

#: Transiciones válidas. Espejo de `mch_transicion_valida`.
TRANSICIONES: dict[EstadoOrden, frozenset[EstadoOrden]] = {
    EstadoOrden.RECIBIDO: frozenset({EstadoOrden.EN_DIAGNOSTICO, EstadoOrden.CANCELADO}),
    EstadoOrden.EN_DIAGNOSTICO: frozenset(
        {EstadoOrden.PRESUPUESTO_PENDIENTE, EstadoOrden.CANCELADO}
    ),
    EstadoOrden.PRESUPUESTO_PENDIENTE: frozenset(
        {EstadoOrden.APROBADO, EstadoOrden.EN_DIAGNOSTICO, EstadoOrden.CANCELADO}
    ),
    EstadoOrden.APROBADO: frozenset({EstadoOrden.EN_REPARACION, EstadoOrden.CANCELADO}),
    # Trabajo adicional descubierto en plena reparación: vuelve a presupuesto y
    # se emite una versión nueva, en vez de ampliar el monto ya aprobado.
    EstadoOrden.EN_REPARACION: frozenset(
        {EstadoOrden.CONTROL_CALIDAD, EstadoOrden.PRESUPUESTO_PENDIENTE}
    ),
    EstadoOrden.CONTROL_CALIDAD: frozenset(
        {EstadoOrden.LISTO_PARA_ENTREGA, EstadoOrden.EN_REPARACION}
    ),
    EstadoOrden.LISTO_PARA_ENTREGA: frozenset({EstadoOrden.ENTREGADO}),
    EstadoOrden.ENTREGADO: frozenset(),
    EstadoOrden.CANCELADO: frozenset(),
}

#: Quién puede hacer cada transición. Espejo de `mch_rol_puede_transicionar`.
#: El administrador puede todas, así que no aparece aquí.
_ROLES: dict[tuple[EstadoOrden, EstadoOrden], frozenset[Rol]] = {
    (EstadoOrden.RECIBIDO, EstadoOrden.EN_DIAGNOSTICO): frozenset({Rol.ASESOR_SERVICIO}),
    (EstadoOrden.EN_DIAGNOSTICO, EstadoOrden.PRESUPUESTO_PENDIENTE): frozenset({Rol.TECNICO}),
    (EstadoOrden.PRESUPUESTO_PENDIENTE, EstadoOrden.APROBADO): frozenset({Rol.ASESOR_SERVICIO}),
    (EstadoOrden.PRESUPUESTO_PENDIENTE, EstadoOrden.EN_DIAGNOSTICO): frozenset(
        {Rol.ASESOR_SERVICIO}
    ),
    (EstadoOrden.APROBADO, EstadoOrden.EN_REPARACION): frozenset(
        {Rol.ASESOR_SERVICIO, Rol.TECNICO}
    ),
    (EstadoOrden.EN_REPARACION, EstadoOrden.CONTROL_CALIDAD): frozenset({Rol.TECNICO}),
    (EstadoOrden.EN_REPARACION, EstadoOrden.PRESUPUESTO_PENDIENTE): frozenset({Rol.TECNICO}),
    (EstadoOrden.CONTROL_CALIDAD, EstadoOrden.LISTO_PARA_ENTREGA): frozenset(
        {Rol.ASESOR_SERVICIO, Rol.TECNICO}
    ),
    (EstadoOrden.CONTROL_CALIDAD, EstadoOrden.EN_REPARACION): frozenset(
        {Rol.ASESOR_SERVICIO, Rol.TECNICO}
    ),
    (EstadoOrden.LISTO_PARA_ENTREGA, EstadoOrden.ENTREGADO): frozenset({Rol.ASESOR_SERVICIO}),
}

#: Cancelar es potestad de asesoría (y administración), venga del estado que venga.
_ROLES_CANCELACION: frozenset[Rol] = frozenset({Rol.ASESOR_SERVICIO})


def roles_permitidos(anterior: EstadoOrden, nuevo: EstadoOrden) -> frozenset[Rol]:
    """Roles que pueden ejecutar esa transición, incluido el administrador."""
    if nuevo is EstadoOrden.CANCELADO:
        base = _ROLES_CANCELACION
    else:
        base = _ROLES.get((anterior, nuevo), frozenset())
    return base | {Rol.ADMIN_TALLER}


def es_valida(anterior: EstadoOrden, nuevo: EstadoOrden) -> bool:
    return nuevo in TRANSICIONES[anterior]


def siguientes(actual: EstadoOrden, rol: Rol) -> list[EstadoOrden]:
    """Transiciones que ese rol puede hacer desde ese estado.

    Es lo que la interfaz usa para dibujar solo los botones que van a funcionar,
    en vez de mostrarlos todos y dejar que la base rechace la mitad.
    """
    return [
        destino
        for destino in ORDEN_TABLERO
        if destino in TRANSICIONES[actual] and rol in roles_permitidos(actual, destino)
    ]


def validar(anterior: EstadoOrden, nuevo: EstadoOrden, rol: Rol) -> None:
    """Comprueba la transición y el permiso. Lanza si algo no cuadra.

    Postgres volverá a comprobar lo mismo; esto solo adelanta el rechazo con un
    mensaje que se puede enseñar a una persona.
    """
    if anterior is nuevo:
        raise ErrorValidacion(f"La orden ya está en {anterior.etiqueta.lower()}.")

    if anterior in TERMINALES:
        raise ErrorValidacion(
            f"La orden está {anterior.etiqueta.lower()} y ya no admite cambios de estado."
        )

    if not es_valida(anterior, nuevo):
        posibles = ", ".join(e.etiqueta.lower() for e in TRANSICIONES[anterior]) or "ninguno"
        raise ErrorValidacion(
            f"No se puede pasar de {anterior.etiqueta.lower()} a {nuevo.etiqueta.lower()}. "
            f"Desde aquí solo cabe: {posibles}.",
            {"estado_actual": anterior.value, "posibles": sorted(TRANSICIONES[anterior])},
        )

    permitidos = roles_permitidos(anterior, nuevo)
    if rol not in permitidos:
        quienes = ", ".join(sorted(r.etiqueta for r in permitidos))
        raise ErrorPermiso(
            f"Pasar la orden a {nuevo.etiqueta.lower()} es cosa de: {quienes}. "
            f"Tu rol es {rol.etiqueta}.",
            {"rol_actual": rol.value, "roles_requeridos": sorted(r.value for r in permitidos)},
        )
