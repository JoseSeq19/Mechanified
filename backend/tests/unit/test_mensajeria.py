"""El transporte del correo, sin red.

Solo se prueba el buzón de desarrollo: es el único de los dos transportes que se
puede ejercitar sin un servidor de correo, y es además el que se usa por
omisión, así que un fallo suyo se notaría en cada demostración.

Lo que se comprueba no es "se escribió un archivo", sino que el mensaje tenga la
forma que hace falta para que un cliente de correo lo muestre bien: las dos
alternativas, el nombre visible del taller y una respuesta que vuelve al taller.
"""

from email import message_from_bytes
from email.header import decode_header, make_header
from email.message import Message
from pathlib import Path

import pytest

from app.modules.notificaciones.mensajeria import ErrorEnvio, MensajeroBuzon
from app.modules.notificaciones.plantillas import Correo

CORREO = Correo(
    asunto="Tu presupuesto está listo · DLT-00042",
    texto="Hola Andrés, revisamos tu vehículo.",
    html="<!doctype html><html><body><p>Hola Andrés</p></body></html>",
)


async def _enviar(carpeta: Path, destinatario: str = "cliente@ejemplo.test") -> Message:
    mensajero = MensajeroBuzon(carpeta, "notificaciones@mechanified.local")
    await mensajero.enviar(
        destinatario=destinatario,
        correo=CORREO,
        nombre_remitente="Taller Delta",
        responder_a="hola@delta.test",
    )
    archivos = sorted(carpeta.glob("*.eml"))
    assert len(archivos) == 1
    return message_from_bytes(archivos[0].read_bytes())


async def test_guarda_un_eml_que_se_puede_abrir(tmp_path: Path) -> None:
    mensaje = await _enviar(tmp_path)

    # El asunto viaja codificado (RFC 2047) porque lleva acentos y el punto
    # volado. Lo que importa es que al decodificarlo vuelva entero: media
    # plantilla del producto está en español y un asunto roto se ve desde la
    # bandeja de entrada.
    assert str(make_header(decode_header(mensaje["Subject"]))) == CORREO.asunto
    assert mensaje["To"] == "cliente@ejemplo.test"


async def test_el_remitente_visible_es_el_taller(tmp_path: Path) -> None:
    """El cliente reconoce al taller, no al proveedor del software."""
    mensaje = await _enviar(tmp_path)

    assert mensaje["From"] == "Taller Delta <notificaciones@mechanified.local>"
    # Y si contesta, le llega al taller, no a un buzón que nadie lee.
    assert mensaje["Reply-To"] == "hola@delta.test"


async def test_lleva_texto_y_html(tmp_path: Path) -> None:
    mensaje = await _enviar(tmp_path)
    tipos = {parte.get_content_type() for parte in mensaje.walk() if not parte.is_multipart()}

    assert tipos == {"text/plain", "text/html"}


async def test_una_direccion_imposible_no_se_intenta(tmp_path: Path) -> None:
    """Es fallo permanente: reintentarlo cuatro veces no la hace existir."""
    with pytest.raises(ErrorEnvio) as excinfo:
        await _enviar(tmp_path, destinatario="esto no es un correo")

    assert excinfo.value.permanente
    assert not list(tmp_path.glob("*.eml"))


async def test_la_carpeta_se_crea_sola(tmp_path: Path) -> None:
    """Nadie debería tener que preparar el buzón a mano antes de arrancar."""
    destino = tmp_path / "buzon" / "anidado"
    await _enviar(destino)

    assert destino.is_dir()
