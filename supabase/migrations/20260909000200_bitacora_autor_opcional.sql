-- =============================================================================
-- Mechanified · 20260909000200 · La bitácora tolera un autor sin perfil
--
-- `mch_ordenes_bitacora` guardaba `auth.uid()` directo en
-- `orden_eventos.usuario_id`, que referencia `perfiles`. Si el identificador
-- del token no tiene fila ahí, el INSERT viola la llave foránea y **se cae la
-- operación entera**: la orden no avanza de estado y el error que ve el usuario
-- habla de `orden_eventos_usuario_id_fkey`, que no significa nada para él.
--
-- Es un caso alcanzable: los claims viajan dentro del JWT (ver ADR 0001), así
-- que un usuario al que dieron de baja del taller conserva un token válido
-- hasta una hora. Durante esa ventana puede mover una orden, y hoy eso rompe.
--
-- El criterio: perder el autor de un evento es mucho menos grave que impedir
-- que el taller trabaje. Si no hay perfil, se registra NULL —la columna ya lo
-- admite— y el evento queda igualmente en la bitácora.
--
-- De paso, esto permite que las pruebas de integración usen identidades
-- sintéticas sin tener que crear usuarios en auth.users.
-- =============================================================================

create or replace function public.mch_ordenes_bitacora()
returns trigger
language plpgsql
security definer
set search_path = public
as $fn$
declare
  v_usuario uuid;
begin
  -- Resuelve el autor contra `perfiles` en vez de confiar en auth.uid() a
  -- ciegas. Devuelve NULL si esa persona ya no pertenece al taller.
  select p.id into v_usuario
    from public.perfiles p
   where p.id = auth.uid();

  if tg_op = 'INSERT' then
    insert into public.orden_eventos (taller_id, orden_id, estado_anterior, estado_nuevo, usuario_id)
    values (new.taller_id, new.id, null, new.estado, v_usuario);
  elsif new.estado is distinct from old.estado then
    insert into public.orden_eventos (taller_id, orden_id, estado_anterior, estado_nuevo, usuario_id, comentario)
    values (new.taller_id, new.id, old.estado, new.estado, v_usuario,
            case when new.estado = 'cancelado' then new.motivo_cancelacion end);
  end if;

  return null;
end;
$fn$;
