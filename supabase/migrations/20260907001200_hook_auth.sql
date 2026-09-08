-- =============================================================================
-- Mechanified · 001200 · Hook de Auth: claims de tenant y rol
--
-- Supabase invoca esta función al emitir cada access token. Aquí es donde
-- `taller_id` y `rol` entran al JWT, que es de donde los leen mch_taller_actual()
-- y mch_rol_actual(), y por lo tanto todas las políticas RLS del proyecto.
--
-- Se activa en supabase/config.toml:
--     [auth.hook.custom_access_token]
--     enabled = true
--     uri = "pg-functions://postgres/public/mch_hook_access_token"
--
-- En un proyecto hospedado hay que activarlo además en
-- Authentication > Hooks del panel de Supabase.
--
-- IMPORTANTE, consecuencia operativa: los claims viajan dentro del token. Si un
-- administrador cambia el rol de alguien, ese cambio no surte efecto hasta que
-- el token se renueve (por defecto, una hora). Cuando el cambio deba aplicarse
-- ya, el backend tiene que invalidar las sesiones del usuario. La alternativa
-- —consultar `perfiles` en cada política— costaría una consulta por fila
-- evaluada y haría recursivas las políticas de la propia tabla `perfiles`.
--
-- La función es `security invoker`: corre como supabase_auth_admin, que recibe
-- abajo el permiso mínimo para leer `perfiles` y nada más.
-- =============================================================================

create or replace function public.mch_hook_access_token(event jsonb)
returns jsonb
language plpgsql
stable
as $fn$
declare
  v_claims  jsonb;
  v_taller  uuid;
  v_rol     public.rol_usuario;
  v_activo  boolean;
begin
  select p.taller_id, p.rol, p.activo
    into v_taller, v_rol, v_activo
    from public.perfiles p
   where p.id = (event ->> 'user_id')::uuid;

  v_claims := coalesce(event -> 'claims', '{}'::jsonb);

  if v_taller is not null and coalesce(v_activo, false) then
    v_claims := jsonb_set(v_claims, '{taller_id}', to_jsonb(v_taller::text));
    v_claims := jsonb_set(v_claims, '{rol}',       to_jsonb(v_rol::text));
  else
    -- Sin perfil o con el perfil desactivado el token sale sin claims de
    -- tenant. El usuario puede autenticarse, pero mch_taller_actual() devuelve
    -- NULL y toda política lo deniega: falla cerrado.
    v_claims := v_claims - 'taller_id' - 'rol';
  end if;

  return jsonb_set(event, '{claims}', v_claims);
end;
$fn$;

-- -----------------------------------------------------------------------------
-- Permisos mínimos para el rol de Auth
-- -----------------------------------------------------------------------------

grant usage on schema public to supabase_auth_admin;

grant execute on function public.mch_hook_access_token(jsonb) to supabase_auth_admin;
revoke execute on function public.mch_hook_access_token(jsonb) from authenticated, anon, public;

grant select on table public.perfiles to supabase_auth_admin;

-- `perfiles` lleva `force row level security`, así que supabase_auth_admin
-- necesita su propia política para poder leerla desde el hook.
create policy perfiles_auth_admin_select on public.perfiles
  for select to supabase_auth_admin
  using (true);
