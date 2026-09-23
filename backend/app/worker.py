"""Worker de notificaciones como proceso propio.

    python -m app.worker

Es lo que se despliega en producción, con `MCH_WORKER_EMBEBIDO=false` en la API:
así un servidor de correo lento no compite por el bucle de eventos que atiende
las peticiones. En desarrollo no hace falta arrancarlo, porque la API ya lo lleva
dentro.

Correr los dos a la vez tampoco rompe nada: la cola se reparte con
`SELECT ... FOR UPDATE SKIP LOCKED`.
"""

import asyncio
import contextlib
import logging

from app.core.config import obtener_configuracion
from app.modules.notificaciones.mensajeria import mensajero_de
from app.modules.notificaciones.worker import bucle


async def principal() -> None:
    cfg = obtener_configuracion()
    logging.basicConfig(
        level=getattr(logging, cfg.log_nivel.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s :: %(message)s",
    )
    logging.getLogger(__name__).info(
        "Modo de correo: %s%s",
        cfg.email_modo,
        f" ({cfg.ruta_buzon})" if cfg.email_modo == "buzon" else f" ({cfg.smtp_host})",
    )

    await bucle(
        mensajero_de(cfg),
        intervalo_seg=cfg.worker_intervalo_seg,
        limite=cfg.worker_lote,
    )


if __name__ == "__main__":
    # Ctrl+C es la forma normal de pararlo: no es un error que merezca traza.
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(principal())
