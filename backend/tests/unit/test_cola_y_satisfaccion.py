"""Dos cuentas que se pueden equivocar en silencio.

Ni el NPS ni la espera entre reintentos fallan de forma ruidosa: un signo
cambiado sigue devolviendo un número creíble, y un reintento mal espaciado solo
se nota cuando un proveedor de correo empieza a bloquear al remitente. Por eso
las dos viven en funciones puras y se prueban aquí.
"""

from datetime import timedelta

import pytest

from app.modules.encuestas.service import calcular_nps
from app.modules.notificaciones.worker import MAX_INTENTOS, espera_tras_intento

# -----------------------------------------------------------------------------
# NPS
# -----------------------------------------------------------------------------


def test_sin_respuestas_no_hay_indicador() -> None:
    """Cero no es "malo": es que todavía nadie ha contestado."""
    assert calcular_nps(promotores=0, detractores=0, respuestas=0) is None


def test_todos_promotores_da_cien() -> None:
    assert calcular_nps(promotores=8, detractores=0, respuestas=8) == 100


def test_todos_detractores_da_menos_cien() -> None:
    assert calcular_nps(promotores=0, detractores=5, respuestas=5) == -100


def test_los_pasivos_cuentan_en_el_total_pero_no_suman() -> None:
    """Es lo que distingue el NPS de una media: un montón de tibios lo baja.

    Cuatro promotores y seis pasivos no son un 100, son un 40.
    """
    assert calcular_nps(promotores=4, detractores=0, respuestas=10) == 40


def test_mitad_y_mitad_da_cero() -> None:
    assert calcular_nps(promotores=5, detractores=5, respuestas=10) == 0


# -----------------------------------------------------------------------------
# Reintentos
# -----------------------------------------------------------------------------


def test_la_espera_crece_con_cada_intento() -> None:
    esperas = [espera_tras_intento(i) for i in range(1, MAX_INTENTOS + 1)]

    assert esperas == sorted(esperas)
    assert esperas[0] < esperas[-1]


def test_el_primer_reintento_es_pronto() -> None:
    """Casi siempre es un corte de red de segundos: esperar una hora sería absurdo."""
    assert espera_tras_intento(1) <= timedelta(minutes=1)


def test_la_espera_tiene_techo() -> None:
    """Sin tope, un intento tardío quedaría programado para dentro de días."""
    assert espera_tras_intento(99) == espera_tras_intento(MAX_INTENTOS)
    assert espera_tras_intento(99) <= timedelta(hours=1)


@pytest.mark.parametrize("intento", [0, -3])
def test_un_intento_absurdo_no_revienta(intento: int) -> None:
    """La cola no puede caerse por un valor raro en una columna."""
    assert espera_tras_intento(intento) == espera_tras_intento(1)
