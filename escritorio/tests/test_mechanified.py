"""El servidor de Mechanified.exe, contra una API de mentira.

Lo que importa probar es lo que haría daño si fallara en silencio: que al
servidor remoto solo le llegue lo que debe (el token sí, las cookies del equipo
no), que la aplicación cargue aunque Windows diga que un .js es texto plano, y
que una página ajena no pueda usar este servidor por la puerta de atrás.

    pytest escritorio/tests
"""

import http.client
import http.server
import json
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mechanified

# -----------------------------------------------------------------------------
# Una API que devuelve lo que recibe
# -----------------------------------------------------------------------------


class ApiEco(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _responder(self) -> None:
        largo = int(self.headers.get("Content-Length") or 0)
        cuerpo = self.rfile.read(largo).decode() if largo else ""
        if self.path.startswith("/redirige"):
            self.send_response(307)
            self.send_header("Location", f"http://{self.headers['Host']}/destino")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        datos = json.dumps(
            {
                "metodo": self.command,
                "ruta": self.path,
                "cuerpo": cuerpo,
                "encabezados": {k.lower(): v for k, v in self.headers.items()},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    do_GET = do_POST = do_PATCH = do_DELETE = _responder  # noqa: N815

    def log_message(self, *_: object) -> None:
        return


def _en_hilo(servidor: http.server.HTTPServer) -> threading.Thread:
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    return hilo


@pytest.fixture
def api() -> Iterator[str]:
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ApiEco)
    _en_hilo(servidor)
    yield f"http://127.0.0.1:{servidor.server_address[1]}"
    servidor.shutdown()


@pytest.fixture
def web(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>Mechanified</title>")
    (tmp_path / "assets" / "app-1a2b.js").write_text("export const x = 1;")
    return tmp_path


@pytest.fixture
def local(api: str, web: Path) -> Iterator[int]:
    """Mechanified sirviendo `web` y reenviando a la API de mentira."""
    servidor = mechanified.ServidorMechanified(0, web, mechanified.ConexionesApi(api))
    puerto = servidor.server_address[1]
    # El puerto 0 lo asigna el sistema; el nombre válido se fija ya sabiéndolo.
    servidor.anfitriones = {f"127.0.0.1:{puerto}", f"localhost:{puerto}"}
    _en_hilo(servidor)
    yield puerto
    servidor.shutdown()
    servidor.server_close()


def _pedir(
    puerto: int,
    metodo: str,
    ruta: str,
    cuerpo: bytes | None = None,
    encabezados: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=10)
    conexion.request(metodo, ruta, body=cuerpo, headers=encabezados or {})
    respuesta = conexion.getresponse()
    datos = respuesta.read()
    conexion.close()
    return respuesta.status, {k.lower(): v for k, v in respuesta.getheaders()}, datos


# -----------------------------------------------------------------------------
# La aplicación
# -----------------------------------------------------------------------------


def test_sirve_la_aplicacion(local: int) -> None:
    estado, encabezados, datos = _pedir(local, "GET", "/")
    assert estado == 200
    assert encabezados["content-type"].startswith("text/html")
    assert encabezados["cache-control"] == "no-cache"
    assert b"Mechanified" in datos


def test_las_rutas_de_la_aplicacion_caen_en_index(local: int) -> None:
    """Recargar /ordenes/123 tiene que abrir la aplicación, no dar 404."""
    estado, _, datos = _pedir(local, "GET", "/ordenes/123")
    assert estado == 200
    assert b"<title>Mechanified</title>" in datos


def test_un_recurso_que_falta_es_un_404_de_verdad(local: int) -> None:
    estado, _, _ = _pedir(local, "GET", "/assets/no-existe.js")
    assert estado == 404


def test_el_javascript_sale_como_javascript(local: int) -> None:
    """Aunque el registro de Windows diga text/plain, que es lo que rompe los módulos."""
    estado, encabezados, _ = _pedir(local, "GET", "/assets/app-1a2b.js")
    assert estado == 200
    assert encabezados["content-type"].startswith("text/javascript")
    assert "immutable" in encabezados["cache-control"]


def test_otro_anfitrion_se_rechaza(local: int) -> None:
    """Una página que apunte su dominio a 127.0.0.1 no entra."""
    estado, _, _ = _pedir(local, "GET", "/", encabezados={"Host": f"malo.example:{local}"})
    assert estado == 421


def test_una_copia_abierta_se_reconoce(local: int) -> None:
    estado, _, datos = _pedir(local, "GET", mechanified.RUTA_SENAL)
    assert estado == 200
    assert json.loads(datos)["producto"] == "Mechanified"


# -----------------------------------------------------------------------------
# El reenvío a la API
# -----------------------------------------------------------------------------


def test_reenvia_a_la_api_sin_el_prefijo(local: int) -> None:
    estado, _, datos = _pedir(local, "GET", "/api/ordenes?pagina=2")
    eco = json.loads(datos)
    assert estado == 200
    assert eco["ruta"] == "/ordenes?pagina=2"


def test_pasa_el_token_y_no_lo_que_es_del_equipo(local: int, api: str) -> None:
    _, _, datos = _pedir(
        local,
        "POST",
        "/api/cuenta/organizacion",
        cuerpo=b'{"nombre":"Taller"}',
        encabezados={
            "Authorization": "Bearer abc",
            "Content-Type": "application/json",
            "Cookie": "sesion=del-equipo",
            "Origin": f"http://127.0.0.1:{local}",
            "Referer": f"http://127.0.0.1:{local}/cuenta",
        },
    )
    eco = json.loads(datos)
    assert eco["metodo"] == "POST"
    assert eco["cuerpo"] == '{"nombre":"Taller"}'
    assert eco["encabezados"]["authorization"] == "Bearer abc"
    assert eco["encabezados"]["host"] == api.removeprefix("http://")
    for propio in ("cookie", "origin", "referer"):
        assert propio not in eco["encabezados"]


def test_una_redireccion_de_la_api_sigue_pasando_por_aqui(local: int) -> None:
    estado, encabezados, _ = _pedir(local, "GET", "/api/redirige")
    assert estado == 307
    assert encabezados["location"] == "/api/destino"


def test_sin_api_responde_con_un_error_que_la_aplicacion_entiende(web: Path) -> None:
    # Un puerto donde no escucha nadie.
    servidor = mechanified.ServidorMechanified(
        0, web, mechanified.ConexionesApi("http://127.0.0.1:9")
    )
    puerto = servidor.server_address[1]
    servidor.anfitriones = {f"127.0.0.1:{puerto}"}
    _en_hilo(servidor)
    try:
        estado, _, datos = _pedir(puerto, "GET", "/api/salud")
    finally:
        servidor.shutdown()
        servidor.server_close()

    assert estado == 502
    assert json.loads(datos)["error"]["codigo"] == "sin_servidor"


def test_una_direccion_de_api_invalida_no_arranca() -> None:
    with pytest.raises(ValueError):
        mechanified.ConexionesApi("api.mechanified.test")
