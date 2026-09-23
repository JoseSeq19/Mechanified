"""Configuración de la aplicación, leída del entorno.

Ninguna credencial tiene valor por defecto real. Si falta algo obligatorio la
app no arranca, que es preferible a arrancar apuntando a un sitio equivocado.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Ruta absoluta a backend/.env, deducida de la ubicación de este archivo:
#: app/core/config.py -> app/core -> app -> backend.
#:
#: Se resuelve así y no como ".env" a secas porque el archivo relativo se busca
#: desde el directorio de trabajo, y entonces arrancar el servidor desde la raíz
#: del repositorio en vez de desde backend/ hacía fallar el arranque con un
#: error de "falta MCH_DATABASE_URL" que no decía nada del verdadero problema.
ARCHIVO_ENV = Path(__file__).resolve().parents[2] / ".env"


class Configuracion(BaseSettings):
    """Variables de entorno con prefijo MCH_."""

    model_config = SettingsConfigDict(
        env_prefix="MCH_",
        env_file=ARCHIVO_ENV,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    entorno: str = "desarrollo"
    log_nivel: str = "INFO"

    # --- Base de datos -------------------------------------------------------
    # Cadena del session pooler de Supabase. La contraseña va percent-encoded.
    database_url: str
    db_pool_tamano: int = 5
    db_pool_desborde: int = 5
    db_echo: bool = False

    # --- Supabase ------------------------------------------------------------
    supabase_url: str
    supabase_anon_key: str = ""
    # Omite RLS. Solo worker de notificaciones, endpoints públicos por token y
    # alta de talleres.
    supabase_service_role_key: str = ""

    # --- Verificación de tokens ----------------------------------------------
    jwt_audiencia: str = "authenticated"
    # ES256 es lo que emite Supabase con llaves asimétricas; HS256 queda para
    # proyectos que aún usan el secreto compartido heredado.
    jwt_algoritmos: list[str] = Field(default_factory=lambda: ["ES256", "RS256", "HS256"])
    # Solo necesario si el proyecto firma con HS256. Con llaves asimétricas se
    # deja vacío y la verificación usa el JWKS.
    supabase_jwt_secret: str = ""

    # --- HTTP ----------------------------------------------------------------
    cors_origenes: str = "http://localhost:5173"
    url_publica_web: str = "http://localhost:5173"

    # --- Correo saliente -----------------------------------------------------
    # En `buzon` el worker no envía nada: escribe cada mensaje como archivo .eml
    # en una carpeta local. Es el modo de desarrollo, y es deliberado que sea el
    # que viene por omisión. Así se ve el correo exacto que recibiría el cliente
    # sin contratar proveedor, y sobre todo sin que una prueba con datos
    # inventados acabe escribiéndole a una dirección real.
    email_modo: Literal["buzon", "smtp"] = "buzon"
    #: Dirección desde la que sale el correo. El nombre visible lo pone el
    #: taller, así que el cliente ve "Taller Norte" y no el dominio del producto.
    email_remitente: str = "notificaciones@mechanified.local"
    #: Carpeta del buzón de desarrollo, relativa a backend/ si no es absoluta.
    email_buzon: str = "buzon"

    smtp_host: str = ""
    smtp_puerto: int = 587
    smtp_usuario: str = ""
    smtp_clave: str = ""
    smtp_seguridad: Literal["starttls", "ssl", "ninguna"] = "starttls"

    # --- Worker de notificaciones --------------------------------------------
    # Embebido en la API mientras esto sea un despliegue de una sola pieza. En
    # producción se apaga y se corre `python -m app.worker` aparte, para que un
    # envío lento no compita con las peticiones. Tenerlo en dos procesos a la vez
    # tampoco rompe nada: la cola se reparte con SELECT ... FOR UPDATE SKIP LOCKED.
    worker_embebido: bool = True
    worker_intervalo_seg: int = 10
    worker_lote: int = 20

    @field_validator("database_url")
    @classmethod
    def _exigir_driver_async(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "MCH_DATABASE_URL debe usar el driver asíncrono: postgresql+asyncpg://..."
            )
        return v

    @property
    def jwks_url(self) -> str:
        """Endpoint con las llaves públicas que firman los tokens."""
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def origenes_cors(self) -> list[str]:
        """Orígenes permitidos por CORS.

        Fuera de producción se añade el gemelo de cada origen local: para el
        navegador, `http://localhost:5173` y `http://127.0.0.1:5173` son
        orígenes distintos, aunque sean la misma máquina y el mismo puerto.

        Sin esto, abrir la web por una de las dos formas funciona y por la otra
        el preflight responde 400, el navegador bloquea la petición, y en
        pantalla aparece un genérico "no se pudo contactar la API" que apunta a
        un problema que no existe. Es tiempo perdido a cambio de ninguna
        seguridad: quien controla una ya controla la otra.
        """
        declarados = [o.strip() for o in self.cors_origenes.split(",") if o.strip()]

        if self.es_produccion:
            return declarados

        completos = list(declarados)
        for origen in declarados:
            gemelo = (
                origen.replace("//localhost", "//127.0.0.1")
                if "//localhost" in origen
                else origen.replace("//127.0.0.1", "//localhost")
            )
            if gemelo != origen and gemelo not in completos:
                completos.append(gemelo)
        return completos

    @property
    def ruta_buzon(self) -> Path:
        """Carpeta del buzón de desarrollo, siempre como ruta absoluta."""
        ruta = Path(self.email_buzon)
        return ruta if ruta.is_absolute() else ARCHIVO_ENV.parent / ruta

    @property
    def es_produccion(self) -> bool:
        return self.entorno.lower() in {"produccion", "production", "prod"}

    @model_validator(mode="after")
    def _exigir_smtp_completo(self) -> "Configuracion":
        """Si se pide enviar de verdad, tiene que haber a dónde enviar.

        Arrancar con `email_modo=smtp` y sin servidor dejaría la cola llenándose
        de notificaciones que fallan una a una, y el fallo solo se vería en el
        último error de cada fila.
        """
        if self.email_modo == "smtp" and not (self.smtp_host and self.email_remitente):
            raise ValueError(
                "Con MCH_EMAIL_MODO=smtp hacen falta MCH_SMTP_HOST y MCH_EMAIL_REMITENTE."
            )
        return self


@lru_cache
def obtener_configuracion() -> Configuracion:
    """Instancia única. El caché evita releer el archivo en cada request."""
    return Configuracion()  # type: ignore[call-arg]
