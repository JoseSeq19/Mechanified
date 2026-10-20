"""Esquemas de entrada y salida de la configuración del taller.

Las validaciones de `TallerEditar` repiten a propósito los `check` de la
migración 000200. No es desconfianza del esquema: es que Postgres rechazaría el
UPDATE con un mensaje que nombra la restricción
(`talleres_prefijo_formato`), y eso no se le puede mostrar a nadie. Validando
aquí primero, quien llena el formulario recibe "el prefijo son 2 a 6 letras o
números en mayúscula" y la base nunca llega a quejarse.

Tres campos de la tabla no se aceptan para escritura, y conviene decir por qué:

- `slug` identifica al taller de forma global y única. Hoy nada lo consume;
  dejarlo editar solo abriría la puerta a romper una referencia futura.
- `zona_horaria` todavía no la lee nadie: las fechas se formatean con la zona
  del navegador. Ofrecer el control daría a entender que cambia algo.
- `logo_url` espera al módulo de adjuntos. Sin un sitio donde subir el archivo,
  pedir una URL suelta es pedirle al usuario que resuelva el problema él.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

#: Tope de `dias_validez_presupuesto`. La base solo exige que sea positivo; un
#: año es el límite a partir del cual el dato deja de significar nada.
MAXIMO_DIAS_VALIDEZ = 365


def _limpiar(valor: str | None) -> str | None:
    """Recorta espacios y convierte la cadena vacía en NULL.

    Un formulario web manda "" cuando el usuario vacía un campo opcional, y la
    intención es borrarlo, no guardar una cadena vacía que luego se imprime
    como un hueco en el presupuesto del cliente.
    """
    if valor is None:
        return None
    limpio = valor.strip()
    return limpio or None


class TallerEditar(BaseModel):
    """Todo opcional: es un PATCH.

    `model_dump(exclude_unset=True)` distingue "no vino el campo" de "vino en
    null", que es lo que permite vaciar un dato de contacto a propósito.
    """

    nombre: Annotated[str, Field(min_length=2, max_length=120)] | None = None
    identificacion_fiscal: Annotated[str, Field(max_length=40)] | None = None
    telefono: Annotated[str, Field(max_length=40)] | None = None
    email: EmailStr | None = None
    direccion: Annotated[str, Field(max_length=500)] | None = None

    #: Código ISO 4217. La base exige tres caracteres; el formato de moneda del
    #: navegador necesita además que sean los tres de un código real.
    moneda: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] | None = None
    tarifa_hora_default: Annotated[Decimal, Field(ge=0, le=Decimal("9999999999.99"))] | None = None
    impuesto_pct: Annotated[Decimal, Field(ge=0, le=100)] | None = None

    prefijo_orden: Annotated[str, Field(pattern=r"^[A-Z0-9]{2,6}$")] | None = None
    dias_validez_presupuesto: Annotated[int, Field(ge=1, le=MAXIMO_DIAS_VALIDEZ)] | None = None

    @field_validator("nombre", mode="before")
    @classmethod
    def _nombre_sin_espacios(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @field_validator("identificacion_fiscal", "telefono", "direccion", "email", mode="before")
    @classmethod
    def _normalizar(cls, v: object) -> object:
        return _limpiar(v) if isinstance(v, str) or v is None else v

    @field_validator("moneda", "prefijo_orden", mode="before")
    @classmethod
    def _a_mayusculas(cls, v: object) -> object:
        # Nadie debería ver un 403 por escribir "usd" en minúscula.
        return v.strip().upper() if isinstance(v, str) else v


class TallerRespuesta(BaseModel):
    """La configuración completa del taller de la sesión.

    La leen todos los roles, no solo administración: la interfaz necesita la
    moneda para poder escribir una cifra sin ambigüedad, y la tarifa y el
    impuesto para poder mostrar de antemano lo que el servidor va a aplicar si
    quien registra una línea no indica otra cosa.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre: str
    slug: str
    identificacion_fiscal: str | None
    telefono: str | None
    email: str | None
    direccion: str | None
    zona_horaria: str
    moneda: str
    tarifa_hora_default: Decimal
    impuesto_pct: Decimal
    prefijo_orden: str
    dias_validez_presupuesto: int
    activo: bool
    creado_en: datetime
    actualizado_en: datetime


class TallerAlta(BaseModel):
    """Alta de un taller nuevo con su primer administrador.

    Es el alta que hace el equipo de Mechanified desde `python -m
    app.alta_taller`, y no tiene endpoint: crea también la cuenta del
    administrador, con la llave de servicio, y le inventa una contraseña. Sirve
    sobre todo para sumar una sede a una organización que ya existe.

    Quien se registra en el sitio y funda su propia organización entra por otra
    puerta, `mch_crear_mi_organizacion()`, que no necesita esa llave: la cuenta
    ya existe y la función la saca del token.

    El `slug` y el prefijo de folio se derivan del nombre si no se indican, que
    es lo que hace que el alta quepa en una línea.
    """

    nombre: Annotated[str, Field(min_length=2, max_length=120)]
    slug: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$")] | None = None

    #: Del primer administrador. Es con esto con lo que entra.
    admin_email: EmailStr
    admin_nombre: Annotated[str, Field(min_length=2, max_length=120)]

    #: A qué organización pertenece. Con `organizacion` (un slug) se suma como
    #: sede a una que ya existe; con `organizacion_nombre` estrena una con ese
    #: nombre. Sin ninguna de las dos, funda la suya con el nombre del taller,
    #: que es el caso del taller independiente.
    organizacion: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$")] | None = None
    organizacion_nombre: Annotated[str, Field(min_length=2, max_length=120)] | None = None

    identificacion_fiscal: Annotated[str, Field(max_length=40)] | None = None
    telefono: Annotated[str, Field(max_length=40)] | None = None
    email: EmailStr | None = None
    direccion: Annotated[str, Field(max_length=500)] | None = None

    zona_horaria: Annotated[str, Field(min_length=3, max_length=60)] = "America/Caracas"
    moneda: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] = "USD"
    tarifa_hora_default: Annotated[Decimal, Field(ge=0, le=Decimal("9999999999.99"))] = Decimal(0)
    impuesto_pct: Annotated[Decimal, Field(ge=0, le=100)] = Decimal(0)
    prefijo_orden: Annotated[str, Field(pattern=r"^[A-Z0-9]{2,6}$")] | None = None
    dias_validez_presupuesto: Annotated[int, Field(ge=1, le=MAXIMO_DIAS_VALIDEZ)] = 15

    @field_validator("nombre", "admin_nombre", mode="before")
    @classmethod
    def _sin_espacios(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @field_validator("identificacion_fiscal", "telefono", "direccion", "email", mode="before")
    @classmethod
    def _normalizar_opcionales(cls, v: object) -> object:
        return _limpiar(v) if isinstance(v, str) or v is None else v

    @field_validator("moneda", "prefijo_orden", mode="before")
    @classmethod
    def _mayusculas(cls, v: object) -> object:
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("slug", "organizacion", mode="before")
    @classmethod
    def _minusculas(cls, v: object) -> object:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("organizacion_nombre", mode="before")
    @classmethod
    def _nombre_organizacion(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _una_sola_organizacion(self) -> "TallerAlta":
        if self.organizacion and self.organizacion_nombre:
            raise ValueError(
                "Indica la organización existente o el nombre de una nueva, no las dos cosas."
            )
        return self
