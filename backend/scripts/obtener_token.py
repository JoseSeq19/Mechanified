"""Imprime un token de acceso para probar la API a mano.

El archivo NO puede llamarse token.py: al ejecutarlo, su carpeta entra primero
en sys.path y taparia el modulo `token` de la biblioteca estandar, que `logging`
importa de forma indirecta. El interprete revienta antes de llegar a main().

Mechanified no tiene endpoint de login propio: la autenticación la hace
Supabase Auth directamente desde la web o el móvil, y el backend solo verifica
el token que le llega. Para probar con /docs o con curl hace falta pedirle ese
token a Supabase, y eso es lo único que hace este script.

    python scripts/obtener_token.py
    python scripts/obtener_token.py otro@correo.test 'su-contraseña'

Para pegarlo en /docs: copiar la salida, pulsar "Authorize" arriba a la derecha
y pegar el token (sin la palabra "Bearer").
"""

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import obtener_configuracion

CORREO_POR_OMISION = "admin@mechanfied"


def main() -> int:
    cfg = obtener_configuracion()

    if not cfg.supabase_anon_key:
        print("Falta MCH_SUPABASE_ANON_KEY en el .env", file=sys.stderr)
        return 1

    correo = sys.argv[1] if len(sys.argv) > 1 else CORREO_POR_OMISION
    clave = sys.argv[2] if len(sys.argv) > 2 else None

    if clave is None:
        print("Uso: python scripts/obtener_token.py [correo] <contraseña>", file=sys.stderr)
        print(f"     (correo por omisión: {CORREO_POR_OMISION})", file=sys.stderr)
        return 1

    respuesta = httpx.post(
        f"{cfg.supabase_url.rstrip('/')}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": cfg.supabase_anon_key},
        json={"email": correo, "password": clave},
        timeout=20,
    )

    if respuesta.status_code != 200:
        print(f"Login rechazado ({respuesta.status_code}): {respuesta.text}", file=sys.stderr)
        return 1

    datos = respuesta.json()
    token = datos["access_token"]

    # Se decodifica sin verificar firma: aquí solo interesa mostrar qué claims
    # trae, para detectar de un vistazo si el hook de Auth está apagado.
    import jwt

    claims = jwt.decode(token, options={"verify_signature": False})

    print(token)
    print(f"\n  usuario   : {claims.get('email', correo)}", file=sys.stderr)
    print(f"  taller_id : {claims.get('taller_id', '(AUSENTE)')}", file=sys.stderr)
    print(f"  rol       : {claims.get('rol', '(AUSENTE)')}", file=sys.stderr)
    if not claims.get("taller_id"):
        print(
            "\n  El token no trae claims de taller. Revisa que el hook de Auth "
            "(mch_hook_access_token) esté activo en el proyecto.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
