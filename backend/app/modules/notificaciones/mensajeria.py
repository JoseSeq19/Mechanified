"""Salida física del correo: quién lo pone en la red.

Dos implementaciones tras la misma interfaz:

  - `MensajeroBuzon` no envía nada. Guarda cada mensaje como un archivo `.eml`
    en una carpeta local, que cualquier cliente de correo abre tal cual. Es el
    modo por omisión, y no es una simulación de juguete: el archivo contiene
    exactamente los mismos encabezados y el mismo cuerpo que se enviarían. Sirve
    para desarrollar sin proveedor y, sobre todo, para que una prueba con datos
    inventados no acabe escribiéndole a una dirección real.

  - `MensajeroSmtp` envía de verdad. SMTP y no la API de un proveedor concreto
    porque lo habla todo el mundo —Gmail, Zoho, Brevo, SES, el servidor del
    hosting— y cambiar de proveedor es cambiar tres variables de entorno, no
    reescribir este archivo.

`smtplib` es bloqueante, así que el envío va a un hilo aparte: el worker corre
en el mismo bucle de eventos que la API, y un servidor de correo lento no puede
quedarse con él.
"""

import asyncio
import logging
import re
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path
from typing import Protocol

from app.core.config import Configuracion
from app.modules.notificaciones.plantillas import Correo

_log = logging.getLogger(__name__)

#: Dirección mínimamente creíble. No valida el buzón —eso solo lo dice el envío—
#: pero atrapa lo que nunca podría llegar.
_CORREO = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")


class ErrorEnvio(Exception):
    """No se pudo entregar el mensaje.

    `permanente` distingue "vuelve a intentarlo" de "no insistas": una dirección
    rechazada por el servidor no va a existir en cinco minutos, y reintentarla
    cuatro veces solo ensucia la cola y la reputación del remitente.
    """

    def __init__(self, mensaje: str, *, permanente: bool = False) -> None:
        super().__init__(mensaje)
        self.permanente = permanente


class Mensajero(Protocol):
    """Lo que el worker necesita de un transporte."""

    async def enviar(
        self,
        *,
        destinatario: str,
        correo: Correo,
        nombre_remitente: str,
        responder_a: str | None = None,
    ) -> None: ...


def _armar(
    *,
    destinatario: str,
    correo: Correo,
    nombre_remitente: str,
    remitente: str,
    responder_a: str | None,
) -> EmailMessage:
    """Construye el mensaje multiparte, igual para los dos transportes."""
    if not _CORREO.match(destinatario):
        raise ErrorEnvio(f"Dirección inválida: {destinatario}", permanente=True)

    mensaje = EmailMessage()
    # El nombre visible es el del taller y la dirección la del producto: el
    # cliente reconoce a quién le dejó el vehículo, no a su proveedor de software.
    mensaje["From"] = formataddr((nombre_remitente, remitente))
    mensaje["To"] = destinatario
    mensaje["Subject"] = correo.asunto
    mensaje["Date"] = formatdate(localtime=True)
    mensaje["Message-ID"] = make_msgid(domain=remitente.split("@")[-1] or None)
    if responder_a:
        # Responder al correo debe llegarle al taller, no a un buzón que nadie lee.
        mensaje["Reply-To"] = responder_a
    mensaje["Auto-Submitted"] = "auto-generated"

    mensaje.set_content(correo.texto)
    mensaje.add_alternative(correo.html, subtype="html")
    return mensaje


class MensajeroBuzon:
    """Guarda el correo en disco en vez de enviarlo."""

    def __init__(self, carpeta: Path, remitente: str) -> None:
        self.carpeta = carpeta
        self.remitente = remitente

    async def enviar(
        self,
        *,
        destinatario: str,
        correo: Correo,
        nombre_remitente: str,
        responder_a: str | None = None,
    ) -> None:
        mensaje = _armar(
            destinatario=destinatario,
            correo=correo,
            nombre_remitente=nombre_remitente,
            remitente=self.remitente,
            responder_a=responder_a,
        )

        self.carpeta.mkdir(parents=True, exist_ok=True)
        sello = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        limpio = re.sub(r"[^a-zA-Z0-9._-]", "_", destinatario)[:40]
        archivo = self.carpeta / f"{sello}_{limpio}.eml"

        await asyncio.to_thread(archivo.write_bytes, mensaje.as_bytes())
        _log.info("Correo guardado en el buzón: %s (%s)", archivo.name, correo.asunto)


class MensajeroSmtp:
    """Envía por SMTP, con o sin cifrado según la configuración."""

    def __init__(self, cfg: Configuracion) -> None:
        self.host = cfg.smtp_host
        self.puerto = cfg.smtp_puerto
        self.usuario = cfg.smtp_usuario
        self.clave = cfg.smtp_clave
        self.seguridad = cfg.smtp_seguridad
        self.remitente = cfg.email_remitente

    async def enviar(
        self,
        *,
        destinatario: str,
        correo: Correo,
        nombre_remitente: str,
        responder_a: str | None = None,
    ) -> None:
        mensaje = _armar(
            destinatario=destinatario,
            correo=correo,
            nombre_remitente=nombre_remitente,
            remitente=self.remitente,
            responder_a=responder_a,
        )
        await asyncio.to_thread(self._entregar, mensaje)

    def _entregar(self, mensaje: EmailMessage) -> None:
        contexto = ssl.create_default_context()
        try:
            if self.seguridad == "ssl":
                servidor: smtplib.SMTP = smtplib.SMTP_SSL(
                    self.host, self.puerto, timeout=30, context=contexto
                )
            else:
                servidor = smtplib.SMTP(self.host, self.puerto, timeout=30)

            with servidor:
                if self.seguridad == "starttls":
                    servidor.starttls(context=contexto)
                if self.usuario:
                    servidor.login(self.usuario, self.clave)
                servidor.send_message(mensaje)

        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPNotSupportedError) as exc:
            # El servidor dice que a esa dirección no se puede. Insistir no ayuda.
            raise ErrorEnvio(str(exc), permanente=True) from exc
        except smtplib.SMTPResponseException as exc:
            # 4xx es temporal (buzón lleno, límite de envío); 5xx es definitivo.
            raise ErrorEnvio(
                f"{exc.smtp_code} {exc.smtp_error!r}", permanente=500 <= exc.smtp_code < 600
            ) from exc
        except (OSError, smtplib.SMTPException) as exc:
            # Red caída, DNS, timeout: exactamente el caso para el que existe la cola.
            raise ErrorEnvio(str(exc)) from exc


def mensajero_de(cfg: Configuracion) -> Mensajero:
    """El transporte que toca según la configuración."""
    if cfg.email_modo == "smtp":
        return MensajeroSmtp(cfg)
    return MensajeroBuzon(cfg.ruta_buzon, cfg.email_remitente)
