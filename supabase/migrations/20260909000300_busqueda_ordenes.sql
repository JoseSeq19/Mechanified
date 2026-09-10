-- =============================================================================
-- Mechanified · 20260909000300 · Búsqueda de órdenes por folio
--
-- El índice único `ordenes_taller_folio_uidx` sirve para el folio exacto y para
-- prefijos, pero en recepción se teclea el trozo que se recuerda ("42", "0042")
-- y eso exige coincidencia por subcadena.
--
-- Mismo criterio que en clientes y vehículos: trigramas. El índice único se
-- conserva, porque es lo que garantiza que no haya dos folios iguales.
-- =============================================================================

create index ordenes_folio_trgm_idx on public.ordenes_servicio
  using gin (folio extensions.gin_trgm_ops);

comment on index public.ordenes_folio_trgm_idx is
  'Soporta ILIKE ''%texto%'' sobre el folio. La búsqueda por placa o por nombre '
  'del cliente la resuelven los índices de vehiculos y clientes vía JOIN.';
