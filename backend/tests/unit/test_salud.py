"""Prueba de humo de la aplicación.

Verifica que la app se construye y responde. No toca la base de datos: las
pruebas que sí lo hacen viven en tests/integration y necesitan Supabase.
"""

from fastapi.testclient import TestClient

from app.main import app

cliente = TestClient(app)


def test_salud_responde_ok() -> None:
    respuesta = cliente.get("/salud")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok", "servicio": "meseta-api"}


def test_openapi_se_genera() -> None:
    """El esquema OpenAPI es parte del contrato: si no se genera, /docs muere."""
    respuesta = cliente.get("/openapi.json")

    assert respuesta.status_code == 200
    esquema = respuesta.json()
    assert esquema["info"]["title"] == "API de Grupo La Meseta"
    assert "/salud" in esquema["paths"]
