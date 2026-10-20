-- =============================================================================
-- Mechanified · 20261020000100 · Organizaciones
--
-- Mechanified es el producto y quien lo usa es una organización: un grupo con
-- varias sedes, como Grupo La Meseta, o un taller independiente con una sola.
-- El nombre de la organización es el que lleva el producto para quien entra en
-- ella: la gente de Grupo La Meseta ve "Grupo La Meseta", no "Mechanified".
--
-- La organización está **por encima** del inquilino, no lo sustituye. El taller
-- sigue siendo la unidad de RLS: dos sedes de la misma organización siguen sin
-- verse la una a la otra, que es lo que este esquema garantizó desde el
-- principio. La organización no da acceso a ningún dato; da identidad.
--
-- Cuatro piezas:
--
--   1. `organizaciones` y `talleres.organizacion_id`.
--   2. `mch_crear_mi_organizacion()`: alta por cuenta propia. Quien se registra
--      en el sitio de Mechanified funda su organización con su primer taller y
--      queda como su administrador.
--   3. `solicitudes_organizacion`: para quien prefiere que se la cree el
--      equipo de Mechanified.
--   4. El bucket `mch-descargas`, de donde sale el instalador para Windows.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Identificadores libres
-- -----------------------------------------------------------------------------

-- Primer slug libre a partir de una base: "taller-garcia", "taller-garcia-2"...
--
-- Con el alta por cuenta propia, dos talleres que se llaman igual dejan de ser
-- raros, y pedirle a quien se registra que invente un identificador global es
-- hacerle resolver un problema que no es suyo. Quien llama garantiza que la base
-- cumple el formato de slug; aquí solo se le añade un sufijo si está ocupada.
create or replace function public.mch_slug_libre(p_base text, p_tabla regclass)
returns text
language plpgsql
stable
as $fn$
declare
  v_slug   text := p_base;
  v_n      int  := 1;
  v_existe boolean;
begin
  loop
    execute format('select exists (select 1 from %s where slug = $1)', p_tabla)
      into v_existe
      using v_slug;
    exit when not v_existe;

    v_n := v_n + 1;
    v_slug := rtrim(left(p_base, 50 - length(v_n::text) - 1), '-') || '-' || v_n;
  end loop;
  return v_slug;
end;
$fn$;

-- Interna: solo la llaman los triggers y las funciones de alta de abajo. Bajo
-- RLS no vería las filas ajenas y devolvería un slug que parece libre sin serlo.
revoke execute on function public.mch_slug_libre(text, regclass) from public, anon, authenticated;

-- -----------------------------------------------------------------------------
-- Organizaciones
-- -----------------------------------------------------------------------------

-- No lleva `taller_id`, como tampoco lo lleva `talleres`: está por encima del
-- inquilino, no dentro de él.
create table public.organizaciones (
  id             uuid primary key default gen_random_uuid(),
  nombre         text not null check (length(trim(nombre)) between 2 and 120),
  slug           text not null unique,
  -- Quién la fundó, cuando fue por cuenta propia. Nulo en las que crea el
  -- equipo de Mechanified y en la que nace con esta migración.
  creada_por     uuid references auth.users(id) on delete set null,
  creado_en      timestamptz not null default now(),
  actualizado_en timestamptz not null default now(),
  constraint organizaciones_slug_formato check (slug ~ '^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$')
);

comment on table public.organizaciones is
  'Cliente de Mechanified. Agrupa talleres (sedes) y da nombre al producto. '
  'No es unidad de aislamiento: esa sigue siendo el taller.';

create trigger mch_organizaciones_actualizado_en
  before update on public.organizaciones
  for each row execute function public.mch_set_actualizado_en();

alter table public.talleres
  add column organizacion_id uuid references public.organizaciones(id) on delete restrict;

-- Hasta esta migración la base era el sistema interno de Grupo La Meseta, así
-- que todo taller que ya exista es una sede suya. En una base nueva no hay
-- talleres todavía y no se crea nada.
with grupo as (
  insert into public.organizaciones (nombre, slug)
  select 'Grupo La Meseta', 'grupo-la-meseta'
   where exists (select 1 from public.talleres)
  returning id
)
update public.talleres
   set organizacion_id = (select id from grupo)
 where organizacion_id is null;

alter table public.talleres alter column organizacion_id set not null;

create index talleres_organizacion_idx on public.talleres (organizacion_id);

-- Un taller que llega sin organización funda la suya, con su mismo nombre.
--
-- Es el caso del taller independiente, el más común: para él organización y
-- taller son la misma cosa, y obligar a crear las dos a mano sería pedir el
-- mismo nombre dos veces. También deja funcionando sin cambios cada sitio que ya
-- insertaba talleres (el alta por línea de comandos, el seed, las pruebas).
create or replace function public.mch_talleres_organizacion_propia()
returns trigger
language plpgsql
as $fn$
begin
  if new.organizacion_id is null then
    insert into public.organizaciones (nombre, slug)
    values (new.nombre, public.mch_slug_libre(new.slug, 'public.organizaciones'))
    returning id into new.organizacion_id;
  end if;
  return new;
end;
$fn$;

create trigger mch_talleres_organizacion
  before insert on public.talleres
  for each row execute function public.mch_talleres_organizacion_propia();

-- Un taller no se cambia de organización desde una sesión de usuario.
--
-- `talleres_update` deja a la administración editar su taller, y la API de
-- datos de Supabase queda expuesta a cualquier token: sin esto, un
-- administrador podría colgar su sede de otra organización con un PATCH directo
-- y presentarse con el nombre de otro cliente. Mover sedes es una operación del
-- equipo de Mechanified, que trabaja sin claims de usuario.
create or replace function public.mch_talleres_organizacion_guard()
returns trigger
language plpgsql
as $fn$
begin
  if new.organizacion_id is distinct from old.organizacion_id
     and public.mch_rol_actual() is not null then
    raise exception 'Un taller no se cambia de organización desde la aplicación'
      using errcode = 'insufficient_privilege';
  end if;
  return new;
end;
$fn$;

create trigger mch_talleres_organizacion_guard
  before update of organizacion_id on public.talleres
  for each row execute function public.mch_talleres_organizacion_guard();

-- Una organización sin talleres no tiene a nadie dentro —los perfiles cuelgan
-- del taller— y su slug quedaría ocupado para siempre. Se va con su último
-- taller, que es también lo que deshace un alta fallida a medias.
create or replace function public.mch_organizaciones_sin_talleres()
returns trigger
language plpgsql
as $fn$
begin
  delete from public.organizaciones o
   where o.id = old.organizacion_id
     and not exists (select 1 from public.talleres t where t.organizacion_id = o.id);
  return null;
end;
$fn$;

create trigger mch_talleres_organizacion_vacia
  after delete on public.talleres
  for each row execute function public.mch_organizaciones_sin_talleres();

-- Organización de la sesión: la del taller del token. Pasa por la política de
-- `talleres`, así que no puede devolver otra que la propia.
create or replace function public.mch_organizacion_actual()
returns uuid
language sql
stable
as $$
  select t.organizacion_id from public.talleres t where t.id = public.mch_taller_actual();
$$;

comment on function public.mch_organizacion_actual() is
  'Organización del taller de la sesión. NULL fuera de una sesión con taller.';

alter table public.organizaciones enable row level security;
alter table public.organizaciones force  row level security;

-- Cada sede ve su organización y ninguna otra. Escribirla es cosa del alta (por
-- cuenta propia o del equipo), que pasa por funciones `security definer`: no hay
-- políticas de INSERT, UPDATE ni DELETE.
create policy organizaciones_select on public.organizaciones
  for select to authenticated
  using (id = (select public.mch_organizacion_actual()));

-- -----------------------------------------------------------------------------
-- Solicitudes: "que nos la cree el equipo"
--
-- No lleva `taller_id` porque es anterior a cualquier taller: la escribe una
-- cuenta que todavía no pertenece a ninguno. Su barrera es la cuenta, con la
-- misma forma que la del resto del esquema: una comparación simple con
-- `auth.uid()`.
-- -----------------------------------------------------------------------------

create type public.estado_solicitud as enum ('pendiente', 'atendida', 'descartada');

create table public.solicitudes_organizacion (
  id                  uuid primary key default gen_random_uuid(),
  cuenta_id           uuid not null references auth.users(id) on delete cascade,
  -- Copia del correo de la cuenta, que es a donde contesta el equipo. La pone
  -- el trigger de abajo, no el formulario.
  email               text not null,
  nombre_contacto     text not null check (length(trim(nombre_contacto)) between 2 and 120),
  nombre_organizacion text not null check (length(trim(nombre_organizacion)) between 2 and 120),
  telefono            text check (length(telefono) <= 40),
  sedes               int  check (sedes between 1 and 999),
  mensaje             text check (length(mensaje) <= 2000),
  estado              public.estado_solicitud not null default 'pendiente',
  organizacion_id     uuid references public.organizaciones(id) on delete set null,
  creado_en           timestamptz not null default now(),
  atendida_en         timestamptz
);

comment on table public.solicitudes_organizacion is
  'Peticiones de alta que atiende el equipo de Mechanified. Pertenecen a una '
  'cuenta, no a un taller: quien la manda todavía no tiene ninguno.';

-- Una pendiente por cuenta: pedirlo dos veces no lo hace más rápido, y al
-- equipo le basta con una para contestar.
create unique index solicitudes_organizacion_pendiente_uidx
  on public.solicitudes_organizacion (cuenta_id)
  where estado = 'pendiente';

create index solicitudes_organizacion_estado_idx
  on public.solicitudes_organizacion (estado, creado_en);

-- Una solicitud nace pendiente, sin organización y con el correo de la cuenta,
-- la mande quien la mande: la API de datos de Supabase está expuesta, y el
-- correo es a donde el equipo va a escribir. Nadie debe poder apuntarlo a la
-- dirección de otro.
create or replace function public.mch_solicitudes_organizacion_guard()
returns trigger
language plpgsql
security definer
set search_path = public
as $fn$
begin
  select u.email into new.email from auth.users u where u.id = new.cuenta_id;
  if new.email is null then
    raise exception 'La cuenta de la solicitud no existe o no tiene correo'
      using errcode = 'foreign_key_violation';
  end if;

  new.estado          := 'pendiente';
  new.organizacion_id := null;
  new.atendida_en     := null;
  return new;
end;
$fn$;

create trigger mch_solicitudes_organizacion_guard
  before insert on public.solicitudes_organizacion
  for each row execute function public.mch_solicitudes_organizacion_guard();

alter table public.solicitudes_organizacion enable row level security;
alter table public.solicitudes_organizacion force  row level security;

create policy solicitudes_organizacion_select on public.solicitudes_organizacion
  for select to authenticated
  using (cuenta_id = (select auth.uid()));

-- Solo quien aún no pertenece a ninguna organización: a quien ya tiene una no
-- le hace falta otra, y la de su sede la amplía el equipo con un taller más.
create policy solicitudes_organizacion_insert on public.solicitudes_organizacion
  for insert to authenticated
  with check (
    cuenta_id = (select auth.uid())
    and not exists (select 1 from public.perfiles p where p.id = (select auth.uid()))
  );

-- -----------------------------------------------------------------------------
-- Alta de una organización con su primer taller y su administrador
-- -----------------------------------------------------------------------------

-- El núcleo, para una cuenta que ya existe en Auth. Lo usan dos caminos:
--
--   - mch_crear_mi_organizacion(), la puerta para la propia cuenta, de abajo;
--   - el equipo de Mechanified al atender una solicitud, desde la línea de
--     comandos, sin claims de usuario.
--
-- No está al alcance de `authenticated`: recibe la cuenta por parámetro, y
-- dejarla abierta sería dejar que cualquiera fundara organizaciones a nombre de
-- otro.
create or replace function public.mch_crear_organizacion(
  p_cuenta              uuid,
  p_nombre_organizacion text,
  p_nombre_taller       text,
  p_slug_organizacion   text,
  p_slug_taller         text,
  p_prefijo             text,
  p_nombre_admin        text,
  p_telefono            text    default null,
  p_moneda              text    default 'USD',
  p_tarifa              numeric default 0,
  p_impuesto            numeric default 0
)
returns table (organizacion_id uuid, taller_id uuid)
language plpgsql
security definer
set search_path = public
as $fn$
#variable_conflict use_column
declare
  v_email  text;
  v_org    uuid;
  v_taller uuid;
begin
  -- Las altas se hacen de una en una. Son raras, y así la búsqueda de slug libre
  -- y la comprobación de "esta cuenta ya tiene organización" no pueden cruzarse
  -- con otra alta que esté ocurriendo a la vez.
  perform pg_advisory_xact_lock(hashtext('mch_crear_organizacion'));

  select u.email into v_email from auth.users u where u.id = p_cuenta;
  if not found then
    raise exception 'La cuenta % no existe', p_cuenta using errcode = 'foreign_key_violation';
  end if;

  -- Una cuenta, una organización: el perfil es el de la cuenta (perfiles.id es
  -- el de auth.users) y el token solo lleva un taller.
  if exists (select 1 from public.perfiles p where p.id = p_cuenta) then
    raise exception 'Esta cuenta ya pertenece a una organización'
      using errcode = 'unique_violation';
  end if;

  insert into public.organizaciones (nombre, slug, creada_por)
  values (
    trim(p_nombre_organizacion),
    public.mch_slug_libre(p_slug_organizacion, 'public.organizaciones'),
    p_cuenta
  )
  returning id into v_org;

  insert into public.talleres (
    organizacion_id, nombre, slug, telefono,
    moneda, tarifa_hora_default, impuesto_pct, prefijo_orden
  ) values (
    v_org, trim(p_nombre_taller), public.mch_slug_libre(p_slug_taller, 'public.talleres'),
    p_telefono, p_moneda, p_tarifa, p_impuesto, p_prefijo
  )
  returning id into v_taller;

  insert into public.perfiles (id, taller_id, nombre_completo, email, telefono, rol)
  values (p_cuenta, v_taller, trim(p_nombre_admin), v_email, p_telefono, 'admin_taller');

  -- Si había pedido que se la creara el equipo y al final la creó ella misma,
  -- la solicitud queda atendida: no hay nada que el equipo tenga que hacer ya.
  update public.solicitudes_organizacion s
     set estado = 'atendida', organizacion_id = v_org, atendida_en = now()
   where s.cuenta_id = p_cuenta
     and s.estado = 'pendiente';

  return query select v_org, v_taller;
end;
$fn$;

revoke execute on function public.mch_crear_organizacion(
  uuid, text, text, text, text, text, text, text, text, numeric, numeric
) from public, anon, authenticated;

-- La puerta de la propia cuenta: la misma alta, con la cuenta sacada del token
-- y no de un parámetro. El perfil que crea es el que el hook de Auth convierte
-- en claims, así que el siguiente token de esa cuenta ya sale con su taller.
create or replace function public.mch_crear_mi_organizacion(
  p_nombre_organizacion text,
  p_nombre_taller       text,
  p_slug_organizacion   text,
  p_slug_taller         text,
  p_prefijo             text,
  p_nombre_admin        text,
  p_telefono            text    default null,
  p_moneda              text    default 'USD',
  p_tarifa              numeric default 0,
  p_impuesto            numeric default 0
)
returns table (organizacion_id uuid, taller_id uuid)
language plpgsql
security definer
set search_path = public
as $fn$
begin
  if auth.uid() is null then
    raise exception 'Hace falta iniciar sesión para crear una organización'
      using errcode = 'insufficient_privilege';
  end if;

  return query
    select * from public.mch_crear_organizacion(
      auth.uid(), p_nombre_organizacion, p_nombre_taller, p_slug_organizacion,
      p_slug_taller, p_prefijo, p_nombre_admin, p_telefono, p_moneda, p_tarifa, p_impuesto
    );
end;
$fn$;

revoke execute on function public.mch_crear_mi_organizacion(
  text, text, text, text, text, text, text, text, numeric, numeric
) from public, anon;
grant execute on function public.mch_crear_mi_organizacion(
  text, text, text, text, text, text, text, text, numeric, numeric
) to authenticated;

-- Dónde está la cuenta de la sesión: su organización, su sede y su rol.
--
-- Es lo que necesita saber el sitio para decidir qué ofrecerle a alguien, y lo
-- necesita también cuando su token aún no trae taller (recién creada la
-- organización, antes de renovarlo), que es justo cuando la política de
-- `talleres` todavía no le deja ver el suyo. Solo devuelve la fila de la propia
-- cuenta.
create or replace function public.mch_mi_cuenta()
returns table (
  organizacion_id     uuid,
  organizacion_nombre text,
  taller_id           uuid,
  taller_nombre       text,
  rol                 public.rol_usuario,
  activo              boolean
)
language sql
stable
security definer
set search_path = public
as $$
  select o.id, o.nombre, t.id, t.nombre, p.rol, p.activo
    from public.perfiles p
    join public.talleres t       on t.id = p.taller_id
    join public.organizaciones o on o.id = t.organizacion_id
   where p.id = auth.uid();
$$;

revoke execute on function public.mch_mi_cuenta() from public, anon;
grant execute on function public.mch_mi_cuenta() to authenticated;

-- -----------------------------------------------------------------------------
-- Descargas
--
-- El instalador sale de un bucket privado, y lo puede bajar cualquier cuenta con
-- sesión, tenga organización o no: descargarlo es el paso anterior a crearla.
-- Que haga falta sesión no protege ningún secreto —el ejecutable no lleva
-- ninguno— sino que el producto se entrega a quien tiene cuenta.
--
-- Solo hay política de lectura: lo sube el equipo con la llave de servicio.
-- Si `supabase db reset` falla aquí con "must be owner of table objects", es el
-- mismo caso que documenta 20260907001000_adjuntos.sql.
-- -----------------------------------------------------------------------------

insert into storage.buckets (id, name, public)
values ('mch-descargas', 'mch-descargas', false)
on conflict (id) do nothing;

create policy mch_descargas_select on storage.objects
  for select to authenticated
  using (bucket_id = 'mch-descargas');
