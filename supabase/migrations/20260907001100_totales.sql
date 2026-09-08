-- =============================================================================
-- Mechanified · 001100 · Totales de la orden
--
-- `ordenes_servicio.total_mano_obra` y `total_repuestos` se mantienen por
-- trigger en vez de calcularse al vuelo con un SUM. El tablero de órdenes
-- muestra decenas de filas con su monto: resolverlo por agregación en cada
-- consulta obligaría a recorrer las líneas de todas las órdenes visibles.
--
-- La función es `security invoker` a propósito. Corre como el usuario que
-- modificó la línea y por lo tanto queda sujeta a la política de UPDATE de
-- `ordenes_servicio`, que exige que la orden sea de su taller. Si fuera
-- `security definer` correría como postgres y, con `force row level security`
-- activo en esa tabla, ninguna política le aplicaría y la escritura fallaría.
-- =============================================================================

create or replace function public.mch_recalcular_totales_orden()
returns trigger
language plpgsql
as $fn$
declare
  v_orden_id  uuid := coalesce(new.orden_id, old.orden_id);
  v_mano_obra numeric(12,2);
  v_repuestos numeric(12,2);
begin
  -- Al borrar una orden, la cascada elimina primero sus líneas y dispara este
  -- trigger. Sin esta salida temprana intentaríamos actualizar una fila que ya
  -- está siendo eliminada en la misma sentencia.
  if not exists (select 1 from public.ordenes_servicio where id = v_orden_id) then
    return null;
  end if;

  select coalesce(sum(subtotal), 0) into v_mano_obra
    from public.orden_mano_obra where orden_id = v_orden_id;

  select coalesce(sum(subtotal), 0) into v_repuestos
    from public.orden_repuestos where orden_id = v_orden_id;

  update public.ordenes_servicio
     set total_mano_obra = v_mano_obra,
         total_repuestos = v_repuestos
   where id = v_orden_id
     and (total_mano_obra, total_repuestos) is distinct from (v_mano_obra, v_repuestos);

  return null;
end;
$fn$;

comment on function public.mch_recalcular_totales_orden is
  'Suma todas las líneas de la orden, sin filtrar por estado del ítem. El total '
  'de la orden refleja lo que hay cargado; lo que el cliente aprobó vive en el '
  'presupuesto, que es un documento aparte y congelado.';

create trigger mch_mano_obra_totales
  after insert or update or delete on public.orden_mano_obra
  for each row execute function public.mch_recalcular_totales_orden();

create trigger mch_orden_repuestos_totales
  after insert or update or delete on public.orden_repuestos
  for each row execute function public.mch_recalcular_totales_orden();
