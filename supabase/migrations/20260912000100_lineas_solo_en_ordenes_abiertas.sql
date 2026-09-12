-- =============================================================================
-- Mechanified · 20260912000100 · No se cargan líneas a una orden cerrada
--
-- `orden_mano_obra` y `orden_repuestos` alimentan por trigger los totales de la
-- orden. Nada impedía hasta ahora añadir o modificar una línea en una orden ya
-- entregada o cancelada, lo que cambiaría en silencio el total de un trabajo
-- que el cliente ya pagó y se llevó.
--
-- El guard se aplica solo a INSERT y UPDATE, **no a DELETE**, y eso es
-- deliberado: al borrar una orden, la cascada elimina primero sus líneas, y un
-- guard sobre DELETE haría imposible borrar una orden cancelada. Añadir o
-- cambiar importes es lo que hay que impedir; quitar líneas de algo que se está
-- borrando de todos modos, no.
-- =============================================================================

create or replace function public.mch_linea_orden_abierta()
returns trigger
language plpgsql
as $fn$
declare
  v_estado public.estado_orden;
  v_folio  text;
begin
  select estado, folio into v_estado, v_folio
    from public.ordenes_servicio
   where id = new.orden_id;

  if v_estado in ('entregado', 'cancelado') then
    raise exception
      'La orden % está % y ya no admite cambios en sus líneas.', v_folio, v_estado
      using errcode = 'check_violation';
  end if;

  return new;
end;
$fn$;

create trigger mch_mano_obra_orden_abierta
  before insert or update on public.orden_mano_obra
  for each row execute function public.mch_linea_orden_abierta();

create trigger mch_orden_repuestos_orden_abierta
  before insert or update on public.orden_repuestos
  for each row execute function public.mch_linea_orden_abierta();
