"""Derivación del identificador y del prefijo, y lectura de argumentos.

El alta en sí necesita base de datos y Supabase Auth, y se prueba en
`tests/integration/test_alta_taller.py`. Lo que se comprueba aquí es lo que
decide cómo se llamará el taller para siempre: el `slug`, que es único y global,
y el prefijo que llevarán todos sus folios.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.alta_taller import _argumentos, _datos
from app.core.exceptions import ErrorConflicto
from app.modules.talleres.alta import derivar_prefijo, derivar_slug
from app.modules.talleres.schemas import TallerAlta

# -----------------------------------------------------------------------------
# Identificador
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        ("Delta Motors", "delta-motors"),
        ("Talleres Peña & Hijos, C.A.", "talleres-pena-hijos-c-a"),
        ("  Taller   del   Este  ", "taller-del-este"),
        ("Autoservicio 24/7", "autoservicio-24-7"),
        ("MECÁNICA ÁVILA", "mecanica-avila"),
    ],
)
def test_slug_se_deriva_del_nombre(nombre: str, esperado: str) -> None:
    assert derivar_slug(nombre) == esperado


def test_slug_cumple_el_formato_de_la_base() -> None:
    """`talleres_slug_formato` exige empezar y acabar en letra o número."""
    slug = derivar_slug("-- Taller (nuevo) --")

    assert slug == "taller-nuevo"
    assert slug[0].isalnum() and slug[-1].isalnum()


def test_slug_no_pasa_de_cincuenta_caracteres() -> None:
    slug = derivar_slug("Taller " * 20)

    assert len(slug) <= 50
    assert not slug.endswith("-")


@pytest.mark.parametrize("nombre", ["A1", "—", "- -"])
def test_nombre_sin_slug_posible_pide_indicarlo(nombre: str) -> None:
    """Mejor pedirlo que inventar un identificador que nadie reconoce."""
    with pytest.raises(ErrorConflicto, match="--slug"):
        derivar_slug(nombre)


# -----------------------------------------------------------------------------
# Prefijo del folio
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        ("Delta Motors", "DEL"),
        ("Mecánica Ávila", "MEC"),
        ("3M Taller", "3MT"),
        ("Ab", "AB"),
    ],
)
def test_prefijo_se_deriva_del_nombre(nombre: str, esperado: str) -> None:
    assert derivar_prefijo(nombre) == esperado


def test_prefijo_imposible_pide_indicarlo() -> None:
    with pytest.raises(ErrorConflicto, match="--prefijo"):
        derivar_prefijo("&")


# -----------------------------------------------------------------------------
# Argumentos de la línea de comandos
# -----------------------------------------------------------------------------

_MINIMOS = [
    "--nombre",
    "Delta Motors",
    "--admin-correo",
    "Marisol@Example.com",
    "--admin-nombre",
    "Marisol Peñaranda",
]


def test_con_lo_minimo_el_resto_toma_valores_por_omision() -> None:
    datos = _datos(_argumentos(_MINIMOS))

    assert datos.nombre == "Delta Motors"
    assert datos.slug is None  # se deriva al crear
    assert datos.moneda == "USD"
    assert datos.impuesto_pct == Decimal(0)
    assert datos.dias_validez_presupuesto == 15
    assert datos.zona_horaria == "America/Caracas"
    # Pydantic normaliza el dominio pero respeta la parte local, que en teoría
    # distingue mayúsculas. `crear_taller` lo pasa entero a minúsculas antes de
    # crear la cuenta, porque es con eso con lo que se inicia sesión.
    assert str(datos.admin_email) == "Marisol@example.com"


def test_la_configuracion_inicial_se_puede_dar_entera() -> None:
    datos = _datos(
        _argumentos(
            [
                *_MINIMOS,
                "--slug",
                "Delta-Motors",
                "--moneda",
                "ves",
                "--tarifa",
                "18.50",
                "--impuesto",
                "16",
                "--prefijo",
                "dlt",
                "--dias-validez",
                "30",
                "--rif",
                "  J-40123456-7  ",
            ]
        )
    )

    # Lo que se escribe en minúscula se normaliza, no se rechaza.
    assert datos.slug == "delta-motors"
    assert datos.moneda == "VES"
    assert datos.prefijo_orden == "DLT"
    assert datos.tarifa_hora_default == Decimal("18.50")
    assert datos.dias_validez_presupuesto == 30
    assert datos.identificacion_fiscal == "J-40123456-7"


def test_un_correo_invalido_no_llega_a_la_base() -> None:
    with pytest.raises(ValidationError):
        _datos(
            _argumentos(
                [
                    "--nombre",
                    "Taller",
                    "--admin-correo",
                    "no-es-correo",
                    "--admin-nombre",
                    "Alguien",
                ]
            )
        )


def test_un_impuesto_fuera_de_rango_se_rechaza() -> None:
    with pytest.raises(ValidationError):
        _datos(_argumentos([*_MINIMOS, "--impuesto", "120"]))


def test_el_esquema_exige_nombre_y_administrador() -> None:
    with pytest.raises(ValidationError):
        TallerAlta(nombre="Delta Motors")  # type: ignore[call-arg]
