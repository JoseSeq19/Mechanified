"""Validación y normalización de los esquemas de configuración del taller.

Lo que se comprueba aquí es que el esquema rechaza antes lo que los `check` de
la migración 000200 rechazarían después: la base diría "violates check
constraint talleres_prefijo_formato" y eso no es un mensaje que se le pueda
mostrar a nadie.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.talleres.schemas import TallerEditar


def test_patch_vacio_no_toca_nada() -> None:
    """Es lo que distingue "no vino el campo" de "vino en null"."""
    assert TallerEditar().model_dump(exclude_unset=True) == {}


def test_campo_de_contacto_vacio_se_guarda_como_nulo() -> None:
    """El formulario manda "" al vaciar un campo, y la intención es borrarlo.

    Guardar la cadena vacía dejaría un hueco impreso en el presupuesto que ve
    el cliente, con un teléfono de cero caracteres donde debería no haber nada.
    """
    datos = TallerEditar(telefono="   ", direccion="")

    assert datos.telefono is None
    assert datos.direccion is None
    # Vinieron, aunque en null: el PATCH tiene que borrarlos.
    assert set(datos.model_dump(exclude_unset=True)) == {"telefono", "direccion"}


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [("usd", "USD"), (" ves ", "VES"), ("Eur", "EUR")],
)
def test_moneda_se_normaliza(entrada: str, esperado: str) -> None:
    assert TallerEditar(moneda=entrada).moneda == esperado


@pytest.mark.parametrize("moneda", ["US", "DOLAR", "US$", ""])
def test_moneda_que_no_es_iso_se_rechaza(moneda: str) -> None:
    with pytest.raises(ValidationError):
        TallerEditar(moneda=moneda)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [("dlt", "DLT"), (" mch ", "MCH"), ("a1", "A1")],
)
def test_prefijo_se_normaliza(entrada: str, esperado: str) -> None:
    assert TallerEditar(prefijo_orden=entrada).prefijo_orden == esperado


@pytest.mark.parametrize("prefijo", ["A", "DEMASIADO", "DL-T", "DL T"])
def test_prefijo_con_formato_invalido_se_rechaza(prefijo: str) -> None:
    """El folio se compone con este prefijo; un espacio o un guion lo ensucia."""
    with pytest.raises(ValidationError):
        TallerEditar(prefijo_orden=prefijo)


@pytest.mark.parametrize("impuesto", [Decimal("-1"), Decimal("100.01")])
def test_impuesto_fuera_de_rango_se_rechaza(impuesto: Decimal) -> None:
    with pytest.raises(ValidationError):
        TallerEditar(impuesto_pct=impuesto)


def test_impuesto_exento_se_acepta() -> None:
    """Un taller sin impuesto es un caso legítimo, no un campo sin llenar."""
    assert TallerEditar(impuesto_pct=Decimal("0")).impuesto_pct == Decimal("0")


def test_tarifa_negativa_se_rechaza() -> None:
    with pytest.raises(ValidationError):
        TallerEditar(tarifa_hora_default=Decimal("-0.01"))


@pytest.mark.parametrize("dias", [0, -3, 366])
def test_validez_fuera_de_rango_se_rechaza(dias: int) -> None:
    with pytest.raises(ValidationError):
        TallerEditar(dias_validez_presupuesto=dias)


def test_nombre_se_recorta() -> None:
    assert TallerEditar(nombre="  Delta Motors  ").nombre == "Delta Motors"


@pytest.mark.parametrize("nombre", ["A", " ", "x" * 121])
def test_nombre_invalido_se_rechaza(nombre: str) -> None:
    with pytest.raises(ValidationError):
        TallerEditar(nombre=nombre)


def test_correo_invalido_se_rechaza() -> None:
    with pytest.raises(ValidationError):
        TallerEditar(email="no-es-un-correo")


def test_campos_que_no_se_editan_se_ignoran() -> None:
    """`slug`, `zona_horaria` y `logo_url` no son editables; ver el docstring
    del módulo de esquemas. Pydantic los descarta en vez de escribirlos."""
    datos = TallerEditar.model_validate(
        {"nombre": "Delta Motors", "slug": "otro-slug", "zona_horaria": "UTC"}
    )

    assert datos.model_dump(exclude_unset=True) == {"nombre": "Delta Motors"}
