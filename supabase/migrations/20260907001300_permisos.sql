-- =============================================================================
-- Mechanified · 001300 · Permisos de esquema
--
-- Supabase concede por defecto acceso al rol `anon` sobre las tablas de
-- `public`. En Mechanified nadie sin sesión toca datos de negocio: la web y el
-- móvil hablan con FastAPI, y los dos flujos públicos que existen (aprobar un
-- presupuesto, responder la encuesta) los resuelve el backend con el rol de
-- servicio tras validar el token del enlace.
--
-- Quitar el acceso de `anon` es defensa en profundidad: aunque a alguien se le
-- olvidara una política, sin privilegio de tabla no hay lectura posible.
-- =============================================================================

revoke all on all tables    in schema public from anon;
revoke all on all sequences in schema public from anon;

-- Aplica también a lo que se cree en migraciones futuras, para no depender de
-- que alguien recuerde repetir el revoke.
alter default privileges in schema public revoke all on tables    from anon;
alter default privileges in schema public revoke all on sequences from anon;

-- El rol de las sesiones de usuario conserva sus privilegios de tabla; el
-- filtrado real lo hacen las políticas RLS.
grant usage on schema public to authenticated;
grant select, insert, update, delete on all tables in schema public to authenticated;
grant usage, select on all sequences in schema public to authenticated;

-- Tablas de infraestructura que ningún usuario debe alcanzar, ni siquiera con
-- privilegio de tabla: solo las escriben funciones security definer y el worker.
revoke all on table public.secuencias_folio from authenticated, anon;
