"""Dibuja el icono de Mechanified.exe, sin dependencias.

    python escritorio/generar_icono.py

Escribe `escritorio/mechanified.ico` con la misma figura que el glifo de la
marca en la web (`web/public/favicon.svg`): una "M" blanca sobre un cuadrado
redondeado con el degradado petróleo de `web/src/styles/tokens.css`. Se
versiona el .ico ya hecho; esto queda para poder rehacerlo si cambia la marca.

Cada tamaño se dibuja por separado, con supermuestreo, en vez de reducir el
grande: a 16 px un reescalado deja la letra borrosa.
"""

import struct
import zlib
from pathlib import Path

#: --mch-petroleo-600 y --mch-petroleo-800
ARRIBA = (0x16, 0x7B, 0x83)
ABAJO = (0x0A, 0x40, 0x46)

#: La "M", en coordenadas de 0 a 1. Es la misma que la del favicon.
LETRA = [
    (0.24, 0.73), (0.24, 0.27), (0.36, 0.27), (0.50, 0.47), (0.64, 0.27),
    (0.76, 0.27), (0.76, 0.73), (0.64, 0.73), (0.64, 0.46), (0.50, 0.66),
    (0.36, 0.46), (0.36, 0.73),
]  # fmt: skip

RADIO = 0.22
TAMANOS = (16, 24, 32, 48, 64, 128, 256)


def _dentro_redondeado(x: float, y: float) -> bool:
    cx = min(max(x, RADIO), 1 - RADIO)
    cy = min(max(y, RADIO), 1 - RADIO)
    return (x - cx) ** 2 + (y - cy) ** 2 <= RADIO**2


def _dentro_letra(x: float, y: float) -> bool:
    dentro = False
    j = len(LETRA) - 1
    for i, (xi, yi) in enumerate(LETRA):
        xj, yj = LETRA[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


def _pixeles(tamano: int) -> bytes:
    muestras = 4 if tamano >= 64 else 6
    filas = bytearray()
    for py in range(tamano):
        filas.append(0)  # filtro PNG: ninguno
        for px in range(tamano):
            fondo = letra = 0
            for sy in range(muestras):
                for sx in range(muestras):
                    x = (px + (sx + 0.5) / muestras) / tamano
                    y = (py + (sy + 0.5) / muestras) / tamano
                    if _dentro_redondeado(x, y):
                        fondo += 1
                        if _dentro_letra(x, y):
                            letra += 1
            total = muestras * muestras
            # Degradado en diagonal, como el linear-gradient(145deg) del glifo.
            t = min(max(((px + 0.5) / tamano + (py + 0.5) / tamano) / 2, 0), 1)
            base = [round(a + (b - a) * t) for a, b in zip(ARRIBA, ABAJO, strict=True)]
            mezcla = letra / fondo if fondo else 0
            color = [round(c + (255 - c) * mezcla) for c in base]
            filas += bytes([*color, round(255 * fondo / total)])
    return bytes(filas)


def _png(tamano: int) -> bytes:
    def bloque(tipo: bytes, datos: bytes) -> bytes:
        crc = zlib.crc32(tipo + datos) & 0xFFFFFFFF
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", crc)

    cabecera = struct.pack(">IIBBBBB", tamano, tamano, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + bloque(b"IHDR", cabecera)
        + bloque(b"IDAT", zlib.compress(_pixeles(tamano), 9))
        + bloque(b"IEND", b"")
    )


def _ico(imagenes: list[tuple[int, bytes]]) -> bytes:
    salida = struct.pack("<HHH", 0, 1, len(imagenes))
    desplazamiento = 6 + 16 * len(imagenes)
    cuerpo = b""
    for tamano, png in imagenes:
        lado = 0 if tamano >= 256 else tamano
        salida += struct.pack("<BBBBHHII", lado, lado, 0, 0, 1, 32, len(png), desplazamiento)
        desplazamiento += len(png)
        cuerpo += png
    return salida + cuerpo


def principal() -> None:
    destino = Path(__file__).with_name("mechanified.ico")
    destino.write_bytes(_ico([(t, _png(t)) for t in TAMANOS]))
    print(f"Icono escrito en {destino} ({destino.stat().st_size} bytes)")


if __name__ == "__main__":
    principal()
