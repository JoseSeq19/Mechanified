-- =============================================================================
-- Mechanified · 000800 · Control de calidad
--
-- El checklist es configurable por taller: cada uno define sus plantillas y sus
-- puntos de revisión. Al ejecutar un control se copian las respuestas contra
-- los ítems de la plantilla, de modo que editar la plantilla más adelante no
-- reescribe inspecciones ya realizadas.
-- =============================================================================

create table public.checklist_plantillas (
  id             uuid primary key default gen_random_uuid(),
  taller_id      uuid not null references public.talleres(id) on delete cascade,
  nombre         text not null check (length(trim(nombre)) between 2 and 120),
  descripcion    text,
  activo         boolean not null default true,
  creado_en      timestamptz not null default now(),
  actualizado_en timestamptz not null default now()
);

create unique index checklist_plantillas_taller_nombre_uidx
  on public.checklist_plantillas (taller_id, lower(nombre));
create index checklist_plantillas_taller_idx
  on public.checklist_plantillas (taller_id) where activo;

create trigger mch_checklist_plantillas_actualizado_en
  before update on public.checklist_plantillas
  for each row execute function public.mch_set_actualizado_en();

create table public.checklist_plantilla_items (
  id           uuid primary key default gen_random_uuid(),
  taller_id    uuid not null references public.talleres(id) on delete cascade,
  plantilla_id uuid not null references public.checklist_plantillas(id) on delete cascade,
  categoria    text,
  descripcion  text not null check (length(trim(descripcion)) >= 3),
  obligatorio  boolean not null default true,
  orden_visual int not null default 0
);

create index checklist_items_plantilla_idx
  on public.checklist_plantilla_items (plantilla_id, orden_visual);
create index checklist_items_taller_idx on public.checklist_plantilla_items (taller_id);

-- -----------------------------------------------------------------------------

create table public.controles_calidad (
  id            uuid primary key default gen_random_uuid(),
  taller_id     uuid not null references public.talleres(id) on delete cascade,
  orden_id      uuid not null references public.ordenes_servicio(id) on delete cascade,
  plantilla_id  uuid references public.checklist_plantillas(id) on delete set null,
  inspector_id  uuid references public.perfiles(id) on delete set null,
  resultado     text not null default 'pendiente'
                check (resultado in ('pendiente', 'aprobado', 'rechazado')),
  observaciones text,
  creado_en     timestamptz not null default now(),
  cerrado_en    timestamptz
);

create index controles_calidad_orden_idx  on public.controles_calidad (orden_id, creado_en desc);
create index controles_calidad_taller_idx on public.controles_calidad (taller_id, resultado);

create trigger mch_controles_calidad_guard
  before insert or update of orden_id, taller_id on public.controles_calidad
  for each row execute function public.mch_hijo_orden_guard();

create table public.control_calidad_respuestas (
  id           uuid primary key default gen_random_uuid(),
  taller_id    uuid not null references public.talleres(id) on delete cascade,
  control_id   uuid not null references public.controles_calidad(id) on delete cascade,
  item_id      uuid references public.checklist_plantilla_items(id) on delete set null,
  descripcion  text not null,
  resultado    public.resultado_check not null default 'no_aplica',
  comentario   text,
  evidencia_url text,
  orden_visual int not null default 0
);

create unique index control_respuestas_control_item_uidx
  on public.control_calidad_respuestas (control_id, item_id)
  where item_id is not null;
create index control_respuestas_control_idx
  on public.control_calidad_respuestas (control_id, orden_visual);
create index control_respuestas_taller_idx on public.control_calidad_respuestas (taller_id);

-- Un control no se cierra como aprobado si quedan puntos obligatorios en falta.
-- La verificación va aquí y no en el backend porque es la regla que impide
-- entregar un vehículo con una revisión a medias.
create or replace function public.mch_controles_calidad_cierre()
returns trigger
language plpgsql
as $fn$
declare
  v_pendientes int;
begin
  if new.resultado = 'aprobado' and old.resultado <> 'aprobado' then
    select count(*) into v_pendientes
      from public.control_calidad_respuestas r
      join public.checklist_plantilla_items i on i.id = r.item_id
     where r.control_id = new.id
       and i.obligatorio
       and r.resultado <> 'ok';

    if v_pendientes > 0 then
      raise exception
        'No se puede aprobar el control: quedan % puntos obligatorios sin conformidad',
        v_pendientes
        using errcode = 'check_violation';
    end if;

    if new.cerrado_en is null then
      new.cerrado_en := now();
    end if;
  end if;

  if new.resultado = 'rechazado' and new.cerrado_en is null then
    new.cerrado_en := now();
  end if;

  return new;
end;
$fn$;

create trigger mch_controles_calidad_cierre
  before update on public.controles_calidad
  for each row execute function public.mch_controles_calidad_cierre();

-- -----------------------------------------------------------------------------
-- RLS
-- -----------------------------------------------------------------------------

alter table public.checklist_plantillas       enable row level security;
alter table public.checklist_plantillas       force  row level security;
alter table public.checklist_plantilla_items  enable row level security;
alter table public.checklist_plantilla_items  force  row level security;
alter table public.controles_calidad          enable row level security;
alter table public.controles_calidad          force  row level security;
alter table public.control_calidad_respuestas enable row level security;
alter table public.control_calidad_respuestas force  row level security;

-- Las plantillas las consulta todo el taller (el técnico las ejecuta en el
-- móvil) pero solo administración las define.
create policy checklist_plantillas_select on public.checklist_plantillas
  for select to authenticated
  using (taller_id = public.mch_taller_actual());

create policy checklist_plantillas_escritura on public.checklist_plantillas
  for all to authenticated
  using (taller_id = public.mch_taller_actual() and public.mch_es_admin())
  with check (taller_id = public.mch_taller_actual() and public.mch_es_admin());

create policy checklist_items_select on public.checklist_plantilla_items
  for select to authenticated
  using (taller_id = public.mch_taller_actual());

create policy checklist_items_escritura on public.checklist_plantilla_items
  for all to authenticated
  using (taller_id = public.mch_taller_actual() and public.mch_es_admin())
  with check (taller_id = public.mch_taller_actual() and public.mch_es_admin());

create policy controles_calidad_select on public.controles_calidad
  for select to authenticated
  using (taller_id = public.mch_taller_actual());

create policy controles_calidad_escritura on public.controles_calidad
  for all to authenticated
  using (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'asesor_servicio', 'tecnico')
  )
  with check (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'asesor_servicio', 'tecnico')
  );

create policy control_respuestas_select on public.control_calidad_respuestas
  for select to authenticated
  using (taller_id = public.mch_taller_actual());

create policy control_respuestas_escritura on public.control_calidad_respuestas
  for all to authenticated
  using (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'asesor_servicio', 'tecnico')
  )
  with check (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'asesor_servicio', 'tecnico')
  );
