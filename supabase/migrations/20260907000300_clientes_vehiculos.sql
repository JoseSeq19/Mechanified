-- =============================================================================
-- Mechanified · 000300 · Clientes y vehículos
-- El historial "por placa/VIN" no es una tabla aparte: sale de consultar las
-- órdenes de servicio del vehículo, que es lo que conserva la trazabilidad
-- aunque el vehículo cambie de dueño.
-- =============================================================================

create table public.clientes (
  id             uuid primary key default gen_random_uuid(),
  taller_id      uuid not null references public.talleres(id) on delete cascade,
  tipo           public.tipo_cliente not null default 'persona',
  nombre         text not null check (length(trim(nombre)) between 2 and 160),
  documento      text,
  telefono       text,
  email          text,
  direccion      text,
  notas          text,
  activo         boolean not null default true,
  creado_en      timestamptz not null default now(),
  actualizado_en timestamptz not null default now(),
  constraint clientes_email_formato
    check (email is null or email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$')
);

-- Un mismo documento no se repite dentro de un taller, pero dos talleres
-- distintos sí pueden tener al mismo cliente: el índice incluye taller_id.
create unique index clientes_taller_documento_uidx
  on public.clientes (taller_id, documento)
  where documento is not null;

create index clientes_taller_idx on public.clientes (taller_id);
create index clientes_busqueda_idx on public.clientes
  using gin (to_tsvector('spanish', nombre));

create trigger mch_clientes_actualizado_en
  before update on public.clientes
  for each row execute function public.mch_set_actualizado_en();

create table public.vehiculos (
  id                  uuid primary key default gen_random_uuid(),
  taller_id           uuid not null references public.talleres(id) on delete cascade,
  cliente_id          uuid not null references public.clientes(id) on delete restrict,
  placa               text not null check (length(trim(placa)) between 4 and 12),
  vin                 text,
  marca               text not null,
  modelo              text not null,
  anio                int check (anio between 1900 and 2100),
  color               text,
  tipo_combustible    text,
  transmision         text,
  kilometraje_ultimo  int check (kilometraje_ultimo >= 0),
  notas               text,
  activo              boolean not null default true,
  creado_en           timestamptz not null default now(),
  actualizado_en      timestamptz not null default now()
);

create unique index vehiculos_taller_placa_uidx on public.vehiculos (taller_id, upper(placa));
create unique index vehiculos_taller_vin_uidx
  on public.vehiculos (taller_id, upper(vin))
  where vin is not null;

create index vehiculos_taller_idx on public.vehiculos (taller_id);
create index vehiculos_cliente_idx on public.vehiculos (cliente_id);

create trigger mch_vehiculos_actualizado_en
  before update on public.vehiculos
  for each row execute function public.mch_set_actualizado_en();

-- Un vehículo no puede quedar bajo un cliente de otro taller. La FK sola no lo
-- impide porque apunta a la fila, no al tenant.
create or replace function public.mch_vehiculos_guard()
returns trigger
language plpgsql
as $fn$
declare
  v_taller_cliente uuid;
begin
  select taller_id into v_taller_cliente
    from public.clientes where id = new.cliente_id;

  if v_taller_cliente is distinct from new.taller_id then
    raise exception 'El cliente % no pertenece al taller %', new.cliente_id, new.taller_id
      using errcode = 'foreign_key_violation';
  end if;
  return new;
end;
$fn$;

create trigger mch_vehiculos_guard
  before insert or update of cliente_id, taller_id on public.vehiculos
  for each row execute function public.mch_vehiculos_guard();

-- -----------------------------------------------------------------------------
-- RLS
-- -----------------------------------------------------------------------------

alter table public.clientes  enable row level security;
alter table public.clientes  force  row level security;
alter table public.vehiculos enable row level security;
alter table public.vehiculos force  row level security;

-- Todos los roles del taller consultan clientes y vehículos: el técnico
-- necesita ver de qué carro habla la orden que tiene asignada.
create policy clientes_select on public.clientes
  for select to authenticated
  using (taller_id = public.mch_taller_actual());

create policy clientes_insert on public.clientes
  for insert to authenticated
  with check (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'asesor_servicio')
  );

create policy clientes_update on public.clientes
  for update to authenticated
  using (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'asesor_servicio')
  )
  with check (taller_id = public.mch_taller_actual());

create policy clientes_delete on public.clientes
  for delete to authenticated
  using (taller_id = public.mch_taller_actual() and public.mch_es_admin());

create policy vehiculos_select on public.vehiculos
  for select to authenticated
  using (taller_id = public.mch_taller_actual());

create policy vehiculos_insert on public.vehiculos
  for insert to authenticated
  with check (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'asesor_servicio')
  );

create policy vehiculos_update on public.vehiculos
  for update to authenticated
  using (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'asesor_servicio', 'tecnico')
  )
  with check (taller_id = public.mch_taller_actual());

create policy vehiculos_delete on public.vehiculos
  for delete to authenticated
  using (taller_id = public.mch_taller_actual() and public.mch_es_admin());
