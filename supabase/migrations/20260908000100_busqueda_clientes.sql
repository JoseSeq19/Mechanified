-- =============================================================================
-- Mechanified · 20260908000100 · Búsqueda de clientes por coincidencia parcial
--
-- La migración 000300 indexó `clientes.nombre` con un GIN de tsvector. Al
-- construir el buscador quedó claro que ese índice no sirve para este caso:
-- tsvector indexa palabras completas y lematizadas, así que un asesor que
-- escribe "villa" en la caja de búsqueda no encuentra a "Villamizar".
--
-- Lo que hace falta es coincidencia por subcadena (`ILIKE '%villa%'`), y eso lo
-- indexa pg_trgm con trigramas. Se sustituye el índice en vez de sumar otro:
-- mantener uno que ninguna consulta usa solo encarece cada escritura.
--
-- Se indexan también `documento` y `telefono` porque son los otros dos campos
-- por los que se busca a un cliente en recepción.
-- =============================================================================

create extension if not exists pg_trgm with schema extensions;

drop index if exists public.clientes_busqueda_idx;

create index clientes_busqueda_trgm_idx on public.clientes
  using gin (
    nombre    extensions.gin_trgm_ops,
    documento extensions.gin_trgm_ops,
    telefono  extensions.gin_trgm_ops
  );

comment on index public.clientes_busqueda_trgm_idx is
  'Soporta ILIKE ''%texto%'' sobre los campos por los que se busca un cliente. '
  'Requiere al menos 3 caracteres para que el planificador lo aproveche.';
