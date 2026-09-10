"""Paginación compartida por los listados de la API."""

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, Field

LIMITE_MAXIMO = 200


class ParametrosPagina(BaseModel):
    """Parámetros de consulta para un listado."""

    limite: Annotated[int, Field(ge=1, le=LIMITE_MAXIMO)] = 50
    desplazamiento: Annotated[int, Field(ge=0)] = 0


async def parametros_pagina(
    limite: Annotated[int, Query(ge=1, le=LIMITE_MAXIMO, description="Filas por página")] = 50,
    desplazamiento: Annotated[int, Query(ge=0, description="Filas a saltar")] = 0,
) -> ParametrosPagina:
    """Dependencia para inyectar la paginación en un endpoint."""
    return ParametrosPagina(limite=limite, desplazamiento=desplazamiento)


class Pagina[T](BaseModel):
    """Un tramo de resultados junto con el total disponible.

    Se devuelve `total` además de los elementos porque la interfaz necesita
    saber cuántas páginas hay antes de pintar el paginador.
    """

    items: list[T]
    total: int
    limite: int
    desplazamiento: int

    @property
    def hay_mas(self) -> bool:
        return self.desplazamiento + len(self.items) < self.total
