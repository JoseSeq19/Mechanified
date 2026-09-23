"""La contraseña temporal que se le entrega a alguien al darlo de alta.

Se usa una vez, casi siempre dictada o copiada a mano de una pantalla a un
mensaje. De ahí las dos exigencias que se prueban aquí: que no se pueda
confundir al leerla y que no sea adivinable.
"""

import re

from app.modules.usuarios.cuentas import generar_clave

#: Caracteres que se confunden al dictar o al transcribir.
AMBIGUOS = set("O0lI1")


def test_tiene_la_forma_esperada() -> None:
    assert re.fullmatch(r"[a-zA-Z2-9]{4}(-[a-zA-Z2-9]{4}){3}", generar_clave())


def test_no_usa_caracteres_que_se_confunden() -> None:
    """Una clave con O y 0 se transcribe mal y acaba en una llamada al taller."""
    caracteres = set("".join(generar_clave() for _ in range(200)).replace("-", ""))

    assert not (caracteres & AMBIGUOS)


def test_no_se_repite() -> None:
    """No prueba la aleatoriedad, pero sí delata un generador roto o fijo."""
    claves = {generar_clave() for _ in range(500)}

    assert len(claves) == 500


def test_es_bastante_larga() -> None:
    assert len(generar_clave().replace("-", "")) >= 16
