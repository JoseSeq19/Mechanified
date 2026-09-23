"""Redacción de los correos que el taller manda al cliente.

Módulo deliberadamente puro: entra un `Contexto`, sale un `Correo`. Ni base de
datos, ni sesión, ni configuración. Por eso se puede probar el texto exacto que
recibe el cliente sin levantar nada, y por eso el worker y la vista previa de la
ficha usan lo mismo: lo que se ve antes de enviar es lo que sale.

Sobre el HTML: nada de hojas de estilo ni de flexbox. Los clientes de correo
—Outlook el primero— siguen necesitando tablas y estilos en línea, así que el
maquetado es el que es a propósito. Los colores son los del sistema de diseño,
copiados como literales porque un correo no puede leer `tokens.css`.

Cada mensaje lleva además su versión en texto plano. No es un adorno: hay quien
lee el correo en texto, y un mensaje que solo existe en HTML le llega en blanco.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from html import escape

from app.modules.notificaciones.models import PlantillaCorreo

# Paleta, copiada de web/src/styles/tokens.css.
_PETROLEO = "#0f5c63"
_PETROLEO_OSCURO = "#06282c"
_TINTA = "#10191c"
_TINTA_MEDIA = "#4a5a5e"
_LINEA = "#dde4e4"
_LIENZO = "#f4f7f6"


@dataclass(frozen=True)
class Contexto:
    """Todo lo que puede aparecer en un correo, ya resuelto.

    Lo arma `service.construir_contexto` leyendo la base. Que sea un dataclass
    cerrado y no un diccionario suelto es lo que hace que un dato que falta se
    note al escribir la plantilla, y no en el buzón del cliente.
    """

    taller_nombre: str
    cliente_nombre: str
    folio: str
    vehiculo: str
    placa: str
    moneda: str = ""
    taller_telefono: str | None = None
    taller_email: str | None = None
    taller_direccion: str | None = None
    #: Enlace público, cuando el aviso lleva uno.
    enlace: str | None = None
    total: Decimal | None = None
    version: int | None = None
    valido_hasta: date | None = None


@dataclass(frozen=True)
class Correo:
    asunto: str
    texto: str
    html: str


def _dinero(valor: Decimal, moneda: str) -> str:
    """1234.5 -> '1.234,50 USD'. Mismo formato que usa la interfaz."""
    entero, _, decimales = f"{valor:,.2f}".partition(".")
    cifra = f"{entero.replace(',', '.')},{decimales}"
    return f"{cifra} {moneda}".strip()


def _fecha(valor: date) -> str:
    meses = (
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    )
    return f"{valor.day} de {meses[valor.month - 1]} de {valor.year}"


def _pie_texto(ctx: Contexto) -> str:
    partes = [ctx.taller_nombre]
    partes += [p for p in (ctx.taller_telefono, ctx.taller_direccion) if p]
    return " · ".join(partes)


def _documento(
    *,
    ctx: Contexto,
    titulo: str,
    parrafos: list[str],
    datos: list[tuple[str, str]],
    boton: tuple[str, str] | None,
    cierre: str,
) -> tuple[str, str]:
    """Arma las dos versiones del mensaje a partir de las mismas piezas.

    Escribirlas por separado invitaba a que una se quedara atrás; así el texto
    plano no puede acabar diciendo algo distinto del HTML.
    """
    lineas = [ctx.taller_nombre, "", titulo, ""]
    lineas += [*parrafos, ""]
    lineas += [f"{etiqueta}: {valor}" for etiqueta, valor in datos]
    if boton:
        lineas += ["", f"{boton[0]}: {boton[1]}"]
    lineas += ["", cierre, "", "—", _pie_texto(ctx)]
    texto = "\n".join(lineas)

    _celda = f"padding:6px 0;color:{_TINTA_MEDIA};font-size:13px"
    _celda_valor = "padding:6px 0;text-align:right;font-size:13px;font-weight:600"
    filas_datos = "".join(
        f'<tr><td style="{_celda}">{escape(e)}</td><td style="{_celda_valor}">{escape(v)}</td></tr>'
        for e, v in datos
    )

    bloque_boton = ""
    if boton:
        etiqueta_boton, url = boton
        estilo_boton = (
            f"display:inline-block;background:{_PETROLEO};color:#ffffff;"
            "text-decoration:none;padding:12px 22px;border-radius:7px;"
            "font-weight:600;font-size:15px"
        )
        estilo_respaldo = (
            f"padding:6px 0 0;color:{_TINTA_MEDIA};font-size:12px;word-break:break-all"
        )
        # El enlace va también en texto: hay clientes de correo que no pintan el
        # botón, y quedarse sin forma de abrirlo deja el aviso inservible.
        bloque_boton = (
            '<tr><td style="padding:8px 0 4px">'
            f'<a href="{escape(url, quote=True)}" style="{estilo_boton}">'
            f"{escape(etiqueta_boton)}</a></td></tr>"
            f'<tr><td style="{estilo_respaldo}">'
            f"Si el botón no funciona, copia este enlace: {escape(url)}</td></tr>"
        )

    estilo_parrafo = "padding:0 0 12px;font-size:15px;line-height:1.55"
    cuerpo = "".join(f'<tr><td style="{estilo_parrafo}">{escape(p)}</td></tr>' for p in parrafos)

    pie = escape(_pie_texto(ctx))
    if ctx.taller_email:
        correo_taller = escape(ctx.taller_email, quote=True)
        pie += (
            f' · <a href="mailto:{correo_taller}" style="color:{_PETROLEO}">'
            f"{escape(ctx.taller_email)}</a>"
        )

    html = _ESQUELETO.format(
        titulo=escape(titulo),
        taller=escape(ctx.taller_nombre),
        cuerpo=cuerpo,
        datos=filas_datos,
        boton=bloque_boton,
        cierre=escape(cierre),
        pie=pie,
        petroleo=_PETROLEO_OSCURO,
        tinta=_TINTA,
        medio=_TINTA_MEDIA,
        linea=_LINEA,
        lienzo=_LIENZO,
    )
    return texto, html


#: Maquetado del mensaje. Va aparte para que las plantillas de arriba se lean
#: como texto y no como HTML entreverado.
_ESQUELETO = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{titulo}</title></head>
<body style="margin:0;padding:24px 12px;background:{lienzo};color:{tinta};
 font-family:'Segoe UI',system-ui,-apple-system,Roboto,Helvetica,Arial,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
 style="max-width:560px;background:#ffffff;border:1px solid {linea};border-radius:12px">
<tr><td style="background:{petroleo};color:#ffffff;padding:20px 28px;
 border-radius:12px 12px 0 0;font-size:17px;font-weight:600">{taller}</td></tr>
<tr><td style="padding:26px 28px 6px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td style="padding:0 0 14px;font-size:20px;font-weight:650;line-height:1.3">{titulo}</td></tr>
{cuerpo}
</table></td></tr>
<tr><td style="padding:0 28px">
<table role="presentation" width="100%" cellpadding="10" cellspacing="0" border="0"
 style="background:{lienzo};border-radius:8px">
{datos}
</table></td></tr>
<tr><td style="padding:16px 28px 0">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
{boton}
</table></td></tr>
<tr><td style="padding:18px 28px 26px;font-size:14px;line-height:1.55;color:{medio}">
{cierre}</td></tr>
<tr><td style="border-top:1px solid {linea};padding:16px 28px;font-size:12px;color:{medio};
 border-radius:0 0 12px 12px">{pie}</td></tr>
</table>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
 style="max-width:560px"><tr><td style="padding:12px 4px;font-size:11px;color:{medio}">
Recibes este correo porque dejaste tu vehículo en {taller}.</td></tr></table>
</td></tr></table></body></html>"""


def _exigir_enlace(ctx: Contexto, plantilla: PlantillaCorreo) -> str:
    if not ctx.enlace:
        raise ValueError(f"La plantilla {plantilla.value} necesita un enlace y no lo tiene.")
    return ctx.enlace


def _presupuesto(ctx: Contexto) -> Correo:
    enlace = _exigir_enlace(ctx, PlantillaCorreo.PRESUPUESTO_ENVIADO)

    datos = [("Orden", ctx.folio), ("Vehículo", f"{ctx.placa} · {ctx.vehiculo}")]
    if ctx.total is not None:
        datos.append(("Total presupuestado", _dinero(ctx.total, ctx.moneda)))
    if ctx.valido_hasta is not None:
        datos.append(("Válido hasta", _fecha(ctx.valido_hasta)))

    texto, html = _documento(
        ctx=ctx,
        titulo="Tu presupuesto está listo",
        parrafos=[
            f"Hola {ctx.cliente_nombre}, revisamos tu {ctx.vehiculo} y preparamos el "
            "presupuesto del trabajo que hace falta.",
            "Puedes verlo detallado, línea por línea, y aprobarlo o rechazarlo desde el "
            "enlace. No hace falta crear una cuenta ni contestar este correo.",
        ],
        datos=datos,
        boton=("Ver el presupuesto", enlace),
        cierre=(
            "No empezamos ninguna reparación hasta que lo apruebes. Si tienes dudas, "
            "llámanos y lo repasamos contigo."
        ),
    )
    version = f" (versión {ctx.version})" if ctx.version and ctx.version > 1 else ""
    return Correo(
        asunto=f"Presupuesto de tu {ctx.vehiculo}{version} · {ctx.folio}",
        texto=texto,
        html=html,
    )


def _vehiculo_listo(ctx: Contexto) -> Correo:
    datos = [("Orden", ctx.folio), ("Vehículo", f"{ctx.placa} · {ctx.vehiculo}")]
    if ctx.taller_direccion:
        datos.append(("Dónde recogerlo", ctx.taller_direccion))
    if ctx.taller_telefono:
        datos.append(("Teléfono", ctx.taller_telefono))

    texto, html = _documento(
        ctx=ctx,
        titulo="Tu vehículo está listo",
        parrafos=[
            f"Hola {ctx.cliente_nombre}, terminamos el trabajo en tu {ctx.vehiculo} y ya "
            "pasó la revisión de calidad.",
            "Puedes pasar a recogerlo cuando te venga bien.",
        ],
        datos=datos,
        boton=None,
        cierre="Si prefieres coordinar la entrega para otro momento, llámanos y lo vemos.",
    )
    return Correo(
        asunto=f"Tu {ctx.vehiculo} está listo para recoger · {ctx.folio}",
        texto=texto,
        html=html,
    )


def _encuesta(ctx: Contexto) -> Correo:
    enlace = _exigir_enlace(ctx, PlantillaCorreo.ENCUESTA_SATISFACCION)

    texto, html = _documento(
        ctx=ctx,
        titulo="¿Cómo nos fue?",
        parrafos=[
            f"Hola {ctx.cliente_nombre}, gracias por dejarnos el servicio de tu {ctx.vehiculo}.",
            "Saber cómo te fue nos ayuda de verdad: son cuatro preguntas y se responde "
            "en menos de un minuto.",
        ],
        datos=[("Orden", ctx.folio), ("Vehículo", f"{ctx.placa} · {ctx.vehiculo}")],
        boton=("Responder la encuesta", enlace),
        cierre="Si algo no salió como esperabas, cuéntanoslo ahí y lo revisamos.",
    )
    return Correo(
        asunto=f"¿Cómo te fue con {ctx.taller_nombre}? · {ctx.folio}",
        texto=texto,
        html=html,
    )


_REDACTORES = {
    PlantillaCorreo.PRESUPUESTO_ENVIADO: _presupuesto,
    PlantillaCorreo.VEHICULO_LISTO: _vehiculo_listo,
    PlantillaCorreo.ENCUESTA_SATISFACCION: _encuesta,
}


def renderizar(plantilla: PlantillaCorreo, ctx: Contexto) -> Correo:
    """Redacta el mensaje. Lanza `ValueError` si al contexto le falta algo.

    El worker trata ese error como fallo permanente: reintentar no va a hacer
    aparecer un enlace que no existe.
    """
    redactor = _REDACTORES.get(plantilla)
    if redactor is None:
        raise ValueError(f"No hay plantilla de correo para {plantilla}.")
    return redactor(ctx)
