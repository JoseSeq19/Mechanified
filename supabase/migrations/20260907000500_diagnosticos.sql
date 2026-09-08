-- =============================================================================
-- Mechanified · 000500 · Diagnóstico y mano de obra
--
-- El diagnóstico se modela como cabecera + hallazgos en vez de un campo de
-- texto libre, porque cada hallazgo se cotiza y se aprueba por separado: el
-- cliente puede aceptar cambiar las pastillas y rechazar el amortiguador.
--
-- Se admite más de un diagnóstico por orden. Cuando aparece trabajo adicional
-- en plena reparación, se registra un diagnóstico nuevo en lugar de editar el
-- original, que ya respalda un presupuesto aprobado.
-- =============================================================================

-- Helper compartido por todas las tablas hijas de una orden: verifica que la
-- fila hija declare el mismo taller que su orden. La llave foránea apunta a la
-- fila, no al tenant, así que sin esto un taller podría colgar registros de la
-- orden de otro.
create or replace function public.mch_hijo_orden_guard()
returns trigger
language plpgsql
as $fn$
declare
  v_taller uuid;
begin
  select taller_id into v_taller
    from public.ordenes_servicio where id = new.orden_id;

  if v_taller is distinct from new.taller_id then
    raise exception 'La orden % no pertenece al taller %', new.orden_id, new.taller_id
      using errcode = 'foreign_key_violation';
  end if;
  return new;
end;
$fn$;

-- -----------------------------------------------------------------------------

create table public.diagnosticos (
  id              uuid primary key default gen_random_uuid(),
  taller_id       uuid not null references public.talleres(id) on delete cascade,
  orden_id        uuid not null references public.ordenes_servicio(id) on delete cascade,
  tecnico_id      uuid references public.perfiles(id) on delete set null,
  resumen         text not null check (length(trim(resumen)) >= 3),
  horas_estimadas numeric(6,2) not null default 0 check (horas_estimadas >= 0),
  creado_en       timestamptz not null default now(),
  actualizado_en  timestamptz not null default now()
);

create index diagnosticos_orden_idx  on public.diagnosticos (orden_id, creado_en desc);
create index diagnosticos_taller_idx on public.diagnosticos (taller_id);

create trigger mch_diagnosticos_actualizado_en
  before update on public.diagnosticos
  for each row execute function public.mch_set_actualizado_en();

create trigger mch_diagnosticos_guard
  before insert or update of orden_id, taller_id on public.diagnosticos
  for each row execute function public.mch_hijo_orden_guard();

create table public.diagnostico_hallazgos (
  id               uuid primary key default gen_random_uuid(),
  taller_id        uuid not null references public.talleres(id) on delete cascade,
  diagnostico_id   uuid not null references public.diagnosticos(id) on delete cascade,
  sistema          text not null,
  descripcion      text not null check (length(trim(descripcion)) >= 3),
  severidad        public.severidad_hallazgo not null default 'moderada',
  requiere_repuesto boolean not null default false,
  orden_visual     int not null default 0,
  creado_en        timestamptz not null default now()
);

create index hallazgos_diagnostico_idx on public.diagnostico_hallazgos (diagnostico_id, orden_visual);
create index hallazgos_taller_idx      on public.diagnostico_hallazgos (taller_id);

-- -----------------------------------------------------------------------------
-- Mano de obra
-- -----------------------------------------------------------------------------

create table public.orden_mano_obra (
  id          uuid primary key default gen_random_uuid(),
  taller_id   uuid not null references public.talleres(id) on delete cascade,
  orden_id    uuid not null references public.ordenes_servicio(id) on delete cascade,
  descripcion text not null check (length(trim(descripcion)) >= 3),
  horas       numeric(6,2)  not null check (horas > 0),
  tarifa_hora numeric(12,2) not null check (tarifa_hora >= 0),
  subtotal    numeric(12,2) generated always as (round(horas * tarifa_hora, 2)) stored,
  tecnico_id  uuid references public.perfiles(id) on delete set null,
  creado_en   timestamptz not null default now(),
  actualizado_en timestamptz not null default now()
);

comment on column public.orden_mano_obra.tarifa_hora is
  'Se copia de talleres.tarifa_hora_default al crear la línea, pero queda fija: '
  'subir la tarifa del taller no debe alterar órdenes ya cotizadas.';

create index mano_obra_orden_idx  on public.orden_mano_obra (orden_id);
create index mano_obra_taller_idx on public.orden_mano_obra (taller_id);

create trigger mch_mano_obra_actualizado_en
  before update on public.orden_mano_obra
  for each row execute function public.mch_set_actualizado_en();

create trigger mch_mano_obra_guard
  before insert or update of orden_id, taller_id on public.orden_mano_obra
  for each row execute function public.mch_hijo_orden_guard();

-- -----------------------------------------------------------------------------
-- RLS
-- -----------------------------------------------------------------------------

alter table public.diagnosticos          enable row level security;
alter table public.diagnosticos          force  row level security;
alter table public.diagnostico_hallazgos enable row level security;
alter table public.diagnostico_hallazgos force  row level security;
alter table public.orden_mano_obra       enable row level security;
alter table public.orden_mano_obra       force  row level security;

create policy diagnosticos_select on public.diagnosticos
  for select to authenticated
  using (taller_id = public.mch_taller_actual());

create policy diagnosticos_escritura on public.diagnosticos
  for all to authenticated
  using (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'tecnico')
  )
  with check (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'tecnico')
  );

create policy hallazgos_select on public.diagnostico_hallazgos
  for select to authenticated
  using (taller_id = public.mch_taller_actual());

create policy hallazgos_escritura on public.diagnostico_hallazgos
  for all to authenticated
  using (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'tecnico')
  )
  with check (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'tecnico')
  );

create policy mano_obra_select on public.orden_mano_obra
  for select to authenticated
  using (taller_id = public.mch_taller_actual());

create policy mano_obra_escritura on public.orden_mano_obra
  for all to authenticated
  using (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'tecnico', 'asesor_servicio')
  )
  with check (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'tecnico', 'asesor_servicio')
  );
