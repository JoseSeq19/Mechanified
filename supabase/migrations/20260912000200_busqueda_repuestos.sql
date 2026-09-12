-- =============================================================================
-- Mechanified · 20260912000200 · Búsqueda del catálogo de repuestos
--
-- La migración 000600 indexó el catálogo con un GIN de tsvector, que indexa
-- palabras completas y lematizadas. Quien busca una pieza en el mostrador
-- escribe un trozo del SKU ("AMO-020") o media palabra ("amorti"), y eso
-- tsvector no lo encuentra.
--
-- Se sustituye por trigramas, igual que en clientes (20260908000100) y
-- vehículos (20260909000100). El índice único sobre upper(sku) se conserva:
-- es lo que garantiza que no haya dos piezas con el mismo código.
-- =============================================================================

drop index if exists public.repuestos_busqueda_idx;

create index repuestos_busqueda_trgm_idx on public.repuestos
  using gin (
    sku       extensions.gin_trgm_ops,
    nombre    extensions.gin_trgm_ops,
    categoria extensions.gin_trgm_ops
  );

comment on index public.repuestos_busqueda_trgm_idx is
  'Soporta ILIKE ''%texto%'' sobre SKU, nombre y categoría del catálogo.';
