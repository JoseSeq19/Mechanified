"""Enlaces públicos que se le mandan al cliente.

Viven aquí y no en el módulo que los usa porque los arman dos sitios distintos:
el servicio que crea el documento y el worker que redacta el correo. Si cada uno
compusiera su URL, bastaría con cambiar una ruta de la web para que el enlace
del correo dejara de existir mientras el de la ficha sigue funcionando.

Las rutas tienen que coincidir con las que declara `web/src/app/App.tsx`.
"""

from app.core.config import obtener_configuracion


def _base() -> str:
    return obtener_configuracion().url_publica_web.rstrip("/")


def enlace_presupuesto(token: str) -> str:
    """Donde el cliente aprueba o rechaza, sin cuenta."""
    return f"{_base()}/presupuesto/{token}"


def enlace_encuesta(token: str) -> str:
    """Donde el cliente califica el servicio, sin cuenta."""
    return f"{_base()}/encuesta/{token}"
