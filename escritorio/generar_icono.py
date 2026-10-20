"""Arma el icono de Mechanified.exe a partir del emblema del logo.

    python escritorio/generar_icono.py

Escribe `escritorio/mechanified.ico` con el emblema que usan el sitio y la
aplicación (`web/src/assets/mechanified-emblema.webp`, ya sin fondo). Se
versiona el .ico hecho; esto queda para poder rehacerlo si cambia el logo.

Necesita Pillow (`pip install pillow`). Es una herramienta de quien desarrolla:
el cliente de escritorio en sí sigue sin más dependencia que la biblioteca
estándar, y el .exe no lleva este archivo.
"""

from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
EMBLEMA = RAIZ / "web" / "src" / "assets" / "mechanified-emblema.webp"
TAMANOS = (16, 24, 32, 48, 64, 128, 256)


def principal() -> None:
    destino = Path(__file__).with_name("mechanified.ico")
    emblema = Image.open(EMBLEMA).convert("RGBA")
    emblema.save(destino, format="ICO", sizes=[(t, t) for t in TAMANOS])
    print(f"Icono escrito en {destino} ({destino.stat().st_size} bytes)")


if __name__ == "__main__":
    principal()
