"""Máquina de estados de la orden de servicio.

Estas pruebas cubren dos cosas distintas:

1. Que el flujo es el que se diseñó (transiciones válidas, quién puede hacer qué).
2. Que la tabla de transiciones y la de roles **no se han separado entre sí**.

Lo segundo importa porque este módulo es una copia de lo que aplica Postgres.
Aquí se comprueba la coherencia interna; que la copia siga coincidiendo con la
base lo verifican las pruebas de integración, que recorren el flujo real.
"""

from itertools import pairwise

import pytest

from app.core.exceptions import ErrorPermiso, ErrorValidacion
from app.core.roles import Rol
from app.modules.ordenes.estados import (
    ORDEN_TABLERO,
    TERMINALES,
    TRANSICIONES,
    EstadoOrden,
    es_valida,
    roles_permitidos,
    siguientes,
    validar,
)

E = EstadoOrden


# -----------------------------------------------------------------------------
# Coherencia de las tablas
# -----------------------------------------------------------------------------


def test_todos_los_estados_tienen_transiciones_declaradas() -> None:
    assert set(TRANSICIONES) == set(EstadoOrden)


def test_el_tablero_incluye_todos_los_estados() -> None:
    assert set(ORDEN_TABLERO) == set(EstadoOrden)
    assert len(ORDEN_TABLERO) == len(EstadoOrden), "no debe haber estados repetidos"


def test_los_terminales_no_llevan_a_ningun_sitio() -> None:
    for estado in TERMINALES:
        assert TRANSICIONES[estado] == frozenset()


def test_toda_transicion_valida_tiene_algun_rol_autorizado() -> None:
    """Detecta el olvido de añadir el rol al sumar una transición nueva.

    Sin esta prueba, una transición sin roles quedaría permitida solo para
    administración y nadie se daría cuenta hasta que un técnico se quejara.
    """
    huerfanas = [
        (a.value, b.value)
        for a, destinos in TRANSICIONES.items()
        for b in destinos
        if roles_permitidos(a, b) == frozenset({Rol.ADMIN_TALLER})
    ]
    assert huerfanas == []


def test_el_administrador_puede_cualquier_transicion_valida() -> None:
    for a, destinos in TRANSICIONES.items():
        for b in destinos:
            assert Rol.ADMIN_TALLER in roles_permitidos(a, b)


def test_encargado_de_repuestos_no_mueve_ordenes() -> None:
    """No es su función: pide y recibe piezas, no decide el avance del taller."""
    for a, destinos in TRANSICIONES.items():
        for b in destinos:
            assert Rol.ENCARGADO_REPUESTOS not in roles_permitidos(a, b)


# -----------------------------------------------------------------------------
# El flujo
# -----------------------------------------------------------------------------


def test_el_camino_feliz_completo_es_valido() -> None:
    camino = [
        E.RECIBIDO,
        E.EN_DIAGNOSTICO,
        E.PRESUPUESTO_PENDIENTE,
        E.APROBADO,
        E.EN_REPARACION,
        E.CONTROL_CALIDAD,
        E.LISTO_PARA_ENTREGA,
        E.ENTREGADO,
    ]
    for actual, siguiente in pairwise(camino):
        assert es_valida(actual, siguiente), f"{actual} -> {siguiente} debería valer"


@pytest.mark.parametrize(
    ("desde", "hasta"),
    [
        (E.RECIBIDO, E.ENTREGADO),
        (E.RECIBIDO, E.EN_REPARACION),
        (E.EN_DIAGNOSTICO, E.APROBADO),
        (E.ENTREGADO, E.EN_REPARACION),
        (E.CANCELADO, E.RECIBIDO),
        (E.LISTO_PARA_ENTREGA, E.CANCELADO),
    ],
)
def test_saltos_invalidos(desde: EstadoOrden, hasta: EstadoOrden) -> None:
    assert not es_valida(desde, hasta)


def test_se_puede_volver_a_presupuesto_desde_reparacion() -> None:
    """Trabajo adicional descubierto con el vehículo abierto.

    No se amplía el monto ya aprobado: se emite una versión nueva del
    presupuesto, y para eso la orden tiene que retroceder.
    """
    assert es_valida(E.EN_REPARACION, E.PRESUPUESTO_PENDIENTE)


def test_calidad_puede_devolver_a_reparacion() -> None:
    assert es_valida(E.CONTROL_CALIDAD, E.EN_REPARACION)


def test_una_orden_en_reparacion_ya_no_se_cancela() -> None:
    """Hay trabajo hecho y piezas puestas: se termina o se devuelve a calidad."""
    assert not es_valida(E.EN_REPARACION, E.CANCELADO)


# -----------------------------------------------------------------------------
# Autorización por rol
# -----------------------------------------------------------------------------


def test_solo_el_tecnico_cierra_el_diagnostico() -> None:
    permitidos = roles_permitidos(E.EN_DIAGNOSTICO, E.PRESUPUESTO_PENDIENTE)
    assert Rol.TECNICO in permitidos
    assert Rol.ASESOR_SERVICIO not in permitidos


def test_solo_asesoria_entrega_el_vehiculo() -> None:
    permitidos = roles_permitidos(E.LISTO_PARA_ENTREGA, E.ENTREGADO)
    assert permitidos == frozenset({Rol.ASESOR_SERVICIO, Rol.ADMIN_TALLER})


def test_el_tecnico_no_cancela_ordenes() -> None:
    assert Rol.TECNICO not in roles_permitidos(E.RECIBIDO, E.CANCELADO)


# -----------------------------------------------------------------------------
# siguientes(): lo que la interfaz usa para dibujar los botones
# -----------------------------------------------------------------------------


def test_siguientes_depende_del_rol() -> None:
    assert siguientes(E.RECIBIDO, Rol.ASESOR_SERVICIO) == [E.EN_DIAGNOSTICO, E.CANCELADO]
    assert siguientes(E.RECIBIDO, Rol.TECNICO) == []


def test_siguientes_esta_vacio_en_los_terminales() -> None:
    for rol in Rol:
        assert siguientes(E.ENTREGADO, rol) == []
        assert siguientes(E.CANCELADO, rol) == []


def test_siguientes_respeta_el_orden_del_tablero() -> None:
    """Para que los botones salgan siempre en el mismo sitio."""
    opciones = siguientes(E.PRESUPUESTO_PENDIENTE, Rol.ADMIN_TALLER)
    assert opciones == [E.EN_DIAGNOSTICO, E.APROBADO, E.CANCELADO]


# -----------------------------------------------------------------------------
# validar(): los mensajes que ve la persona
# -----------------------------------------------------------------------------


def test_validar_acepta_una_transicion_correcta() -> None:
    validar(E.RECIBIDO, E.EN_DIAGNOSTICO, Rol.ASESOR_SERVICIO)


def test_validar_rechaza_el_mismo_estado() -> None:
    with pytest.raises(ErrorValidacion, match="ya está"):
        validar(E.RECIBIDO, E.RECIBIDO, Rol.ADMIN_TALLER)


def test_validar_rechaza_desde_un_terminal() -> None:
    with pytest.raises(ErrorValidacion, match="ya no admite"):
        validar(E.ENTREGADO, E.EN_REPARACION, Rol.ADMIN_TALLER)


def test_validar_enumera_las_salidas_posibles() -> None:
    with pytest.raises(ErrorValidacion) as excinfo:
        validar(E.RECIBIDO, E.ENTREGADO, Rol.ADMIN_TALLER)

    assert "en diagnóstico" in str(excinfo.value)


def test_validar_distingue_falta_de_permiso_de_transicion_invalida() -> None:
    """Un 403 y un 422 no significan lo mismo para quien está delante."""
    with pytest.raises(ErrorPermiso) as excinfo:
        validar(E.EN_DIAGNOSTICO, E.PRESUPUESTO_PENDIENTE, Rol.ASESOR_SERVICIO)

    assert "técnico" in str(excinfo.value)
