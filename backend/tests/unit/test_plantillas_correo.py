"""Los correos que recibe el cliente.

Se prueban aquí, sin base de datos, porque `plantillas` es una función pura: el
texto exacto que sale del producto no debería necesitar un Postgres levantado
para poder revisarlo.

Lo que defienden estas pruebas es sobre todo que el mensaje sea *usable*: que
lleve el enlace también en texto, que el nombre del cliente no pueda inyectar
HTML, y que las dos versiones del mensaje cuenten lo mismo.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.modules.notificaciones.models import PlantillaCorreo
from app.modules.notificaciones.plantillas import Contexto, renderizar

BASE = Contexto(
    taller_nombre="Taller Delta",
    cliente_nombre="Andrés Villamizar",
    folio="DLT-00042",
    vehiculo="Ford Cargo 815 2019",
    placa="FL001AA",
    moneda="USD",
    taller_telefono="+58 212 555 0100",
    taller_email="hola@delta.test",
    taller_direccion="Av. Libertador 120",
)

CON_ENLACE = Contexto(**{**BASE.__dict__, "enlace": "https://mch.test/encuesta/abc123"})


def _completo(plantilla: PlantillaCorreo) -> Contexto:
    """Contexto con todo lo que cada plantilla pueda pedir."""
    extra: dict[str, object] = {"enlace": "https://mch.test/p/abc123"}
    if plantilla is PlantillaCorreo.PRESUPUESTO_ENVIADO:
        extra |= {
            "total": Decimal("1234.50"),
            "version": 2,
            "valido_hasta": date(2026, 9, 30),
        }
    return Contexto(**{**BASE.__dict__, **extra})


@pytest.mark.parametrize("plantilla", list(PlantillaCorreo))
def test_toda_plantilla_produce_las_dos_versiones(plantilla: PlantillaCorreo) -> None:
    correo = renderizar(plantilla, _completo(plantilla))

    assert correo.asunto.strip()
    assert correo.texto.strip()
    assert correo.html.lstrip().startswith("<!doctype html>")
    # Quien lee en texto plano tiene que poder identificar de qué orden le hablan.
    assert BASE.folio in correo.texto
    assert BASE.folio in correo.html


@pytest.mark.parametrize("plantilla", list(PlantillaCorreo))
def test_el_asunto_nombra_el_vehiculo_o_el_taller(plantilla: PlantillaCorreo) -> None:
    """Un asunto genérico se confunde con publicidad y no se abre."""
    asunto = renderizar(plantilla, _completo(plantilla)).asunto

    assert BASE.vehiculo in asunto or BASE.taller_nombre in asunto
    assert BASE.folio in asunto


def test_el_nombre_del_cliente_no_puede_inyectar_html() -> None:
    """El nombre lo escribe el taller en un formulario: es entrada no confiable."""
    ctx = Contexto(**{**BASE.__dict__, "cliente_nombre": "<script>alert(1)</script>"})

    html = renderizar(PlantillaCorreo.VEHICULO_LISTO, ctx).html

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_el_enlace_va_tambien_en_texto() -> None:
    """Hay clientes de correo que no pintan el botón.

    Si el enlace solo existiera como `href`, el aviso llegaría sin forma de
    abrirlo y la encuesta simplemente no se respondería.
    """
    correo = renderizar(PlantillaCorreo.ENCUESTA_SATISFACCION, CON_ENLACE)

    assert CON_ENLACE.enlace in correo.texto
    assert f'href="{CON_ENLACE.enlace}"' in correo.html
    assert correo.html.count(CON_ENLACE.enlace or "") >= 2  # el botón y el respaldo


def test_el_presupuesto_muestra_importe_y_validez() -> None:
    correo = renderizar(
        PlantillaCorreo.PRESUPUESTO_ENVIADO, _completo(PlantillaCorreo.PRESUPUESTO_ENVIADO)
    )

    # Formato es-: miles con punto, decimales con coma, moneda del taller.
    assert "1.234,50 USD" in correo.texto
    assert "30 de septiembre de 2026" in correo.texto
    assert "versión 2" in correo.asunto


def test_la_primera_version_no_se_anuncia_como_version() -> None:
    """Decir "versión 1" sugiere que hubo algo antes. No lo hubo."""
    ctx = Contexto(**{**BASE.__dict__, "enlace": "https://mch.test/p/x", "version": 1})

    assert "versión" not in renderizar(PlantillaCorreo.PRESUPUESTO_ENVIADO, ctx).asunto


def test_el_aviso_de_vehiculo_listo_dice_donde_recogerlo() -> None:
    correo = renderizar(PlantillaCorreo.VEHICULO_LISTO, BASE)

    assert BASE.taller_direccion in correo.texto
    assert BASE.taller_telefono in correo.texto
    # Este aviso no lleva enlace: no hay nada que el cliente tenga que responder.
    assert "http" not in correo.texto


@pytest.mark.parametrize(
    "plantilla",
    [PlantillaCorreo.PRESUPUESTO_ENVIADO, PlantillaCorreo.ENCUESTA_SATISFACCION],
)
def test_sin_enlace_falla_al_redactar(plantilla: PlantillaCorreo) -> None:
    """Mejor que el worker lo dé por perdido a mandar un correo inútil.

    Un aviso que invita a aprobar un presupuesto y no lleva a ninguna parte
    obliga al cliente a llamar, que es justo lo que el enlace venía a evitar.
    """
    with pytest.raises(ValueError, match=r"(?i)enlace"):
        renderizar(plantilla, BASE)


def test_el_pie_identifica_al_taller_no_al_producto() -> None:
    """Quien recibe el correo dejó el vehículo en un taller, no en Mechanified."""
    correo = renderizar(PlantillaCorreo.VEHICULO_LISTO, BASE)

    assert correo.texto.rstrip().endswith(
        f"{BASE.taller_nombre} · {BASE.taller_telefono} · {BASE.taller_direccion}"
    )
    assert BASE.taller_nombre in correo.html
