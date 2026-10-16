"""Alta de un taller nuevo, como herramienta de línea de comandos.

    python -m app.alta_taller --nombre "Delta Motors" \
        --admin-correo marisol@deltamotors.test --admin-nombre "Marisol Peñaranda"

Es lo que arranca un despliegue: deja creado el taller, la cuenta de su primer
administrador y su perfil, e imprime la contraseña temporal **una sola vez**.
A partir de ahí todo lo demás se hace desde la aplicación, incluido dar de alta
al resto de la gente.

Necesita `MCH_SUPABASE_SERVICE_ROLE_KEY` y `MCH_DATABASE_URL`, por las mismas
razones por las que esto no es un endpoint: ver el docstring de
`app/modules/talleres/alta.py`.
"""

import argparse
import asyncio
import logging
import sys
from decimal import Decimal

from pydantic import ValidationError

from app.core.exceptions import ErrorDominio
from app.modules.talleres.alta import TallerCreado, crear_taller
from app.modules.talleres.schemas import TallerAlta


def _argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    analizador = argparse.ArgumentParser(
        prog="python -m app.alta_taller",
        description="Crea un taller con su primer administrador.",
        epilog=(
            "El identificador (--slug) y el prefijo de folio (--prefijo) se "
            "derivan del nombre si no se indican."
        ),
    )

    obligatorios = analizador.add_argument_group("obligatorios")
    obligatorios.add_argument("--nombre", required=True, help="Nombre del taller")
    obligatorios.add_argument(
        "--admin-correo", required=True, help="Correo con el que entrará el administrador"
    )
    obligatorios.add_argument(
        "--admin-nombre", required=True, help="Nombre completo del administrador"
    )

    identidad = analizador.add_argument_group("identidad del taller")
    identidad.add_argument("--slug", help="Identificador global, en minúsculas y con guiones")
    identidad.add_argument("--rif", help="Identificación fiscal")
    identidad.add_argument("--telefono", help="Lo ve el cliente en el presupuesto")
    identidad.add_argument("--correo", help="Correo de contacto del taller")
    identidad.add_argument("--direccion")

    operacion = analizador.add_argument_group("configuración inicial")
    operacion.add_argument("--moneda", default="USD", help="Código ISO 4217 (por omisión: USD)")
    operacion.add_argument("--tarifa", default="0", help="Tarifa por hora de mano de obra")
    operacion.add_argument("--impuesto", default="0", help="Porcentaje de impuesto")
    operacion.add_argument("--prefijo", help="Prefijo del folio, de 2 a 6 caracteres")
    operacion.add_argument(
        "--zona-horaria", default="America/Caracas", help="Por omisión: America/Caracas"
    )
    operacion.add_argument(
        "--dias-validez", type=int, default=15, help="Validez del presupuesto, en días"
    )

    return analizador.parse_args(argv)


def _datos(args: argparse.Namespace) -> TallerAlta:
    return TallerAlta(
        nombre=args.nombre,
        slug=args.slug,
        admin_email=args.admin_correo,
        admin_nombre=args.admin_nombre,
        identificacion_fiscal=args.rif,
        telefono=args.telefono,
        email=args.correo,
        direccion=args.direccion,
        zona_horaria=args.zona_horaria,
        moneda=args.moneda,
        tarifa_hora_default=Decimal(args.tarifa),
        impuesto_pct=Decimal(args.impuesto),
        prefijo_orden=args.prefijo,
        dias_validez_presupuesto=args.dias_validez,
    )


def _imprimir(creado: TallerCreado, nombre: str) -> None:
    print()
    print(f"  Taller creado: {nombre}")
    print(f"  Identificador: {creado.slug}")
    print(f"  Prefijo de folio: {creado.prefijo_orden}")
    print()
    print("  Entra en la web con:")
    print(f"      correo:     {creado.admin_email}")
    print(f"      contraseña: {creado.clave_temporal}")
    print()
    print("  Esa contraseña no se vuelve a mostrar y conviene cambiarla al entrar.")
    print("  El resto de la configuración se ajusta en la aplicación, en Configuración.")
    print()


async def principal(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")

    try:
        datos = _datos(args)
    except ValidationError as exc:
        # Un error de Pydantic en bruto no se le pone delante a nadie: se
        # resumen los campos que no pasaron.
        print("No se puede dar el alta con esos datos:", file=sys.stderr)
        for fallo in exc.errors():
            campo = ".".join(str(p) for p in fallo["loc"]) or "(datos)"
            print(f"  - {campo}: {fallo['msg']}", file=sys.stderr)
        return 2

    try:
        creado = await crear_taller(datos)
    except ErrorDominio as exc:
        print(f"No se pudo dar el alta: {exc.mensaje}", file=sys.stderr)
        return 1

    _imprimir(creado, datos.nombre)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
