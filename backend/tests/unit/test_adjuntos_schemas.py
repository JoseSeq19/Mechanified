"""Validación de los metadatos de un adjunto y de la ruta del bucket.

La ruta es lo único de este módulo que vale la pena probar sin base de datos, y
es lo que más importa: de ella depende que un archivo no pueda aparecer colgado
de la orden de otro.
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import ErrorValidacion
from app.modules.adjuntos.models import ContextoAdjunto
from app.modules.adjuntos.schemas import TAMANO_MAXIMO, AdjuntoRegistrar
from app.modules.adjuntos.service import _validar_ruta

TALLER = uuid4()
ORDEN = uuid4()


def _datos(**extra: object) -> AdjuntoRegistrar:
    base = {
        "ruta_storage": f"{TALLER}/{ORDEN}/{uuid4().hex}-frontal.jpg",
        "nombre_archivo": "frontal.jpg",
        "mime": "image/jpeg",
        "tamano_bytes": 120_000,
    }
    return AdjuntoRegistrar(**{**base, **extra})


# -----------------------------------------------------------------------------
# Metadatos
# -----------------------------------------------------------------------------


def test_contexto_por_omision_es_el_ingreso() -> None:
    """Es el caso que más se repite: las fotos de recepción del vehículo."""
    assert _datos().contexto is ContextoAdjunto.INGRESO


@pytest.mark.parametrize("mime", ["image/jpeg", "IMAGE/PNG", " application/pdf "])
def test_mime_del_bucket_se_acepta_y_se_normaliza(mime: str) -> None:
    assert _datos(mime=mime).mime == mime.strip().lower()


@pytest.mark.parametrize("mime", ["image/gif", "video/mp4", "application/zip", "text/html"])
def test_mime_que_el_bucket_rechazaria_se_rechaza_antes(mime: str) -> None:
    """El bucket declara su lista; si aquí sobrara un tipo, la subida fallaría
    después de que la interfaz hubiera dicho que estaba bien."""
    with pytest.raises(ValidationError):
        _datos(mime=mime)


@pytest.mark.parametrize("tamano", [0, -1, TAMANO_MAXIMO + 1])
def test_tamano_fuera_del_limite_se_rechaza(tamano: int) -> None:
    with pytest.raises(ValidationError):
        _datos(tamano_bytes=tamano)


def test_el_nombre_pierde_las_carpetas() -> None:
    """Llega a la cabecera de una descarga y al documento impreso."""
    assert _datos(nombre_archivo="C:\\fotos\\..\\frontal.jpg").nombre_archivo == "frontal.jpg"


def test_descripcion_vacia_es_nula() -> None:
    assert _datos(descripcion="   ").descripcion is None


# -----------------------------------------------------------------------------
# Ruta en el bucket
# -----------------------------------------------------------------------------


def test_ruta_de_la_orden_se_acepta() -> None:
    ruta = f"{TALLER}/{ORDEN}/abc123-frontal.jpg"
    assert _validar_ruta(ruta, TALLER, ORDEN) == ruta


def test_ruta_de_otra_orden_del_mismo_taller_se_rechaza() -> None:
    """Lo que ningún trigger comprueba.

    La base verifica la primera carpeta —el taller—; si esta validación no
    existiera, alguien del taller podría registrar en una orden una foto
    guardada bajo la carpeta de otra, y aparecería en las dos fichas.
    """
    with pytest.raises(ErrorValidacion):
        _validar_ruta(f"{TALLER}/{uuid4()}/abc123-frontal.jpg", TALLER, ORDEN)


def test_ruta_de_otro_taller_se_rechaza() -> None:
    with pytest.raises(ErrorValidacion):
        _validar_ruta(f"{uuid4()}/{ORDEN}/abc123-frontal.jpg", TALLER, ORDEN)


@pytest.mark.parametrize(
    "archivo",
    [
        "",  # la carpeta de la orden, sin archivo
        "sub/carpeta.jpg",  # un nivel más, que la convención no contempla
        "../otra-orden/foto.jpg",
        "foto .jpg",  # un espacio rompe la URL firmada
    ],
)
def test_ultimo_tramo_invalido_se_rechaza(archivo: str) -> None:
    with pytest.raises(ErrorValidacion):
        _validar_ruta(f"{TALLER}/{ORDEN}/{archivo}", TALLER, ORDEN)
