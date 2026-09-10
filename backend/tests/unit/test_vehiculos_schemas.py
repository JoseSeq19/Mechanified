"""Validación y normalización de los esquemas de vehículo."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.vehiculos.schemas import VehiculoCrear, VehiculoEditar

CLIENTE = uuid4()


def _crear(**extra: object) -> VehiculoCrear:
    base = {"cliente_id": CLIENTE, "placa": "AB123CD", "marca": "Toyota", "modelo": "Corolla"}
    return VehiculoCrear(**{**base, **extra})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("entrada", "esperada"),
    [
        ("ab123cd", "AB123CD"),
        ("  AB123CD  ", "AB123CD"),
        ("AB 123 CD", "AB123CD"),
        ("ab-123-cd", "AB123CD"),
    ],
)
def test_placa_se_normaliza(entrada: str, esperada: str) -> None:
    """El índice único es sobre upper(placa).

    Sin normalizar, "ab123cd" y "AB123CD" se enviarían como filas distintas que
    el índice considera la misma, y la búsqueda dependería de cómo la escribió
    quien la capturó.
    """
    assert _crear(placa=entrada).placa == esperada


def test_vin_se_normaliza() -> None:
    assert _crear(vin=" 9bwzzz377vt004251 ").vin == "9BWZZZ377VT004251"


def test_campos_obligatorios() -> None:
    with pytest.raises(ValidationError):
        VehiculoCrear(placa="AB123CD", marca="Toyota", modelo="Corolla")  # type: ignore[call-arg]


def test_placa_demasiado_corta_se_rechaza() -> None:
    with pytest.raises(ValidationError):
        _crear(placa="AB1")


@pytest.mark.parametrize("anio", [1899, 2101])
def test_anio_fuera_de_rango_se_rechaza(anio: int) -> None:
    with pytest.raises(ValidationError):
        _crear(anio=anio)


def test_anio_valido_se_acepta() -> None:
    assert _crear(anio=2018).anio == 2018


def test_kilometraje_negativo_se_rechaza() -> None:
    with pytest.raises(ValidationError):
        _crear(kilometraje_ultimo=-1)


def test_opcionales_vacios_pasan_a_nulo() -> None:
    v = _crear(color="  ", notas="", transmision="   ")
    assert v.color is None
    assert v.notas is None
    assert v.transmision is None


def test_no_se_puede_inyectar_taller_id() -> None:
    assert not hasattr(_crear(taller_id=uuid4()), "taller_id")


def test_patch_distingue_ausente_de_nulo() -> None:
    solo_km = VehiculoEditar(kilometraje_ultimo=98000)
    assert solo_km.model_dump(exclude_unset=True) == {"kilometraje_ultimo": 98000}

    borrar_vin = VehiculoEditar(vin=None)
    assert borrar_vin.model_dump(exclude_unset=True) == {"vin": None}


def test_patch_tambien_normaliza_la_placa() -> None:
    assert VehiculoEditar(placa="xy456zw").placa == "XY456ZW"
