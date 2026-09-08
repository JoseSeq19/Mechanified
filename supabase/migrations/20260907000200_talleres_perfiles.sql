-- =============================================================================
-- Mechanified · 000200 · Talleres y perfiles
-- El taller es el tenant. El perfil enlaza un usuario de Supabase Auth con su
-- taller y su rol; es la tabla que lee el hook de Auth para armar los claims.
-- =============================================================================

create table public.talleres (
  id                       uuid primary key default gen_random_uuid(),
  nombre                   text not null check (length(trim(nombre)) between 2 and 120),
  slug                     text not null unique,
  identificacion_fiscal    text,
  direccion                text,
  telefono                 text,
  email                    text,
  zona_horaria             text not null default 'America/Caracas',
  moneda                   text not null default 'USD' check (length(moneda) = 3),
  tarifa_hora_default      numeric(12,2) not null default 0 check (tarifa_hora_default >= 0),
  impuesto_pct             numeric(5,2)  not null default 0 check (impuesto_pct between 0 and 100),
  prefijo_orden            text not null default 'MCH',
  dias_validez_presupuesto int not null default 15 check (dias_validez_presupuesto > 0),
  logo_url                 text,
  activo                   boolean not null default true,
  creado_en                timestamptz not null default now(),
  actualizado_en           timestamptz not null default now(),
  constraint talleres_slug_formato check (slug ~ '^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$'),
  constraint talleres_prefijo_formato check (prefijo_orden ~ '^[A-Z0-9]{2,6}$')
);

comment on table public.talleres is
  'Tenant raíz. Todo dato de negocio cuelga de un taller vía taller_id.';

create trigger mch_talleres_actualizado_en
  before update on public.talleres
  for each row execute function public.mch_set_actualizado_en();

-- -----------------------------------------------------------------------------
-- Secuencia de folios, separada de `talleres` a propósito
--
-- El folio ("MCH-00042") debe poder incrementarlo cualquier asesor al crear una
-- orden, pero `talleres` solo la puede modificar un administrador. Si el
-- contador viviera en `talleres`, la función que lo incrementa tendría que
-- poder escribir ahí, y eso abriría un hueco en esa restricción.
--
-- Esta tabla no lleva `force row level security` ni políticas: la escriben
-- únicamente funciones `security definer` (propiedad de postgres, que así omite
-- RLS) y el rol de servicio. Ningún usuario la alcanza.
-- -----------------------------------------------------------------------------

create table public.secuencias_folio (
  taller_id uuid primary key references public.talleres(id) on delete cascade,
  prefijo   text   not null,
  valor     bigint not null default 0
);

alter table public.secuencias_folio enable row level security;

create or replace function public.mch_sincronizar_secuencia_folio()
returns trigger
language plpgsql
security definer
set search_path = public
as $fn$
begin
  insert into public.secuencias_folio (taller_id, prefijo, valor)
  values (new.id, new.prefijo_orden, 0)
  on conflict (taller_id) do update set prefijo = excluded.prefijo;
  return null;
end;
$fn$;

create trigger mch_talleres_secuencia
  after insert or update of prefijo_orden on public.talleres
  for each row execute function public.mch_sincronizar_secuencia_folio();

create or replace function public.mch_siguiente_folio(p_taller_id uuid)
returns text
language plpgsql
security definer
set search_path = public
as $fn$
declare
  v_prefijo text;
  v_valor   bigint;
begin
  -- El UPDATE ... RETURNING toma un lock de fila: dos órdenes creadas a la vez
  -- en el mismo taller se serializan y no pueden recibir el mismo folio.
  update public.secuencias_folio
     set valor = valor + 1
   where taller_id = p_taller_id
  returning prefijo, valor into v_prefijo, v_valor;

  if not found then
    raise exception 'No existe secuencia de folios para el taller %', p_taller_id
      using errcode = 'foreign_key_violation';
  end if;

  return v_prefijo || '-' || lpad(v_valor::text, 5, '0');
end;
$fn$;

-- -----------------------------------------------------------------------------
-- Perfiles
-- -----------------------------------------------------------------------------

create table public.perfiles (
  id              uuid primary key references auth.users(id) on delete cascade,
  taller_id       uuid not null references public.talleres(id) on delete cascade,
  nombre_completo text not null check (length(trim(nombre_completo)) between 2 and 120),
  telefono        text,
  rol             public.rol_usuario not null,
  activo          boolean not null default true,
  creado_en       timestamptz not null default now(),
  actualizado_en  timestamptz not null default now()
);

comment on table public.perfiles is
  'Un usuario pertenece a exactamente un taller. Fuente de los claims del JWT.';

create index perfiles_taller_idx on public.perfiles (taller_id);
create index perfiles_taller_rol_idx on public.perfiles (taller_id, rol) where activo;

create trigger mch_perfiles_actualizado_en
  before update on public.perfiles
  for each row execute function public.mch_set_actualizado_en();

-- Impide que un usuario se ascienda a sí mismo o se cambie de taller.
-- La política de UPDATE deja a cada quien editar su propia fila (nombre,
-- teléfono); este guard protege las dos columnas que no debe poder tocar.
create or replace function public.mch_perfiles_guard()
returns trigger
language plpgsql
as $fn$
begin
  if (new.rol is distinct from old.rol or new.taller_id is distinct from old.taller_id)
     and public.mch_rol_actual() is not null
     and not public.mch_es_admin() then
    raise exception 'Solo un administrador del taller puede cambiar el rol o el taller de un perfil'
      using errcode = 'insufficient_privilege';
  end if;
  return new;
end;
$fn$;

create trigger mch_perfiles_guard
  before update on public.perfiles
  for each row execute function public.mch_perfiles_guard();

-- -----------------------------------------------------------------------------
-- RLS
-- -----------------------------------------------------------------------------

alter table public.talleres enable row level security;
alter table public.talleres force  row level security;
alter table public.perfiles enable row level security;
alter table public.perfiles force  row level security;

-- Un usuario ve su taller y nada más. Crear talleres es una operación de alta
-- que hace el backend con el rol de servicio: no hay política de INSERT.
create policy talleres_select on public.talleres
  for select to authenticated
  using (id = public.mch_taller_actual());

create policy talleres_update on public.talleres
  for update to authenticated
  using (id = public.mch_taller_actual() and public.mch_es_admin())
  with check (id = public.mch_taller_actual());

-- Cada quien lee su propia fila aunque aún no tenga claims (primer login), y
-- lee al resto de su taller para poder asignar técnicos y asesores.
create policy perfiles_select on public.perfiles
  for select to authenticated
  using (id = auth.uid() or taller_id = public.mch_taller_actual());

create policy perfiles_insert on public.perfiles
  for insert to authenticated
  with check (taller_id = public.mch_taller_actual() and public.mch_es_admin());

create policy perfiles_update on public.perfiles
  for update to authenticated
  using (id = auth.uid() or (taller_id = public.mch_taller_actual() and public.mch_es_admin()))
  with check (taller_id = public.mch_taller_actual());

create policy perfiles_delete on public.perfiles
  for delete to authenticated
  using (taller_id = public.mch_taller_actual() and public.mch_es_admin() and id <> auth.uid());
