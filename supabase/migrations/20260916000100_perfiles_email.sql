-- =============================================================================
-- Mechanified · 20260916000100 · El correo del usuario, junto a su perfil
--
-- El correo con el que alguien entra vive en `auth.users`, un esquema que las
-- políticas RLS de este proyecto no alcanzan: la pantalla de personal podría
-- listar a la gente del taller, pero no decir con qué dirección entra cada uno,
-- que es justo lo que identifica a una persona cuando hay dos "José".
--
-- Se denormaliza aquí por la misma razón que `taller_id` en el resto de las
-- tablas: para que el dato esté donde se lee, sin un JOIN a un esquema ajeno y
-- sin pedirle nada a la API de administración para pintar una lista.
--
-- Lo escribe el backend al dar de alta a alguien, y lo mantiene el endpoint que
-- cambia el correo de acceso, que actualiza las dos partes a la vez. Cambiarlo
-- a mano desde el panel de Supabase sí lo dejaría desfasado: es el precio de
-- denormalizar, y es un caso raro y sin consecuencias de seguridad.
-- =============================================================================

alter table public.perfiles add column email text;

-- Los perfiles que ya existen toman el correo de su cuenta.
update public.perfiles p
   set email = u.email
  from auth.users u
 where u.id = p.id;

-- Una dirección, una cuenta. `auth.users` ya lo garantiza; este índice impide
-- que una copia desincronizada invente un duplicado que allí no existe.
create unique index perfiles_email_uidx
  on public.perfiles (lower(email))
  where email is not null;

comment on column public.perfiles.email is
  'Copia del correo de auth.users, para poder listarlo bajo RLS. Lo escribe el '
  'backend al crear el usuario y al cambiar su correo de acceso.';
