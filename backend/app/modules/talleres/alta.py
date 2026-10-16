"""Alta de un taller nuevo con su primer administrador.

Es el único arranque posible del sistema: sin un taller no hay `taller_id` que
poner en un token, y sin un administrador no hay quien dé de alta a nadie. El
huevo y la gallina se rompen aquí, desde fuera de la API.

Por qué esto no es un endpoint: `talleres` no tiene política de INSERT, así que
la fila solo la puede escribir el rol de servicio. Exponerlo por HTTP sería
poner esa llave detrás de una puerta, y aquí no hace falta ninguna puerta: este
es un sistema interno y abrir una sede nueva es una decisión del grupo, no algo
que nadie vaya a hacer solo. Vive en la línea de comandos de quien opera el
despliegue, que es quien ya tiene las credenciales.

El alta son tres escrituras en dos sistemas distintos, y pueden fallar a medias:

  1. la fila del taller, en Postgres;
  2. la cuenta del administrador, en Supabase Auth;
  3. su perfil, en Postgres, que es lo que ata 1 con 2.

El orden es ese y la compensación va al revés: si el perfil falla se borra la
cuenta y el taller, porque un taller sin administrador no se puede terminar de
dar de alta por ninguna otra vía, y una cuenta sin perfil solo sirve para
chocar contra un "no autorizado" y para bloquear ese correo en un segundo
intento.
"""

import logging
import unicodedata
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from app.core.database import sesion_servicio
from app.core.exceptions import ErrorConflicto
from app.core.roles import Rol
from app.modules.talleres.schemas import TallerAlta
from app.modules.usuarios.cuentas import AdministradorDeCuentas, CuentasSupabase, generar_clave

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TallerCreado:
    taller_id: UUID
    slug: str
    prefijo_orden: str
    admin_id: UUID
    admin_email: str
    #: Se muestra una sola vez. No se guarda en ninguna parte en claro.
    clave_temporal: str


def derivar_slug(nombre: str) -> str:
    """Identificador global a partir del nombre del taller.

    "Talleres Peña & Hijos, C.A." -> "talleres-pena-hijos-c-a"

    Tiene que cumplir `talleres_slug_formato`: empieza y acaba en letra o
    número, y entre 3 y 50 caracteres. Si del nombre no sale nada que cumpla
    —un taller llamado "A1", por ejemplo— quien da el alta lo indica a mano, que
    es mejor que inventar un identificador que luego nadie reconoce.
    """
    sin_acentos = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()

    limpio: list[str] = []
    for caracter in sin_acentos.lower():
        limpio.append(caracter if caracter.isalnum() else "-")

    partes = [p for p in "".join(limpio).split("-") if p]
    slug = "-".join(partes)[:50].strip("-")

    if len(slug) < 3 or not slug[0].isalnum() or not slug[-1].isalnum():
        raise ErrorConflicto(
            f"Del nombre {nombre!r} no sale un identificador válido. Indícalo con --slug.",
            {"campo": "slug"},
        )
    return slug


def derivar_prefijo(nombre: str) -> str:
    """Prefijo del folio: los tres primeros caracteres útiles del nombre.

    "Delta Motors" -> "DEL". Es un punto de partida; se cambia después en
    Configuración, que es donde se ve el efecto sobre los folios nuevos.
    """
    sin_acentos = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    utiles = [c for c in sin_acentos.upper() if c.isalnum()]

    if len(utiles) < 2:
        raise ErrorConflicto(
            f"Del nombre {nombre!r} no salen dos caracteres para el folio. Indícalo con --prefijo.",
            {"campo": "prefijo_orden"},
        )
    return "".join(utiles[:3])


_INSERTAR_TALLER = """
    insert into public.talleres (
      nombre, slug, identificacion_fiscal, direccion, telefono, email,
      zona_horaria, moneda, tarifa_hora_default, impuesto_pct,
      prefijo_orden, dias_validez_presupuesto
    ) values (
      :nombre, :slug, :identificacion_fiscal, :direccion, :telefono, :email,
      :zona_horaria, :moneda, :tarifa, :impuesto,
      :prefijo, :dias
    )
    returning id
"""

_INSERTAR_PERFIL = """
    insert into public.perfiles (id, taller_id, nombre_completo, email, telefono, rol)
    values (:id, :taller_id, :nombre, :email, :telefono, :rol)
"""


async def _borrar_taller(taller_id: object) -> None:
    async with sesion_servicio() as sesion:
        await sesion.execute(text("delete from public.talleres where id = :id"), {"id": taller_id})


async def crear_taller(
    datos: TallerAlta, cuentas: AdministradorDeCuentas | None = None
) -> TallerCreado:
    """Crea el taller, la cuenta del primer administrador y su perfil."""
    cuentas = cuentas or CuentasSupabase()

    slug = datos.slug or derivar_slug(datos.nombre)
    prefijo = datos.prefijo_orden or derivar_prefijo(datos.nombre)
    correo = str(datos.admin_email).strip().lower()

    async with sesion_servicio() as sesion:
        existe = await sesion.scalar(
            text("select nombre from public.talleres where slug = :slug"), {"slug": slug}
        )
        if existe:
            raise ErrorConflicto(
                f"Ya hay un taller con el identificador {slug!r} ({existe}). Usa --slug.",
                {"campo": "slug"},
            )

        taller_id = (
            await sesion.execute(
                text(_INSERTAR_TALLER),
                {
                    "nombre": datos.nombre,
                    "slug": slug,
                    "identificacion_fiscal": datos.identificacion_fiscal,
                    "direccion": datos.direccion,
                    "telefono": datos.telefono,
                    "email": str(datos.email) if datos.email else None,
                    "zona_horaria": datos.zona_horaria,
                    "moneda": datos.moneda,
                    "tarifa": datos.tarifa_hora_default,
                    "impuesto": datos.impuesto_pct,
                    "prefijo": prefijo,
                    "dias": datos.dias_validez_presupuesto,
                },
            )
        ).scalar_one()

    clave = generar_clave()
    try:
        cuenta_id = await cuentas.crear(correo, clave)
    except Exception:
        # Un taller sin administrador no se puede terminar de dar de alta por
        # ninguna otra vía, y su slug quedaría ocupado para el segundo intento.
        _log.warning("Cuenta fallida para %s; se deshace el taller %s", correo, taller_id)
        await _borrar_taller(taller_id)
        raise

    try:
        async with sesion_servicio() as sesion:
            await sesion.execute(
                text(_INSERTAR_PERFIL),
                {
                    "id": cuenta_id,
                    "taller_id": taller_id,
                    "nombre": datos.admin_nombre,
                    "email": correo,
                    "telefono": datos.telefono,
                    "rol": Rol.ADMIN_TALLER.value,
                },
            )
    except Exception:
        _log.warning(
            "Perfil fallido; se deshacen la cuenta %s y el taller %s", cuenta_id, taller_id
        )
        await cuentas.borrar(cuenta_id)
        await _borrar_taller(taller_id)
        raise

    return TallerCreado(
        taller_id=UUID(str(taller_id)),
        slug=slug,
        prefijo_orden=prefijo,
        admin_id=cuenta_id,
        admin_email=correo,
        clave_temporal=clave,
    )
