"""Organizaciones y cuentas del sitio, sin base de datos.

Lo que se prueba aquí es lo que decide cómo se llamarán las cosas —slugs y
prefijo que salen de un nombre cualquiera escrito en un formulario— y que la
identidad de cuenta no arrastre nunca claims de tenant a la sesión.
"""

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import ErrorAutenticacion
from app.core.security import cuenta_desde_claims
from app.modules.organizaciones.schemas import OrganizacionNueva, SolicitudNueva
from app.modules.organizaciones.service import identificadores
from app.modules.talleres.schemas import TallerAlta

# -----------------------------------------------------------------------------
# Identificadores
# -----------------------------------------------------------------------------


def test_los_identificadores_salen_de_cada_nombre() -> None:
    assert identificadores("Grupo La Meseta", "La Meseta Centro") == (
        "grupo-la-meseta",
        "la-meseta-centro",
        "LAM",
    )


def test_un_nombre_sin_identificador_posible_usa_el_de_respaldo() -> None:
    """En el alta por cuenta propia no hay a quién pedirle un --slug."""
    assert identificadores("A1", "¡!") == ("organizacion", "taller", "MCH")


# -----------------------------------------------------------------------------
# Formularios del sitio
# -----------------------------------------------------------------------------


def test_la_organizacion_nueva_normaliza_lo_que_llega_del_formulario() -> None:
    datos = OrganizacionNueva(
        nombre="  Taller García  ",
        sede="   ",
        nombre_completo=" Ana García ",
        telefono="",
        moneda="cop",
    )

    assert datos.nombre == "Taller García"
    assert datos.sede is None
    assert datos.nombre_completo == "Ana García"
    assert datos.telefono is None
    assert datos.moneda == "COP"
    assert datos.tarifa_hora_default == Decimal(0)


@pytest.mark.parametrize(
    "campos",
    [
        {"nombre": "X"},
        {"moneda": "PESOS"},
        {"impuesto_pct": "101"},
        {"tarifa_hora_default": "-1"},
    ],
)
def test_la_organizacion_nueva_rechaza_lo_que_la_base_rechazaria(campos: dict[str, str]) -> None:
    base = {"nombre": "Taller Bueno", "nombre_completo": "Ana García"}
    with pytest.raises(ValidationError):
        OrganizacionNueva.model_validate({**base, **campos})


def test_la_solicitud_no_pide_correo() -> None:
    """Es el de la cuenta; si el formulario lo mandara, se ignoraría."""
    assert "email" not in SolicitudNueva.model_fields


def test_la_solicitud_acota_las_sedes() -> None:
    with pytest.raises(ValidationError):
        SolicitudNueva(nombre_organizacion="Grupo", nombre_contacto="Ana", sedes=0)


# -----------------------------------------------------------------------------
# Alta del equipo
# -----------------------------------------------------------------------------


def test_el_alta_del_equipo_no_admite_las_dos_formas_de_organizacion() -> None:
    with pytest.raises(ValidationError, match="no las dos cosas"):
        TallerAlta(
            nombre="La Meseta Sur",
            admin_email="sur@example.com",
            admin_nombre="Óscar Rangel",
            organizacion="grupo-la-meseta",
            organizacion_nombre="Otro Grupo",
        )


def test_el_slug_de_la_organizacion_se_normaliza() -> None:
    alta = TallerAlta(
        nombre="La Meseta Sur",
        admin_email="sur@example.com",
        admin_nombre="Óscar Rangel",
        organizacion="  Grupo-La-Meseta ",
    )
    assert alta.organizacion == "grupo-la-meseta"


# -----------------------------------------------------------------------------
# Identidad de cuenta
# -----------------------------------------------------------------------------


def test_la_cuenta_no_exige_taller() -> None:
    sub = uuid4()
    cuenta = cuenta_desde_claims({"sub": str(sub), "email": "nueva@example.com"})

    assert cuenta.id == sub
    assert cuenta.email == "nueva@example.com"


def test_la_cuenta_no_lleva_claims_de_tenant_a_la_sesion_aunque_el_token_los_traiga() -> None:
    """Desde /cuenta solo se alcanza lo que se compara con auth.uid()."""
    cuenta = cuenta_desde_claims(
        {"sub": str(uuid4()), "taller_id": str(uuid4()), "rol": "admin_taller"}
    )

    assert set(cuenta.claims_rls) == {"sub", "role"}


def test_un_token_sin_sujeto_no_es_una_cuenta() -> None:
    with pytest.raises(ErrorAutenticacion):
        cuenta_desde_claims({"email": "x@example.com"})
