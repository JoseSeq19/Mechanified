-- =============================================================================
-- Mechanified · 20260909000100 · Búsqueda de vehículos
--
-- En recepción se busca un vehículo escribiendo un trozo de la placa, y a veces
-- por marca o modelo cuando el cliente no la recuerda. Los índices únicos que
-- ya existen sobre `upper(placa)` y `upper(vin)` sirven para comparaciones
-- exactas y para prefijos, pero no para subcadenas: buscar "123" no encontraría
-- "AB123CD".
--
-- Se añade un índice de trigramas sobre los cuatro campos por los que se busca,
-- igual que se hizo con clientes en 20260908000100. Los índices únicos se
-- conservan: siguen haciendo falta para garantizar que no haya dos vehículos
-- con la misma placa en el mismo taller.
-- =============================================================================

create index vehiculos_busqueda_trgm_idx on public.vehiculos
  using gin (
    placa  extensions.gin_trgm_ops,
    vin    extensions.gin_trgm_ops,
    marca  extensions.gin_trgm_ops,
    modelo extensions.gin_trgm_ops
  );

comment on index public.vehiculos_busqueda_trgm_idx is
  'Soporta ILIKE ''%texto%'' sobre placa, VIN, marca y modelo. Requiere al '
  'menos 3 caracteres para que el planificador lo aproveche.';
