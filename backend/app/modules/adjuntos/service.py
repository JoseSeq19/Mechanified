"""Lógica de adjuntos de una orden.

El archivo llega al bucket por su cuenta, sin pasar por aquí (ver el docstring
de `schemas.py`). Lo que hace este servicio es registrar, listar y dar de baja
los metadatos, y una cosa más que es la importante: **comprobar que la ruta
declarada pertenece a esta orden y a este taller**.

Esa comprobación existe aunque la base también la haga. El trigger
`mch_adjuntos_ruta_guard` verifica la primera carpeta —el taller—, que es lo que
sostiene el aislamiento; la segunda —la orden— no la mira nadie en SQL, y sin
este filtro alguien del mismo taller podría registrar en la orden A un archivo
guardado bajo la carpeta de la B, y la foto aparecería en las dos fichas.

No se exige que la orden esté abierta, al contrario que con las líneas de mano
de obra y de repuestos. Una foto no cambia ningún importe, y la evidencia de la
entrega se sube justo cuando la orden pasa a entregada.
"""

import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.exc import StaleDataError

from app.core.exceptions import (
    ErrorConflicto,
    ErrorNoEncontrado,
    ErrorPermiso,
    ErrorValidacion,
    extraer_sqlstate,
)
from app.core.security import UsuarioAutenticado
from app.modules.adjuntos.models import Adjunto
from app.modules.adjuntos.schemas import AdjuntoRegistrar
from app.modules.ordenes import service as srv_ordenes

_RELACIONES = (selectinload(Adjunto.autor),)

#: Lo que puede llevar el último tramo de la ruta. Sin barras, sin `..` y sin
#: nada que no se pueda escribir en una URL firmada.
_NOMBRE_EN_RUTA = re.compile(r"^[A-Za-z0-9._\-]{1,180}$")


def _validar_ruta(ruta: str, taller_id: UUID, orden_id: UUID) -> str:
    """Comprueba la convención `{taller_id}/{orden_id}/{archivo}`."""
    prefijo = f"{taller_id}/{orden_id}/"
    archivo = ruta[len(prefijo) :] if ruta.startswith(prefijo) else ""

    if not archivo or not _NOMBRE_EN_RUTA.match(archivo):
        raise ErrorValidacion(
            "La ruta del archivo no corresponde a esta orden.",
            {"esperado": f"{prefijo}<archivo>", "recibido": ruta},
        )
    return ruta


async def listar(sesion: AsyncSession, orden_id: UUID) -> list[Adjunto]:
    await srv_ordenes.obtener(sesion, orden_id)  # 404 si es de otro taller

    filas = await sesion.scalars(
        select(Adjunto)
        .where(Adjunto.orden_id == orden_id)
        .options(*_RELACIONES)
        .order_by(Adjunto.creado_en)
    )
    return list(filas.all())


async def obtener(sesion: AsyncSession, adjunto_id: UUID) -> Adjunto:
    adjunto = await sesion.scalar(
        select(Adjunto).where(Adjunto.id == adjunto_id).options(*_RELACIONES)
    )
    if adjunto is None:
        raise ErrorNoEncontrado("Ese archivo no existe o es de otro taller.")
    return adjunto


async def registrar(
    sesion: AsyncSession,
    orden_id: UUID,
    datos: AdjuntoRegistrar,
    usuario: UsuarioAutenticado,
) -> Adjunto:
    """Da de alta los metadatos de un archivo ya subido al bucket."""
    orden = await srv_ordenes.obtener(sesion, orden_id)
    _validar_ruta(datos.ruta_storage, orden.taller_id, orden_id)

    adjunto = Adjunto(
        **datos.model_dump(),
        orden_id=orden_id,
        taller_id=orden.taller_id,
        subido_por=usuario.id,
    )
    sesion.add(adjunto)

    try:
        await sesion.flush()
    except IntegrityError as exc:
        codigo = extraer_sqlstate(exc)
        if codigo == "23505":
            raise ErrorConflicto(
                "Ese archivo ya está registrado en la orden.", {"campo": "ruta_storage"}
            ) from exc
        if codigo == "23503":
            # `subido_por` apunta a `perfiles`: pasa si la persona está en Auth
            # pero su perfil se borró. Mejor dejar el archivo sin autor que
            # perderlo.
            adjunto.subido_por = None
            await sesion.flush()
        else:
            raise

    return await obtener(sesion, adjunto.id)


async def eliminar(sesion: AsyncSession, adjunto_id: UUID) -> str:
    """Borra la fila y devuelve la ruta, para que el navegador borre el objeto.

    El orden importa: primero la fila, que es la que tiene la política estricta
    —solo quien lo subió o administración—, y solo si eso pasa se borra el
    archivo. Al revés quedaría una fila apuntando a un objeto que ya no existe,
    es decir una foto rota en la ficha.
    """
    adjunto = await obtener(sesion, adjunto_id)
    ruta = adjunto.ruta_storage

    await sesion.delete(adjunto)
    try:
        await sesion.flush()
    except StaleDataError as exc:
        # `adjuntos_delete` solo deja a administración o a quien lo subió; a los
        # demás el DELETE no empareja ninguna fila y SQLAlchemy lo cuenta como
        # fila desaparecida. Sin esto sería un 500 en lugar de un permiso.
        raise ErrorPermiso(
            "Este archivo solo lo puede borrar quien lo subió o la administración del taller."
        ) from exc

    return ruta
