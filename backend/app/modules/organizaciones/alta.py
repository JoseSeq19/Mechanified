"""Atención de las solicitudes de organización, del lado del equipo.

Quien prefiere no crear su organización por su cuenta deja una solicitud desde
el sitio. El equipo de Mechanified la atiende con `python -m app.solicitudes`,
que llega aquí.

Atenderla es crear la organización, su primera sede y el perfil de
administrador **para la cuenta que la pidió**: esa persona ya tiene cuenta (se
registró en el sitio para poder pedirlo), así que no hay contraseña temporal que
entregar, a diferencia del alta de `talleres/alta.py`. Entra con la suya.

Va con la sesión de servicio porque no hay sesión de usuario: quien ejecuta esto
es el equipo, desde la línea de comandos donde ya están las credenciales. Llama
al mismo núcleo que el alta por cuenta propia, `mch_crear_organizacion()`.
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Text, cast, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import sesion_servicio
from app.core.exceptions import ErrorConflicto, ErrorNoEncontrado
from app.modules.organizaciones.models import EstadoSolicitud, SolicitudOrganizacion
from app.modules.organizaciones.service import identificadores


@dataclass(frozen=True, slots=True)
class SolicitudAtendida:
    organizacion_id: UUID
    taller_id: UUID
    organizacion_nombre: str
    taller_nombre: str
    email: str


async def pendientes() -> list[SolicitudOrganizacion]:
    """Las que esperan al equipo, las más antiguas primero."""
    async with sesion_servicio() as sesion:
        filas = await sesion.scalars(
            select(SolicitudOrganizacion)
            .where(SolicitudOrganizacion.estado == EstadoSolicitud.PENDIENTE)
            .order_by(SolicitudOrganizacion.creado_en)
        )
        return list(filas)


async def _buscar(sesion: AsyncSession, referencia: str) -> SolicitudOrganizacion:
    """Por id completo o por sus primeros caracteres, que es como se listan."""
    referencia = referencia.strip().lower()
    filas = list(
        await sesion.scalars(
            select(SolicitudOrganizacion)
            .where(cast(SolicitudOrganizacion.id, Text).like(f"{referencia}%"))
            .with_for_update()
        )
    )
    if not filas:
        raise ErrorNoEncontrado(f"No hay ninguna solicitud que empiece por {referencia!r}.")
    if len(filas) > 1:
        raise ErrorConflicto(f"Hay {len(filas)} solicitudes que empiezan por {referencia!r}.")
    return filas[0]


async def atender(
    referencia: str,
    *,
    sede: str | None = None,
    moneda: str = "USD",
    tarifa: Decimal = Decimal(0),
    impuesto: Decimal = Decimal(0),
) -> SolicitudAtendida:
    """Crea la organización pedida y deja a quien la pidió como administrador."""
    async with sesion_servicio() as sesion:
        solicitud = await _buscar(sesion, referencia)
        if solicitud.estado is not EstadoSolicitud.PENDIENTE:
            raise ErrorConflicto(f"Esa solicitud ya está {solicitud.estado.value}.")

        nombre_sede = (sede or solicitud.nombre_organizacion).strip()
        slug_organizacion, slug_taller, prefijo = identificadores(
            solicitud.nombre_organizacion, nombre_sede
        )

        fila = (
            await sesion.execute(
                text(
                    "select * from public.mch_crear_organizacion("
                    " :cuenta, :nombre, :sede, :slug_organizacion, :slug_taller,"
                    " :prefijo, :nombre_admin, :telefono, :moneda, :tarifa, :impuesto)"
                ),
                {
                    "cuenta": solicitud.cuenta_id,
                    "nombre": solicitud.nombre_organizacion,
                    "sede": nombre_sede,
                    "slug_organizacion": slug_organizacion,
                    "slug_taller": slug_taller,
                    "prefijo": prefijo,
                    "nombre_admin": solicitud.nombre_contacto,
                    "telefono": solicitud.telefono,
                    "moneda": moneda.strip().upper(),
                    "tarifa": tarifa,
                    "impuesto": impuesto,
                },
            )
        ).one()

        # La función ya la marca como atendida; se recarga para devolverlo así.
        await sesion.refresh(solicitud)
        return SolicitudAtendida(
            organizacion_id=fila.organizacion_id,
            taller_id=fila.taller_id,
            organizacion_nombre=solicitud.nombre_organizacion,
            taller_nombre=nombre_sede,
            email=solicitud.email,
        )


async def descartar(referencia: str) -> SolicitudOrganizacion:
    """La deja cerrada sin crear nada: la persona puede volver a pedirlo."""
    async with sesion_servicio() as sesion:
        solicitud = await _buscar(sesion, referencia)
        if solicitud.estado is not EstadoSolicitud.PENDIENTE:
            raise ErrorConflicto(f"Esa solicitud ya está {solicitud.estado.value}.")
        await sesion.execute(
            text(
                "update public.solicitudes_organizacion"
                "   set estado = 'descartada', atendida_en = now()"
                " where id = :id"
            ),
            {"id": solicitud.id},
        )
        await sesion.refresh(solicitud)
        return solicitud
