-- =============================================================================
-- Mechanified · 20260909000400 · Comentario en cualquier evento de la bitácora
--
-- Hasta ahora `mch_ordenes_bitacora` solo guardaba un comentario al cancelar,
-- copiando `motivo_cancelacion`. El resto de las transiciones quedaban sin nota,
-- y son justo las que suelen necesitarla: por qué el control de calidad devolvió
-- el vehículo a reparación, qué apareció que obliga a re-presupuestar.
--
-- El comentario no puede viajar como columna de `ordenes_servicio` —no
-- pertenece a la orden, sino al evento— ni escribirse después del UPDATE,
-- porque `orden_eventos` no admite escritura desde la aplicación: es
-- append-only y solo la toca este trigger.
--
-- La vía es un ajuste local de transacción. El servicio hace:
--
--     select set_config('mch.comentario_evento', 'texto', true);
--     update public.ordenes_servicio set estado = ... where id = ...;
--
-- y el trigger lo recoge. Al ser `local`, el valor muere con la transacción, así
-- que no puede filtrarse al siguiente request que reutilice la conexión.
-- =============================================================================

create or replace function public.mch_ordenes_bitacora()
returns trigger
language plpgsql
security definer
set search_path = public
as $fn$
declare
  v_usuario    uuid;
  v_comentario text;
begin
  -- Autor: NULL si quien mueve la orden ya no tiene perfil en el taller.
  -- Ver la migración 20260909000200.
  select p.id into v_usuario
    from public.perfiles p
   where p.id = auth.uid();

  -- El segundo argumento en true hace que devuelva NULL en vez de fallar
  -- cuando el ajuste no se definió en esta transacción.
  v_comentario := nullif(current_setting('mch.comentario_evento', true), '');

  if tg_op = 'INSERT' then
    insert into public.orden_eventos (taller_id, orden_id, estado_anterior, estado_nuevo, usuario_id, comentario)
    values (new.taller_id, new.id, null, new.estado, v_usuario, v_comentario);
  elsif new.estado is distinct from old.estado then
    insert into public.orden_eventos (taller_id, orden_id, estado_anterior, estado_nuevo, usuario_id, comentario)
    values (new.taller_id, new.id, old.estado, new.estado, v_usuario,
            coalesce(
              v_comentario,
              case when new.estado = 'cancelado' then new.motivo_cancelacion end
            ));
  end if;

  return null;
end;
$fn$;
