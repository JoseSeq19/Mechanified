"""Mechanified para Windows: la aplicación, servida desde el propio equipo.

    Mechanified.exe                     abre Mechanified en el navegador
    Mechanified.exe --sin-navegador     sin abrirlo
    Mechanified.exe --api URL           contra otra API (soporte y pruebas)

Lleva dentro la aplicación web ya compilada y nada más. Ni la API, ni la base de
datos, ni una sola credencial: es lo que lo hace repartible. La primera versión
del ejecutable llevaba la API dentro, y con ella la cadena de conexión a
Postgres y la llave de servicio, que se saltan RLS; repartirla a un cliente era
darle las llaves de los datos de todos los demás.

Lo que hace es lo mismo que el proxy de Vite en desarrollo:

  - sirve la aplicación en http://127.0.0.1:5180, solo para este equipo;
  - reenvía lo que empieza por `/api` a la API central de Mechanified, con el
    token de quien tiene la sesión abierta, sin guardarlo ni mirarlo.

Así la aplicación se compila igual que siempre (`VITE_API_URL=/api`) y el
navegador nunca hace peticiones a otro origen: no hay CORS que configurar para
cada equipo.

El puerto es fijo a propósito: la sesión de Supabase vive en el
almacenamiento del navegador, que va por origen. Con un puerto distinto en cada
arranque, habría que volver a entrar cada vez.

Solo usa la biblioteca estándar de Python. Se empaqueta con
`npm run empaquetar` desde la raíz del repositorio (ver scripts/empaquetar.mjs).
"""

import argparse
import contextlib
import http.client
import http.server
import json
import os
import queue
import ssl
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

PRODUCTO = "Mechanified"
PUERTO = 5180
PREFIJO_API = "/api"
#: Ruta con la que una copia ya abierta se reconoce. Sirve para que abrir el
#: ejecutable dos veces abra el navegador en vez de chocar con el puerto.
RUTA_SENAL = "/__mechanified"

#: Lo único que se reenvía a la API. Las cookies, el `Origin` o el `Referer`
#: son de este equipo y no tienen nada que hacer en el servidor.
ENCABEZADOS_REENVIADOS = {
    "accept",
    "accept-encoding",
    "accept-language",
    "authorization",
    "content-type",
    "if-modified-since",
    "if-none-match",
}

#: Encabezados de la respuesta que no se devuelven tal cual: los de salto, que
#: valen solo para la conexión con la API; el largo, que se recalcula; y la
#: fecha y el servidor, que este servidor ya pone y saldrían repetidos.
ENCABEZADOS_DE_SALTO = {
    "connection",
    "content-length",
    "date",
    "keep-alive",
    "server",
    "proxy-authenticate",
    "proxy-authorization",
    "strict-transport-security",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

#: Windows resuelve los tipos MIME con el registro, y en muchos equipos dice que
#: un .js es `text/plain`. Con eso el navegador se niega a cargar la aplicación,
#: así que los tipos que importan van fijos.
TIPOS = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".webp": "image/webp",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
}

TIEMPO_ESPERA_API = 30


def _recurso(nombre: str) -> Path:
    """Lo empaquetado: dentro del ejecutable, o junto a este archivo."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / nombre  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / nombre


def _configuracion() -> dict[str, str]:
    """La que se fijó al empaquetar (`configuracion.json`), si la hay."""
    archivo = _recurso("configuracion.json")
    if archivo.is_file():
        return json.loads(archivo.read_text(encoding="utf-8"))
    return {}


def _carpeta_web() -> Path:
    if getattr(sys, "frozen", False):
        return _recurso("web")
    return Path(__file__).resolve().parents[1] / "web" / "dist"


# -----------------------------------------------------------------------------
# Conexiones con la API
# -----------------------------------------------------------------------------


class ConexionesApi:
    """Conexiones reutilizables con la API central.

    Abrir una conexión TLS por petición añade un apretón de manos a cada lista
    que pinta la aplicación. Aquí se guardan las que quedan libres y se
    reutilizan. Una conexión guardada puede haberla cerrado el servidor
    mientras esperaba: si falla así una lectura (GET, HEAD), se repite con una
    nueva; una escritura no se repite nunca, porque no se sabe si llegó.
    """

    def __init__(self, url: str, maximo: int = 6) -> None:
        partes = urllib.parse.urlsplit(url)
        if partes.scheme not in {"http", "https"} or not partes.hostname:
            raise ValueError(f"La dirección de la API no es válida: {url!r}")
        self.url = url
        self.esquema = partes.scheme
        self.anfitrion = partes.hostname
        self.puerto = partes.port
        self.base = partes.path.rstrip("/")
        self.cabecera_host = partes.netloc
        #: Esquema, anfitrión y ruta base: lo que hay que quitar de una
        #: redirección para que siga pasando por aquí.
        self.origen = f"{partes.scheme}://{partes.netloc}{self.base}"
        self._libres: queue.LifoQueue[http.client.HTTPConnection] = queue.LifoQueue(maximo)
        self._tls = ssl.create_default_context() if self.esquema == "https" else None

    def _nueva(self) -> http.client.HTTPConnection:
        if self._tls is not None:
            return http.client.HTTPSConnection(
                self.anfitrion, self.puerto, timeout=TIEMPO_ESPERA_API, context=self._tls
            )
        return http.client.HTTPConnection(self.anfitrion, self.puerto, timeout=TIEMPO_ESPERA_API)

    def _devolver(self, conexion: http.client.HTTPConnection) -> None:
        try:
            self._libres.put_nowait(conexion)
        except queue.Full:
            conexion.close()

    def pedir(
        self, metodo: str, ruta: str, cuerpo: bytes | None, encabezados: dict[str, str]
    ) -> tuple[int, str, list[tuple[str, str]], bytes]:
        encabezados = {**encabezados, "Host": self.cabecera_host}
        destino = self.base + ruta
        repetible = metodo in {"GET", "HEAD", "OPTIONS"}

        try:
            conexion, reutilizada = self._libres.get_nowait(), True
        except queue.Empty:
            conexion, reutilizada = self._nueva(), False

        for intento in (1, 2):
            try:
                conexion.request(metodo, destino, body=cuerpo, headers=encabezados)
                respuesta = conexion.getresponse()
                datos = respuesta.read()
            except (OSError, http.client.HTTPException):
                conexion.close()
                if intento == 1 and reutilizada and repetible:
                    conexion, reutilizada = self._nueva(), False
                    continue
                raise
            if respuesta.will_close:
                conexion.close()
            else:
                self._devolver(conexion)
            return respuesta.status, respuesta.reason, respuesta.getheaders(), datos
        raise AssertionError("inalcanzable")


# -----------------------------------------------------------------------------
# Servidor local
# -----------------------------------------------------------------------------


class Manejador(http.server.SimpleHTTPRequestHandler):
    server_version = PRODUCTO
    sys_version = ""
    protocol_version = "HTTP/1.1"
    extensions_map = TIPOS
    servidor: "ServidorMechanified"

    def __init__(self, *args: object, **kwargs: object) -> None:
        servidor = args[2]
        assert isinstance(servidor, ServidorMechanified)
        self.servidor = servidor
        super().__init__(*args, directory=str(servidor.web), **kwargs)  # type: ignore[arg-type]

    # --- Despacho --------------------------------------------------------

    def _anfitrion_valido(self) -> bool:
        """Solo se atiende a quien llama a esta dirección por su nombre.

        Una página cualquiera de internet puede hacer que su dominio apunte a
        127.0.0.1 y llamar desde el navegador a este servidor como si fuera
        suyo. Comprobar el `Host` deja fuera ese truco.
        """
        anfitrion = (self.headers.get("Host") or "").lower()
        return anfitrion in self.servidor.anfitriones

    def _despachar(self) -> None:
        # Con HTTP/1.1 el mismo manejador atiende varias peticiones seguidas de
        # una conexión: lo que marca la anterior no puede quedarse puesto.
        self._es_estatico = True
        if not self._anfitrion_valido():
            self._json(421, {"error": {"codigo": "anfitrion", "mensaje": "Anfitrión no válido."}})
            return

        ruta = urllib.parse.urlsplit(self.path).path
        if ruta == RUTA_SENAL:
            self._json(200, {"producto": PRODUCTO, "api": self.servidor.api.url})
            return
        if ruta == PREFIJO_API or ruta.startswith(PREFIJO_API + "/"):
            self._reenviar()
            return
        if self.command not in {"GET", "HEAD"}:
            self._json(405, {"error": {"codigo": "metodo", "mensaje": "Método no permitido."}})
            return
        self._web(ruta)

    def do_GET(self) -> None:
        self._despachar()

    def do_HEAD(self) -> None:
        self._despachar()

    def do_POST(self) -> None:
        self._despachar()

    def do_PUT(self) -> None:
        self._despachar()

    def do_PATCH(self) -> None:
        self._despachar()

    def do_DELETE(self) -> None:
        self._despachar()

    def do_OPTIONS(self) -> None:
        self._despachar()

    # --- La aplicación ---------------------------------------------------

    def _web(self, ruta: str) -> None:
        """Un archivo de la aplicación, o index.html para sus rutas.

        La aplicación enruta en el navegador: `/ordenes/123` no existe en
        disco, y sin este repliegue recargar la página daría 404. Lo que sí
        lleva extensión y no existe (`/assets/x.js`) es un 404 de verdad, para
        que un archivo que falta no se disfrace de página.
        """
        fisica = Path(self.translate_path(ruta))
        ultimo = ruta.rsplit("/", 1)[-1]
        if not fisica.exists() and "." not in ultimo:
            self.path = "/index.html"
        if self.command == "HEAD":
            super().do_HEAD()
        else:
            super().do_GET()

    def end_headers(self) -> None:
        # Los recursos llevan su huella en el nombre y no cambian nunca; el
        # index.html, en cambio, tiene que releerse para ver la versión nueva.
        if getattr(self, "_es_estatico", True):
            inmutable = urllib.parse.urlsplit(self.path).path.startswith("/assets/")
            self.send_header(
                "Cache-Control",
                "public, max-age=31536000, immutable" if inmutable else "no-cache",
            )
            self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    # --- La API ----------------------------------------------------------

    def _reenviar(self) -> None:
        self._es_estatico = False
        largo = int(self.headers.get("Content-Length") or 0)
        cuerpo = self.rfile.read(largo) if largo > 0 else None
        encabezados = {k: v for k, v in self.headers.items() if k.lower() in ENCABEZADOS_REENVIADOS}
        ruta = self.path[len(PREFIJO_API) :] or "/"
        if not ruta.startswith("/"):
            ruta = "/" + ruta

        try:
            estado, motivo, recibidos, datos = self.servidor.api.pedir(
                self.command, ruta, cuerpo, encabezados
            )
        except (OSError, http.client.HTTPException) as exc:
            self.servidor.avisar(f"No se pudo contactar con la API ({exc.__class__.__name__}).")
            self._json(
                502,
                {
                    "error": {
                        "codigo": "sin_servidor",
                        "mensaje": (
                            "No se pudo contactar con el servidor de Mechanified. Revisa tu "
                            "conexión a internet y vuelve a intentarlo."
                        ),
                    }
                },
            )
            return

        self.send_response(estado, motivo)
        for clave, valor in recibidos:
            if clave.lower() in ENCABEZADOS_DE_SALTO:
                continue
            # Una redirección de la API apunta a su propia dirección; seguida
            # tal cual, el navegador saldría de este origen y chocaría con CORS.
            if clave.lower() == "location" and valor.startswith(self.servidor.api.origen):
                valor = PREFIJO_API + valor[len(self.servidor.api.origen) :]
            self.send_header(clave, valor)
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(datos)

    def _json(self, estado: int, cuerpo: dict[str, object]) -> None:
        self._es_estatico = False
        datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(datos)

    def log_message(self, format: str, *args: object) -> None:
        # Una línea por petición no le dice nada a quien usa la aplicación. Los
        # fallos que importan se avisan aparte (ver `avisar`).
        return


class ServidorMechanified(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, puerto: int, web: Path, api: ConexionesApi) -> None:
        self.web = web
        self.api = api
        self.anfitriones = {f"127.0.0.1:{puerto}", f"localhost:{puerto}"}
        self._avisos = threading.Lock()
        super().__init__(("127.0.0.1", puerto), Manejador)

    def avisar(self, mensaje: str) -> None:
        with self._avisos:
            print(f"  ! {mensaje}", file=sys.stderr, flush=True)


# -----------------------------------------------------------------------------
# Arranque
# -----------------------------------------------------------------------------


def _ya_abierto(puerto: int) -> bool:
    """Si en el puerto hay ya otra copia de Mechanified (y no otro programa)."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}{RUTA_SENAL}", timeout=2) as r:
            return json.loads(r.read()).get("producto") == PRODUCTO
    except (OSError, ValueError):
        return False


def _titulo_de_ventana(titulo: str) -> None:
    if sys.platform == "win32":
        with contextlib.suppress(Exception):
            import ctypes

            ctypes.windll.kernel32.SetConsoleTitleW(titulo)  # type: ignore[attr-defined]


def _argumentos(argv: list[str]) -> argparse.Namespace:
    analizador = argparse.ArgumentParser(prog=PRODUCTO, description=f"{PRODUCTO} para Windows.")
    analizador.add_argument("--sin-navegador", action="store_true", help="No abrir el navegador")
    analizador.add_argument("--api", help="Dirección de la API (por omisión, la del paquete)")
    analizador.add_argument("--puerto", type=int, default=PUERTO, help=argparse.SUPPRESS)
    return analizador.parse_args(argv)


def principal(argv: list[str]) -> int:
    args = _argumentos(argv)
    _titulo_de_ventana(PRODUCTO)

    web = _carpeta_web()
    if not (web / "index.html").is_file():
        print(f"No encuentro la aplicación compilada en {web}.", file=sys.stderr)
        return 1

    url_api = args.api or os.environ.get("MCH_API_URL") or _configuracion().get("api")
    if not url_api:
        print("Este paquete no sabe a qué API conectarse. Vuelve a empaquetarlo.", file=sys.stderr)
        return 1

    url = f"http://127.0.0.1:{args.puerto}"
    try:
        servidor = ServidorMechanified(args.puerto, web, ConexionesApi(url_api))
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    except OSError:
        if _ya_abierto(args.puerto):
            print(f"{PRODUCTO} ya está abierto. Lo abro en el navegador.")
            if not args.sin_navegador:
                webbrowser.open(url)
            return 0
        print(
            f"El puerto {args.puerto} lo está usando otro programa, y {PRODUCTO} lo necesita.",
            file=sys.stderr,
        )
        return 1

    print(f"\n  {PRODUCTO}\n\n    Abierto en {url}\n")
    print("  Deja esta ventana abierta mientras trabajas.")
    print("  Al cerrarla, Mechanified se cierra.\n")

    if not args.sin_navegador:
        webbrowser.open(url)

    with contextlib.suppress(KeyboardInterrupt):
        servidor.serve_forever()
    servidor.server_close()
    return 0


if __name__ == "__main__":
    codigo = principal(sys.argv[1:])
    # Abierto con doble clic, la ventana se cierra al terminar y el error se
    # pierde antes de poder leerlo.
    if codigo and getattr(sys, "frozen", False) and sys.stdin and sys.stdin.isatty():
        with contextlib.suppress(EOFError):
            input("\nPulsa Enter para cerrar.")
    raise SystemExit(codigo)
