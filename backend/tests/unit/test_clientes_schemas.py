"""Validación y normalización de los esquemas de cliente.

Pruebas puras: no tocan la base de datos.
"""

import pytest
from pydantic import ValidationError

from app.modules.clientes.models import TipoCliente
from app.modules.clientes.schemas import ClienteCrear, ClienteEditar


def test_nombre_es_obligatorio() -> None:
    with pytest.raises(ValidationError):
        ClienteCrear()  # type: ignore[call-arg]


def test_nombre_muy_corto_se_rechaza() -> None:
    with pytest.raises(ValidationError):
        ClienteCrear(nombre="A")


def test_nombre_se_recorta() -> None:
    assert ClienteCrear(nombre="  Andrés Villamizar  ").nombre == "Andrés Villamizar"


def test_tipo_por_omision_es_persona() -> None:
    assert ClienteCrear(nombre="Taller Sur").tipo is TipoCliente.PERSONA


def test_tipo_acepta_el_valor_del_enum_de_postgres() -> None:
    assert ClienteCrear(nombre="Distribuidora X", tipo="empresa").tipo is TipoCliente.EMPRESA


def test_tipo_invalido_se_rechaza() -> None:
    with pytest.raises(ValidationError):
        ClienteCrear(nombre="X Y", tipo="cooperativa")


@pytest.mark.parametrize("vacio", ["", "   "])
def test_opcionales_vacios_pasan_a_nulo(vacio: str) -> None:
    """Un formulario web manda "" cuando el usuario no llena el campo.

    Si eso llegara como cadena vacía a la base, el índice único parcial de
    `documento` —que solo ignora NULL— haría chocar entre sí a dos clientes sin
    documento.
    """
    cliente = ClienteCrear(nombre="Neida Colmenares", documento=vacio, telefono=vacio, notas=vacio)

    assert cliente.documento is None
    assert cliente.telefono is None
    assert cliente.notas is None


def test_email_vacio_pasa_a_nulo_sin_fallar_validacion() -> None:
    assert ClienteCrear(nombre="Luis Betancourt", email="   ").email is None


def test_email_invalido_se_rechaza() -> None:
    with pytest.raises(ValidationError):
        ClienteCrear(nombre="Luis Betancourt", email="esto-no-es-un-correo")


def test_no_se_puede_inyectar_taller_id() -> None:
    """El taller sale del token, nunca del cuerpo de la petición."""
    cliente = ClienteCrear(nombre="Intento", taller_id="00000000-0000-4000-8000-000000000001")

    assert not hasattr(cliente, "taller_id")


def test_patch_distingue_ausente_de_nulo() -> None:
    """Es lo que permite borrar un campo a propósito sin arrasar el resto."""
    solo_telefono = ClienteEditar(telefono="+58 414 000 0000")
    assert solo_telefono.model_dump(exclude_unset=True) == {"telefono": "+58 414 000 0000"}

    borrar_telefono = ClienteEditar(telefono=None)
    assert borrar_telefono.model_dump(exclude_unset=True) == {"telefono": None}


def test_patch_vacio_no_cambia_nada() -> None:
    assert ClienteEditar().model_dump(exclude_unset=True) == {}
