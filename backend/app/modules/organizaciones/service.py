"""Lógica de la organización y de la cuenta del sitio.

Sirve a dos públicos:

- La aplicación de una sede (`obtener`), que solo quiere saber cómo se llama su
  organización para presentarse con ese nombre. La política
  `organizaciones_select` deja ver una sola fila, la del taller de la sesión, así
  que la consulta no lleva `where`.
- El sitio de Mechanified (`estado_cuenta`, `crear_propia`, `solicitar`), al que
  entra una cuenta que puede no tener taller todavía. Tampoco filtra por cuenta:
  lo hacen `auth.uid()` en las políticas y en las funciones de la migración.
"""

from collections.abc import Callable

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ErrorConflicto, ErrorNoEncontrado, extraer_sqlstate
from app.core.security import CuentaAutenticada
from app.modules.organizaciones.models import (
    EstadoSolicitud,
    Organizacion,
    SolicitudOrganizacion,
)
from app.modules.organizaciones.schemas import (
    EstadoCuenta,
    OrganizacionNueva,
    PertenenciaCuenta,
    SolicitudNueva,
    SolicitudRespuesta,
)
from app.modules.talleres.alta import derivar_prefijo, derivar_slug

#: Si del nombre no sale un identificador —"A1", "¡!"—, se usa esto como base y
#: la base de datos le añade el sufijo que lo haga único. Quien se registra no
#: tiene por qué saber qué es un slug.
SLUG_ORGANIZACION_RESPALDO = "organizacion"
SLUG_TALLER_RESPALDO = "taller"
PREFIJO_RESPALDO = "MCH"


async def obtener(sesion: AsyncSession) -> Organizacion:
    """La organización del taller de la sesión."""
    organizacion = await sesion.scalar(select(Organizacion))
    if organizacion is None:
        raise ErrorNoEncontrado(
            "Tu taller no aparece en ninguna organización. Avisa al equipo de Mechanified."
        )
    return organizacion


def identificadores(nombre_organizacion: str, nombre_taller: str) -> tuple[str, str, str]:
    """Slug de la organización, slug del taller y prefijo de folio.

    Son bases: si el slug ya está ocupado, la base de datos le añade un sufijo
    ("taller-garcia-2"). El prefijo sale del nombre de la sede porque es lo que
    lleva cada folio de esa sede, y se cambia después en Configuración.
    """
    return (
        _o_respaldo(derivar_slug, nombre_organizacion, SLUG_ORGANIZACION_RESPALDO),
        _o_respaldo(derivar_slug, nombre_taller, SLUG_TALLER_RESPALDO),
        _o_respaldo(derivar_prefijo, nombre_taller, PREFIJO_RESPALDO),
    )


def _o_respaldo(derivar: Callable[[str], str], nombre: str, respaldo: str) -> str:
    try:
        return derivar(nombre)
    except ErrorConflicto:
        return respaldo


async def _pertenencia(sesion: AsyncSession) -> PertenenciaCuenta | None:
    fila = (await sesion.execute(text("select * from public.mch_mi_cuenta()"))).mappings().first()
    return PertenenciaCuenta.model_validate(dict(fila)) if fila else None


async def _ultima_solicitud(sesion: AsyncSession) -> SolicitudOrganizacion | None:
    return await sesion.scalar(
        select(SolicitudOrganizacion).order_by(SolicitudOrganizacion.creado_en.desc()).limit(1)
    )


async def estado_cuenta(sesion: AsyncSession, cuenta: CuentaAutenticada) -> EstadoCuenta:
    """Dónde está la cuenta: con organización, esperando una, o sin nada."""
    solicitud = await _ultima_solicitud(sesion)
    return EstadoCuenta(
        email=cuenta.email,
        organizacion=await _pertenencia(sesion),
        solicitud=SolicitudRespuesta.model_validate(solicitud) if solicitud else None,
    )


async def _exigir_sin_organizacion(sesion: AsyncSession) -> None:
    pertenencia = await _pertenencia(sesion)
    if pertenencia is not None:
        raise ErrorConflicto(
            f"Tu cuenta ya pertenece a {pertenencia.organizacion_nombre}. Una cuenta es de "
            "una sola organización; para sumar una sede, pídeselo al equipo de Mechanified.",
            {"organizacion_id": str(pertenencia.organizacion_id)},
        )


async def crear_propia(
    sesion: AsyncSession, cuenta: CuentaAutenticada, datos: OrganizacionNueva
) -> EstadoCuenta:
    """Funda la organización con su primera sede, y a la cuenta como su admin.

    Lo hace `mch_crear_mi_organizacion()`, dentro de esta misma sesión RLS: la
    función saca la cuenta del token, no de un parámetro, y es la única puerta
    por la que una sesión de usuario escribe en `talleres` y `organizaciones`.

    El token que trae esta petición todavía no lleva taller. El siguiente sí:
    lo arma el hook de Auth a partir del perfil que se acaba de crear, así que
    el cliente tiene que renovar la sesión para entrar como administrador.
    """
    await _exigir_sin_organizacion(sesion)

    sede = datos.sede or datos.nombre
    slug_organizacion, slug_taller, prefijo = identificadores(datos.nombre, sede)

    try:
        await sesion.execute(
            text(
                "select * from public.mch_crear_mi_organizacion("
                " :nombre, :sede, :slug_organizacion, :slug_taller, :prefijo,"
                " :nombre_admin, :telefono, :moneda, :tarifa, :impuesto)"
            ),
            {
                "nombre": datos.nombre,
                "sede": sede,
                "slug_organizacion": slug_organizacion,
                "slug_taller": slug_taller,
                "prefijo": prefijo,
                "nombre_admin": datos.nombre_completo,
                "telefono": datos.telefono,
                "moneda": datos.moneda,
                "tarifa": datos.tarifa_hora_default,
                "impuesto": datos.impuesto_pct,
            },
        )
    except DBAPIError as exc:
        # Solo llega aquí si dos peticiones de la misma cuenta se cruzan (un
        # doble clic): la función serializa las altas y la segunda encuentra el
        # perfil que acaba de crear la primera.
        if extraer_sqlstate(exc) == "23505":
            raise ErrorConflicto("Tu cuenta ya pertenece a una organización.") from exc
        raise

    return await estado_cuenta(sesion, cuenta)


async def solicitar(
    sesion: AsyncSession, cuenta: CuentaAutenticada, datos: SolicitudNueva
) -> EstadoCuenta:
    """Deja la petición para que el equipo de Mechanified cree la organización.

    El correo, el estado y la organización los pone la base (ver el trigger
    `mch_solicitudes_organizacion_guard`): aquí solo se escribe lo que cuenta
    quien la pide.
    """
    await _exigir_sin_organizacion(sesion)

    anterior = await _ultima_solicitud(sesion)
    if anterior is not None and anterior.estado is EstadoSolicitud.PENDIENTE:
        raise ErrorConflicto(
            "Ya tienes una solicitud pendiente. El equipo de Mechanified te escribirá al "
            "correo de tu cuenta.",
            {"solicitud_id": str(anterior.id)},
        )

    sesion.add(
        SolicitudOrganizacion(
            cuenta_id=cuenta.id,
            nombre_contacto=datos.nombre_contacto,
            nombre_organizacion=datos.nombre_organizacion,
            telefono=datos.telefono,
            sedes=datos.sedes,
            mensaje=datos.mensaje,
        )
    )
    await sesion.flush()
    return await estado_cuenta(sesion, cuenta)
