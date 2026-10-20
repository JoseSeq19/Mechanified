"""Solicitudes de organización, desde la línea de comandos del equipo.

    python -m app.solicitudes                       las pendientes
    python -m app.solicitudes atender 3f9a1c2e      crea la organización pedida
    python -m app.solicitudes atender 3f9a1c2e --sede "Taller Centro" --moneda VES
    python -m app.solicitudes descartar 3f9a1c2e

Basta con los primeros caracteres del id, que son los que muestra el listado.

Atender una solicitud deja a quien la pidió como administrador de la
organización nueva. No hay contraseña que entregarle: ya tiene cuenta, la que
usó para pedirlo, y entra con ella en Mechanified. Lo que sí hay que hacer es
avisarle; este comando no escribe a nadie (ver la nota del README).

Necesita `MCH_DATABASE_URL`, como `python -m app.alta_taller`.
"""

import argparse
import asyncio
import logging
import sys
from decimal import Decimal

from app.core.exceptions import ErrorDominio
from app.modules.organizaciones import alta


def _argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    analizador = argparse.ArgumentParser(
        prog="python -m app.solicitudes",
        description="Lista y atiende las solicitudes de organización.",
    )
    sub = analizador.add_subparsers(dest="accion")

    atender = sub.add_parser("atender", help="Crea la organización pedida")
    atender.add_argument("id", help="Id de la solicitud, o sus primeros caracteres")
    atender.add_argument(
        "--sede", help="Nombre de la primera sede (por omisión, el de la organización)"
    )
    atender.add_argument("--moneda", default="USD", help="Código ISO 4217 (por omisión: USD)")
    atender.add_argument("--tarifa", default="0", help="Tarifa por hora de mano de obra")
    atender.add_argument("--impuesto", default="0", help="Porcentaje de impuesto")

    descartar = sub.add_parser("descartar", help="La cierra sin crear nada")
    descartar.add_argument("id", help="Id de la solicitud, o sus primeros caracteres")

    return analizador.parse_args(argv)


async def _listar() -> int:
    solicitudes = await alta.pendientes()
    if not solicitudes:
        print("No hay solicitudes pendientes.")
        return 0

    print()
    for s in solicitudes:
        sedes = f" · {s.sedes} sede{'s' if s.sedes != 1 else ''}" if s.sedes else ""
        print(f"  {str(s.id)[:8]}  {s.nombre_organizacion}{sedes}")
        print(f"            {s.nombre_contacto} <{s.email}>", end="")
        print(f" · {s.telefono}" if s.telefono else "")
        print(f"            desde el {s.creado_en.astimezone():%d/%m/%Y %H:%M}")
        if s.mensaje:
            print(f"            «{s.mensaje}»")
        print()
    return 0


async def principal(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)-8s %(message)s")

    try:
        if args.accion == "atender":
            hecha = await alta.atender(
                args.id,
                sede=args.sede,
                moneda=args.moneda,
                tarifa=Decimal(args.tarifa),
                impuesto=Decimal(args.impuesto),
            )
            print()
            print(f"  Organización creada: {hecha.organizacion_nombre}")
            print(f"  Primera sede:        {hecha.taller_nombre}")
            print(f"  Administración:      {hecha.email}")
            print()
            print("  Ya puede entrar en Mechanified con su cuenta. Avísale: este comando")
            print("  no le escribe.")
            print()
            return 0

        if args.accion == "descartar":
            s = await alta.descartar(args.id)
            print(f"Descartada la solicitud de {s.nombre_organizacion} ({s.email}).")
            return 0

        return await _listar()
    except ErrorDominio as exc:
        print(exc.mensaje, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
