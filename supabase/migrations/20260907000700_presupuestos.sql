-- =============================================================================
-- Mechanified · 000700 · Presupuestos
--
-- Dos decisiones que sostienen la trazabilidad del acuerdo con el cliente:
--
--   1. Versionado. Un presupuesto no se edita después de enviarse; si aparece
--      trabajo adicional se emite la versión siguiente sobre la misma orden.
--      Así queda registro de qué se le mostró al cliente y cuándo.
--
--   2. Ítems como fotografía. `presupuesto_items` no apunta a las líneas vivas
--      de mano de obra ni de repuestos: las copia. Si el cliente aprobó 480,00
--      ese documento sigue diciendo 480,00 aunque después cambie la tarifa por
--      hora o el precio de una pieza.
-- =============================================================================

create table public.presupuestos (
  id                   uuid primary key default gen_random_uuid(),
  taller_id            uuid not null references public.talleres(id) on delete cascade,
  orden_id             uuid not null references public.ordenes_servicio(id) on delete cascade,
  version              int not null,
  subtotal_mano_obra   numeric(12,2) not null default 0 check (subtotal_mano_obra >= 0),
  subtotal_repuestos   numeric(12,2) not null default 0 check (subtotal_repuestos >= 0),
  descuento            numeric(12,2) not null default 0 check (descuento >= 0),
  -- Sin DEFAULT a propósito: el trigger lo completa desde el taller cuando
  -- llega NULL. Con `default 0` no habría forma de distinguir "no lo indicaron"
  -- de "es exento", y un presupuesto sin impuesto quedaría gravado igual.
  impuesto_pct         numeric(5,2)  not null check (impuesto_pct between 0 and 100),
  impuesto_monto numeric(12,2) generated always as (
    round((subtotal_mano_obra + subtotal_repuestos - descuento) * impuesto_pct / 100, 2)
  ) stored,
  total numeric(12,2) generated always as (
    round(subtotal_mano_obra + subtotal_repuestos - descuento, 2)
    + round((subtotal_mano_obra + subtotal_repuestos - descuento) * impuesto_pct / 100, 2)
  ) stored,
  estado               public.estado_presupuesto not null default 'borrador',
  valido_hasta         date,
  token_publico        text not null default public.mch_token_publico(),
  enviado_en           timestamptz,
  respondido_en        timestamptz,
  comentario_cliente   text,
  creado_por           uuid references public.perfiles(id) on delete set null,
  creado_en            timestamptz not null default now(),
  actualizado_en       timestamptz not null default now(),
  constraint presupuestos_descuento_valido
    check (descuento <= subtotal_mano_obra + subtotal_repuestos)
);

create unique index presupuestos_orden_version_uidx on public.presupuestos (orden_id, version);
create unique index presupuestos_token_uidx on public.presupuestos (token_publico);
create index presupuestos_taller_estado_idx on public.presupuestos (taller_id, estado);
create index presupuestos_orden_idx on public.presupuestos (orden_id, version desc);

comment on column public.presupuestos.token_publico is
  'Identificador opaco del enlace de aprobación que recibe el cliente. No se '
  'expone por RLS: lo resuelve un endpoint público dedicado del backend.';

create table public.presupuesto_items (
  id              uuid primary key default gen_random_uuid(),
  taller_id       uuid not null references public.talleres(id) on delete cascade,
  presupuesto_id  uuid not null references public.presupuestos(id) on delete cascade,
  tipo            text not null check (tipo in ('mano_obra', 'repuesto')),
  descripcion     text not null,
  cantidad        numeric(12,2) not null check (cantidad > 0),
  precio_unitario numeric(12,2) not null check (precio_unitario >= 0),
  subtotal        numeric(12,2) generated always as (round(cantidad * precio_unitario, 2)) stored,
  orden_visual    int not null default 0
);

create index presupuesto_items_presupuesto_idx
  on public.presupuesto_items (presupuesto_id, orden_visual);
create index presupuesto_items_taller_idx on public.presupuesto_items (taller_id);

create trigger mch_presupuestos_actualizado_en
  before update on public.presupuestos
  for each row execute function public.mch_set_actualizado_en();

-- -----------------------------------------------------------------------------
-- Numeración de versiones y vigencia
-- -----------------------------------------------------------------------------

create or replace function public.mch_presupuestos_preparar()
returns trigger
language plpgsql
as $fn$
declare
  v_taller_orden uuid;
  v_dias         int;
  v_impuesto     numeric(5,2);
begin
  select taller_id into v_taller_orden
    from public.ordenes_servicio where id = new.orden_id;

  if v_taller_orden is distinct from new.taller_id then
    raise exception 'La orden % no pertenece al taller %', new.orden_id, new.taller_id
      using errcode = 'foreign_key_violation';
  end if;

  if new.version is null then
    select coalesce(max(version), 0) + 1 into new.version
      from public.presupuestos where orden_id = new.orden_id;
  end if;

  select dias_validez_presupuesto, impuesto_pct into v_dias, v_impuesto
    from public.talleres where id = new.taller_id;

  if new.valido_hasta is null then
    new.valido_hasta := (now() + make_interval(days => coalesce(v_dias, 15)))::date;
  end if;

  -- El impuesto se congela al crear el presupuesto, igual que los precios.
  -- Un 0 explícito se respeta: es un presupuesto exento, no un descuido.
  if new.impuesto_pct is null then
    new.impuesto_pct := coalesce(v_impuesto, 0);
  end if;

  return new;
end;
$fn$;

create trigger mch_presupuestos_preparar
  before insert on public.presupuestos
  for each row execute function public.mch_presupuestos_preparar();

-- -----------------------------------------------------------------------------
-- Inmutabilidad después del envío
-- -----------------------------------------------------------------------------

create or replace function public.mch_presupuestos_guard()
returns trigger
language plpgsql
as $fn$
begin
  if old.estado <> 'borrador' then
    -- Ya se le mostró al cliente: solo puede cambiar su desenlace.
    if new.subtotal_mano_obra is distinct from old.subtotal_mano_obra
       or new.subtotal_repuestos is distinct from old.subtotal_repuestos
       or new.descuento         is distinct from old.descuento
       or new.impuesto_pct      is distinct from old.impuesto_pct
       or new.version           is distinct from old.version
       or new.orden_id          is distinct from old.orden_id then
      raise exception
        'El presupuesto v% ya fue enviado: para cambiar montos hay que emitir una versión nueva',
        old.version
        using errcode = 'check_violation';
    end if;
  end if;

  if new.estado is distinct from old.estado then
    if old.estado in ('aprobado', 'rechazado') then
      raise exception 'El presupuesto ya fue respondido por el cliente (%)', old.estado
        using errcode = 'check_violation';
    end if;
    if new.estado in ('aprobado', 'rechazado') and new.respondido_en is null then
      new.respondido_en := now();
    end if;
    if new.estado = 'enviado' and new.enviado_en is null then
      new.enviado_en := now();
    end if;
  end if;

  return new;
end;
$fn$;

create trigger mch_presupuestos_guard
  before update on public.presupuestos
  for each row execute function public.mch_presupuestos_guard();

-- Las líneas se congelan junto con la cabecera.
create or replace function public.mch_presupuesto_items_guard()
returns trigger
language plpgsql
as $fn$
declare
  v_estado public.estado_presupuesto;
  v_id     uuid := coalesce(new.presupuesto_id, old.presupuesto_id);
begin
  select estado into v_estado from public.presupuestos where id = v_id;

  if v_estado is not null and v_estado <> 'borrador' then
    raise exception 'No se pueden modificar las líneas de un presupuesto en estado %', v_estado
      using errcode = 'check_violation';
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$fn$;

create trigger mch_presupuesto_items_guard
  before insert or update or delete on public.presupuesto_items
  for each row execute function public.mch_presupuesto_items_guard();

-- -----------------------------------------------------------------------------
-- RLS
-- -----------------------------------------------------------------------------

alter table public.presupuestos      enable row level security;
alter table public.presupuestos      force  row level security;
alter table public.presupuesto_items enable row level security;
alter table public.presupuesto_items force  row level security;

create policy presupuestos_select on public.presupuestos
  for select to authenticated
  using (taller_id = public.mch_taller_actual());

create policy presupuestos_escritura on public.presupuestos
  for all to authenticated
  using (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'asesor_servicio')
  )
  with check (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'asesor_servicio')
  );

create policy presupuesto_items_select on public.presupuesto_items
  for select to authenticated
  using (taller_id = public.mch_taller_actual());

create policy presupuesto_items_escritura on public.presupuesto_items
  for all to authenticated
  using (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'asesor_servicio')
  )
  with check (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'asesor_servicio')
  );
