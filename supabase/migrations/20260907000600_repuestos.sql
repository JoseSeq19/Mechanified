-- =============================================================================
-- Mechanified · 000600 · Catálogo de repuestos y consumo por orden
--
-- `orden_repuestos.repuesto_id` es opcional a propósito: en un taller real una
-- buena parte de las piezas se compran para un trabajo puntual y no vale la
-- pena darlas de alta en el catálogo. Cuando es NULL, la línea se sostiene con
-- su propia descripción y precio.
-- =============================================================================

create table public.repuestos (
  id             uuid primary key default gen_random_uuid(),
  taller_id      uuid not null references public.talleres(id) on delete cascade,
  sku            text not null,
  nombre         text not null check (length(trim(nombre)) between 2 and 160),
  descripcion    text,
  categoria      text,
  unidad         text not null default 'unidad',
  costo          numeric(12,2) not null default 0 check (costo >= 0),
  precio_venta   numeric(12,2) not null default 0 check (precio_venta >= 0),
  stock          numeric(12,2) not null default 0,
  stock_minimo   numeric(12,2) not null default 0 check (stock_minimo >= 0),
  proveedor      text,
  activo         boolean not null default true,
  creado_en      timestamptz not null default now(),
  actualizado_en timestamptz not null default now()
);

create unique index repuestos_taller_sku_uidx on public.repuestos (taller_id, upper(sku));
create index repuestos_taller_idx on public.repuestos (taller_id) where activo;
create index repuestos_busqueda_idx on public.repuestos
  using gin (to_tsvector('spanish', nombre || ' ' || coalesce(descripcion, '')));

create trigger mch_repuestos_actualizado_en
  before update on public.repuestos
  for each row execute function public.mch_set_actualizado_en();

-- -----------------------------------------------------------------------------

create table public.orden_repuestos (
  id              uuid primary key default gen_random_uuid(),
  taller_id       uuid not null references public.talleres(id) on delete cascade,
  orden_id        uuid not null references public.ordenes_servicio(id) on delete cascade,
  repuesto_id     uuid references public.repuestos(id) on delete set null,
  descripcion     text not null check (length(trim(descripcion)) >= 2),
  cantidad        numeric(12,2) not null check (cantidad > 0),
  precio_unitario numeric(12,2) not null check (precio_unitario >= 0),
  subtotal        numeric(12,2) generated always as (round(cantidad * precio_unitario, 2)) stored,
  estado          public.estado_item_repuesto not null default 'solicitado',
  notas           text,
  solicitado_por  uuid references public.perfiles(id) on delete set null,
  creado_en       timestamptz not null default now(),
  actualizado_en  timestamptz not null default now()
);

comment on column public.orden_repuestos.precio_unitario is
  'Copia del precio de venta al momento de agregar la pieza. Fijo, para que un '
  'cambio de lista de precios no altere presupuestos ya emitidos.';

create index orden_repuestos_orden_idx  on public.orden_repuestos (orden_id);
create index orden_repuestos_taller_idx on public.orden_repuestos (taller_id);
create index orden_repuestos_estado_idx on public.orden_repuestos (taller_id, estado);

create trigger mch_orden_repuestos_actualizado_en
  before update on public.orden_repuestos
  for each row execute function public.mch_set_actualizado_en();

create or replace function public.mch_orden_repuestos_guard()
returns trigger
language plpgsql
as $fn$
declare
  v_taller_orden    uuid;
  v_taller_repuesto uuid;
begin
  select taller_id into v_taller_orden
    from public.ordenes_servicio where id = new.orden_id;

  if v_taller_orden is distinct from new.taller_id then
    raise exception 'La orden % no pertenece al taller %', new.orden_id, new.taller_id
      using errcode = 'foreign_key_violation';
  end if;

  if new.repuesto_id is not null then
    select taller_id into v_taller_repuesto
      from public.repuestos where id = new.repuesto_id;

    if v_taller_repuesto is distinct from new.taller_id then
      raise exception 'El repuesto % no pertenece al taller %', new.repuesto_id, new.taller_id
        using errcode = 'foreign_key_violation';
    end if;
  end if;

  return new;
end;
$fn$;

create trigger mch_orden_repuestos_guard
  before insert or update of orden_id, repuesto_id, taller_id on public.orden_repuestos
  for each row execute function public.mch_orden_repuestos_guard();

-- -----------------------------------------------------------------------------
-- RLS
-- -----------------------------------------------------------------------------

alter table public.repuestos       enable row level security;
alter table public.repuestos       force  row level security;
alter table public.orden_repuestos enable row level security;
alter table public.orden_repuestos force  row level security;

-- Todo el taller consulta el catálogo; solo repuestos y administración lo editan.
create policy repuestos_select on public.repuestos
  for select to authenticated
  using (taller_id = public.mch_taller_actual());

create policy repuestos_escritura on public.repuestos
  for all to authenticated
  using (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'encargado_repuestos')
  )
  with check (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'encargado_repuestos')
  );

create policy orden_repuestos_select on public.orden_repuestos
  for select to authenticated
  using (taller_id = public.mch_taller_actual());

-- El técnico solicita piezas desde el móvil; repuestos y asesoría las cotizan
-- y actualizan su estado.
create policy orden_repuestos_insert on public.orden_repuestos
  for insert to authenticated
  with check (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'encargado_repuestos', 'asesor_servicio', 'tecnico')
  );

create policy orden_repuestos_update on public.orden_repuestos
  for update to authenticated
  using (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'encargado_repuestos', 'asesor_servicio')
  )
  with check (taller_id = public.mch_taller_actual());

create policy orden_repuestos_delete on public.orden_repuestos
  for delete to authenticated
  using (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'encargado_repuestos', 'asesor_servicio')
  );
