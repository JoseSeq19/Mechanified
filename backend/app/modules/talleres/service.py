"""Lógica de la configuración del taller.

Ninguna consulta de aquí filtra por `taller_id`, y tampoco lo recibe: la
política `talleres_select` reduce la tabla a una sola fila —la del taller de la
sesión— antes de que el servicio la vea. Por eso `obtener` puede hacer un
`select(Taller)` sin `where` y esperar exactamente un resultado.

Lo verifica `tests/integration/test_talleres.py::test_solo_se_ve_el_taller_propio`.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.core.exceptions import (
    ErrorConflicto,
    ErrorNoEncontrado,
    ErrorPermiso,
    extraer_sqlstate,
)
from app.modules.talleres.models import Taller
from app.modules.talleres.schemas import TallerEditar


async def obtener(sesion: AsyncSession) -> Taller:
    """Devuelve el taller de la sesión.

    Que no haya fila no es un 404 corriente: significa que el token trae un
    `taller_id` que no existe o que apunta a un taller borrado. El mensaje lo
    dice, porque el usuario no puede hacer nada al respecto salvo avisar.
    """
    taller = await sesion.scalar(select(Taller))
    if taller is None:
        raise ErrorNoEncontrado(
            "Tu sesión apunta a un taller que no existe. Avisa a quien administra el sistema."
        )
    return taller


async def actualizar(sesion: AsyncSession, datos: TallerEditar) -> Taller:
    """Aplica un cambio parcial de configuración.

    Lo que se escribe aquí vale de ahora en adelante y no reescribe historia:
    cada línea de mano de obra se queda con la tarifa que tenía al registrarse y
    cada presupuesto con el impuesto con el que se emitió. Es deliberado —un
    documento que ya vio el cliente no puede cambiar de monto— y es lo que
    permite subir la tarifa sin recalcular lo ya facturado.
    """
    taller = await obtener(sesion)

    cambios = datos.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        setattr(taller, campo, valor)

    try:
        await sesion.flush()
    except StaleDataError as exc:
        # `talleres_update` exige mch_es_admin(): a quien no lo sea, el UPDATE no
        # le empareja ninguna fila y SQLAlchemy lo cuenta como fila desaparecida.
        # Sin esto saldría un 500 donde lo que hubo fue una falta de permiso.
        raise ErrorPermiso(
            "Solo el administrador del taller puede cambiar la configuración."
        ) from exc
    except IntegrityError as exc:
        if extraer_sqlstate(exc) == "23505":
            raise ErrorConflicto("Ya hay otro taller con esos datos.") from exc
        raise

    await sesion.refresh(taller)
    return taller
