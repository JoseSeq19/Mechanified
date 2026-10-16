"""Normalización del inventario de ingreso.

`inventario_ingreso` es la única columna `jsonb` que escribe un formulario, y lo
que se guarde ahí acaba impreso en la orden que el cliente firma. El esquema la
declara libre a propósito —cada taller inventaría cosas distintas— así que estas
pruebas son las que fijan qué quiere decir "libre": pares de texto, acotados, sin
estructuras anidadas que ninguna pantalla sabría mostrar.
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.ordenes.schemas import (
    LARGO_CLAVE_INVENTARIO,
    LARGO_VALOR_INVENTARIO,
    MAXIMO_ENTRADAS_INVENTARIO,
    OrdenCrear,
    OrdenEditar,
)

CLIENTE = uuid4()
VEHICULO = uuid4()


def _crear(**extra: object) -> OrdenCrear:
    base = {
        "cliente_id": CLIENTE,
        "vehiculo_id": VEHICULO,
        "motivo_ingreso": "Chillido al frenar en bajada",
    }
    return OrdenCrear(**{**base, **extra})


def test_sin_inventario_queda_vacio_y_no_nulo() -> None:
    """La columna es `not null` con `{}` por omisión: nunca se manda null."""
    assert _crear().inventario_ingreso == {}


def test_pares_de_texto_se_guardan_tal_cual() -> None:
    inventario = {"Gato": "Sí", "Radio": "Pantalla rayada"}

    assert _crear(inventario_ingreso=inventario).inventario_ingreso == inventario


def test_los_valores_se_normalizan_a_texto() -> None:
    """Es lo que se imprime, así que se guarda ya en la forma en que se lee.

    Un `true` desde la API o desde el móvil es una forma legítima de decir que
    la cosa está: se traduce en vez de rechazarse.
    """
    orden = _crear(
        inventario_ingreso={
            "Gato": True,
            "Caucho de repuesto": False,
            "Litros de aceite": 2,
            "Alfombras": None,
        }
    )

    assert orden.inventario_ingreso == {
        "Gato": "Sí",
        "Caucho de repuesto": "No",
        "Litros de aceite": "2",
        "Alfombras": "",
    }


def test_las_claves_y_los_valores_se_recortan() -> None:
    orden = _crear(inventario_ingreso={"  Gato  ": "  en el maletero  "})

    assert orden.inventario_ingreso == {"Gato": "en el maletero"}


def test_una_fila_sin_nombre_se_descarta() -> None:
    """El formulario deja añadir filas; alguna se queda a medias."""
    orden = _crear(inventario_ingreso={"Gato": "Sí", "   ": "algo", "": "otra cosa"})

    assert orden.inventario_ingreso == {"Gato": "Sí"}


def test_no_se_admiten_estructuras_anidadas() -> None:
    with pytest.raises(ValidationError, match="anidados"):
        _crear(inventario_ingreso={"Herramientas": ["llave", "destornillador"]})

    with pytest.raises(ValidationError, match="anidados"):
        _crear(inventario_ingreso={"Radio": {"marca": "Pioneer"}})


def test_demasiadas_cosas_se_rechazan() -> None:
    """Sin tope, la fila de la orden engorda y se lleva en cada consulta del
    tablero, que es la pantalla que más se mira."""
    exceso = {f"Cosa {n}": "Sí" for n in range(MAXIMO_ENTRADAS_INVENTARIO + 1)}

    with pytest.raises(ValidationError, match=str(MAXIMO_ENTRADAS_INVENTARIO)):
        _crear(inventario_ingreso=exceso)


def test_el_tope_exacto_se_acepta() -> None:
    justo = {f"Cosa {n}": "Sí" for n in range(MAXIMO_ENTRADAS_INVENTARIO)}

    assert len(_crear(inventario_ingreso=justo).inventario_ingreso) == MAXIMO_ENTRADAS_INVENTARIO


def test_claves_y_valores_largos_se_cortan() -> None:
    orden = _crear(inventario_ingreso={"x" * 200: "y" * 500})
    clave, valor = next(iter(orden.inventario_ingreso.items()))

    assert len(clave) == LARGO_CLAVE_INVENTARIO
    assert len(valor) == LARGO_VALOR_INVENTARIO


def test_algo_que_no_es_un_objeto_lo_rechaza_pydantic() -> None:
    with pytest.raises(ValidationError):
        _crear(inventario_ingreso=["Gato", "Radio"])


# -----------------------------------------------------------------------------
# Edición
# -----------------------------------------------------------------------------


def test_editar_sin_inventario_no_lo_toca() -> None:
    """`exclude_unset` distingue "no vino" de "vino vacío", que es lo que
    permite vaciar el inventario a propósito."""
    assert "inventario_ingreso" not in OrdenEditar(notas_internas="algo").model_dump(
        exclude_unset=True
    )


def test_editar_con_el_inventario_vacio_lo_borra() -> None:
    datos = OrdenEditar(inventario_ingreso={})

    assert datos.model_dump(exclude_unset=True) == {"inventario_ingreso": {}}


def test_editar_normaliza_igual_que_el_alta() -> None:
    datos = OrdenEditar(inventario_ingreso={" Gato ": True})

    assert datos.inventario_ingreso == {"Gato": "Sí"}
