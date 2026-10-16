"""Esquemas de entrada y salida de adjuntos.

El archivo **no pasa por esta API**. El navegador lo sube directo al bucket con
su propia sesión de Supabase, y después registra aquí los metadatos. Es
deliberado: hacer pasar 25 MiB de foto por FastAPI no añadiría ninguna
comprobación que la política del bucket no haga ya, y a cambio ocuparía un
trabajador del servidor durante toda la subida, con el móvil del técnico y su
cobertura de taller marcando el ritmo.

Lo que sí se valida aquí es que los metadatos no mientan: el tipo y el tamaño
declarados tienen que ser de los que el bucket acepta, y la ruta tiene que
seguir la convención que sostiene el aislamiento entre talleres.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.adjuntos.models import ContextoAdjunto

#: Los mismos que declara el bucket `mch-evidencias` en la migración 001000.
#: Si aquí sobrara uno, la subida fallaría en el storage después de que la
#: interfaz hubiera dicho que estaba bien.
MIMES_PERMITIDOS: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/heic", "application/pdf"}
)

#: 25 MiB, el tope del bucket.
TAMANO_MAXIMO = 26_214_400


class AdjuntoRegistrar(BaseModel):
    """Metadatos de un archivo que ya está subido al bucket."""

    contexto: ContextoAdjunto = ContextoAdjunto.INGRESO
    ruta_storage: Annotated[str, Field(min_length=3, max_length=500)]
    nombre_archivo: Annotated[str, Field(min_length=1, max_length=200)]
    mime: Annotated[str, Field(max_length=100)]
    tamano_bytes: Annotated[int, Field(ge=1, le=TAMANO_MAXIMO)]
    descripcion: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("descripcion", mode="before")
    @classmethod
    def _vacio_es_nulo(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip() or None
        return v

    @field_validator("nombre_archivo", mode="before")
    @classmethod
    def _solo_el_nombre(cls, v: object) -> object:
        """Se queda con el nombre, sin carpetas.

        Un navegador no manda rutas, pero el nombre acaba escrito en la cabecera
        de una descarga y en el documento impreso; que no pueda traer barras ni
        saltos de línea es más barato que confiar.
        """
        if not isinstance(v, str):
            return v
        limpio = v.replace("\\", "/").split("/")[-1].strip()
        return "".join(c for c in limpio if c.isprintable())

    @field_validator("mime")
    @classmethod
    def _mime_del_bucket(cls, v: str) -> str:
        limpio = v.strip().lower()
        if limpio not in MIMES_PERMITIDOS:
            permitidos = ", ".join(sorted(MIMES_PERMITIDOS))
            raise ValueError(f"tipo de archivo no admitido. Se aceptan: {permitidos}")
        return limpio


class AdjuntoRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    orden_id: UUID
    contexto: ContextoAdjunto
    contexto_etiqueta: str
    ruta_storage: str
    nombre_archivo: str
    mime: str | None
    tamano_bytes: int | None
    descripcion: str | None
    #: Quién lo subió. Es null si esa persona ya no está en el taller.
    autor_nombre: str | None = None
    #: True cuando quien pregunta puede borrarlo: lo subió él, o administra.
    puede_borrar: bool = False
    creado_en: datetime
