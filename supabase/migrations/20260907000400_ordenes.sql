-- =============================================================================
-- Mechanified · 000400 · Órdenes de servicio y bitácora de estados
--
-- La máquina de estados vive aquí, en la base de datos, y no solo en el
-- backend. Un salto inválido (por ejemplo `recibido` -> `entregado`) queda
-- bloqueado aunque alguien escriba directo contra Postgres, desde un script de
-- migración de datos o desde el SQL Editor. El backend replica la misma tabla
-- de transiciones para dar mensajes de error útiles antes de tocar la base.
-- =============================================================================

create table public.ordenes_servicio (
  id                  uuid primary key default gen_random_uuid(),
  taller_id           uuid not null references public.talleres(id) on delete cascade,
  folio               text not null,
  cliente_id          uuid not null references public.clientes(id)  on delete restrict,
  vehiculo_id         uuid not null references public.vehiculos(id) on delete restrict,
  asesor_id           uuid references public.perfiles(id) on delete set null,
  tecnico_id          uuid references public.perfiles(id) on delete set null,
  estado              public.estado_orden not null default 'recibido',
  motivo_ingreso      text not null check (length(trim(motivo_ingreso)) >= 3),
  kilometraje_ingreso int check (kilometraje_ingreso >= 0),
  nivel_combustible   int check (nivel_combustible between 0 and 100),
  inventario_ingreso  jsonb not null default '{}'::jsonb,
  fecha_ingreso       timestamptz not null default now(),
  fecha_promesa       timestamptz,
  fecha_entrega       timestamptz,
  total_mano_obra     numeric(12,2) not null default 0 check (total_mano_obra >= 0),
  total_repuestos     numeric(12,2) not null default 0 check (total_repuestos >= 0),
  total               numeric(12,2) generated always as (total_mano_obra + total_repuestos) stored,
  notas_internas      text,
  motivo_cancelacion  text,
  creado_por          uuid references public.perfiles(id) on delete set null,
  creado_en           timestamptz not null default now(),
  actualizado_en      timestamptz not null default now()
);

comment on table public.ordenes_servicio is
  'Entidad central del flujo de taller. El folio es único y legible por taller.';

create unique index ordenes_taller_folio_uidx on public.ordenes_servicio (taller_id, folio);
create index ordenes_taller_estado_idx on public.ordenes_servicio (taller_id, estado);
create index ordenes_vehiculo_idx  on public.ordenes_servicio (vehiculo_id, fecha_ingreso desc);
create index ordenes_cliente_idx   on public.ordenes_servicio (cliente_id);
create index ordenes_tecnico_idx   on public.ordenes_servicio (taller_id, tecnico_id)
  where estado not in ('entregado', 'cancelado');

create trigger mch_ordenes_actualizado_en
  before update on public.ordenes_servicio
  for each row execute function public.mch_set_actualizado_en();

-- -----------------------------------------------------------------------------
-- Bitácora de estados: append-only
--
-- De aquí salen las métricas de tiempo del dashboard (cuánto tardó cada orden
-- en cada etapa). Por eso no admite UPDATE ni DELETE: no hay política que los
-- permita, y las filas las escribe únicamente el trigger de más abajo.
--
-- La tabla NO lleva `force row level security` a propósito. El trigger que la
-- escribe es `security definer` y corre como postgres, dueño de la tabla; con
-- `force` activo el dueño también quedaría sujeto a las políticas y, como no
-- existe ninguna de INSERT, el trigger fallaría.
-- -----------------------------------------------------------------------------

create table public.orden_eventos (
  id              uuid primary key default gen_random_uuid(),
  taller_id       uuid not null references public.talleres(id) on delete cascade,
  orden_id        uuid not null references public.ordenes_servicio(id) on delete cascade,
  estado_anterior public.estado_orden,
  estado_nuevo    public.estado_orden not null,
  usuario_id      uuid references public.perfiles(id) on delete set null,
  comentario      text,
  creado_en       timestamptz not null default now()
);

create index orden_eventos_orden_idx  on public.orden_eventos (orden_id, creado_en);
create index orden_eventos_taller_idx on public.orden_eventos (taller_id, creado_en desc);

-- -----------------------------------------------------------------------------
-- Máquina de estados
-- -----------------------------------------------------------------------------

create or replace function public.mch_transicion_valida(
  p_anterior public.estado_orden,
  p_nuevo    public.estado_orden
)
returns boolean
language sql
immutable
as $fn$
  select case p_anterior
    when 'recibido'              then p_nuevo in ('en_diagnostico', 'cancelado')
    when 'en_diagnostico'        then p_nuevo in ('presupuesto_pendiente', 'cancelado')
    when 'presupuesto_pendiente' then p_nuevo in ('aprobado', 'en_diagnostico', 'cancelado')
    when 'aprobado'              then p_nuevo in ('en_reparacion', 'cancelado')
    -- Trabajo adicional descubierto en plena reparación: vuelve a presupuesto
    -- y se emite una nueva versión, en vez de ampliar el monto ya aprobado.
    when 'en_reparacion'         then p_nuevo in ('control_calidad', 'presupuesto_pendiente')
    when 'control_calidad'       then p_nuevo in ('listo_para_entrega', 'en_reparacion')
    when 'listo_para_entrega'    then p_nuevo in ('entregado')
    when 'entregado'             then false
    when 'cancelado'             then false
  end;
$fn$;

comment on function public.mch_transicion_valida is
  'Transiciones permitidas del flujo de taller. Estados terminales: entregado, cancelado.';

create or replace function public.mch_rol_puede_transicionar(
  p_rol      public.rol_usuario,
  p_anterior public.estado_orden,
  p_nuevo    public.estado_orden
)
returns boolean
language sql
immutable
as $fn$
  select case
    when p_rol = 'admin_taller' then true
    when p_nuevo = 'cancelado'  then p_rol = 'asesor_servicio'
    when p_anterior = 'recibido'              and p_nuevo = 'en_diagnostico'
      then p_rol = 'asesor_servicio'
    when p_anterior = 'en_diagnostico'        and p_nuevo = 'presupuesto_pendiente'
      then p_rol = 'tecnico'
    when p_anterior = 'presupuesto_pendiente' and p_nuevo in ('aprobado', 'en_diagnostico')
      then p_rol = 'asesor_servicio'
    when p_anterior = 'aprobado'              and p_nuevo = 'en_reparacion'
      then p_rol in ('asesor_servicio', 'tecnico')
    when p_anterior = 'en_reparacion'
      then p_rol = 'tecnico'
    when p_anterior = 'control_calidad'
      then p_rol in ('asesor_servicio', 'tecnico')
    when p_anterior = 'listo_para_entrega'    and p_nuevo = 'entregado'
      then p_rol = 'asesor_servicio'
    else false
  end;
$fn$;

create or replace function public.mch_ordenes_guard()
returns trigger
language plpgsql
as $fn$
declare
  v_rol             public.rol_usuario := public.mch_rol_actual();
  v_taller_cliente  uuid;
  v_taller_vehiculo uuid;
  v_cliente_vehiculo uuid;
begin
  if tg_op = 'INSERT' then
    if new.estado <> 'recibido' then
      raise exception 'Una orden nueva siempre nace en estado recibido, no en %', new.estado
        using errcode = 'check_violation';
    end if;

    if new.folio is null then
      new.folio := public.mch_siguiente_folio(new.taller_id);
    end if;
  end if;

  -- Coherencia de tenant: ni el cliente ni el vehículo pueden ser de otro
  -- taller, y el vehículo tiene que ser de ese cliente.
  select taller_id into v_taller_cliente
    from public.clientes where id = new.cliente_id;
  select taller_id, cliente_id into v_taller_vehiculo, v_cliente_vehiculo
    from public.vehiculos where id = new.vehiculo_id;

  if v_taller_cliente is distinct from new.taller_id
     or v_taller_vehiculo is distinct from new.taller_id then
    raise exception 'El cliente o el vehículo no pertenecen al taller %', new.taller_id
      using errcode = 'foreign_key_violation';
  end if;

  if v_cliente_vehiculo is distinct from new.cliente_id then
    raise exception 'El vehículo % no está registrado a nombre del cliente %',
      new.vehiculo_id, new.cliente_id
      using errcode = 'foreign_key_violation';
  end if;

  if tg_op = 'UPDATE' and new.estado is distinct from old.estado then
    if not public.mch_transicion_valida(old.estado, new.estado) then
      raise exception 'Transición de estado inválida: % -> %', old.estado, new.estado
        using errcode = 'check_violation';
    end if;

    -- v_rol es NULL cuando no hay sesión de usuario: migraciones, seed y el
    -- worker de notificaciones. En ese caso solo se valida que la transición
    -- exista; la autorización por rol aplica al tráfico de usuarios reales.
    if v_rol is not null
       and not public.mch_rol_puede_transicionar(v_rol, old.estado, new.estado) then
      raise exception 'El rol % no puede pasar la orden de % a %', v_rol, old.estado, new.estado
        using errcode = 'insufficient_privilege';
    end if;

    if new.estado = 'entregado' and new.fecha_entrega is null then
      new.fecha_entrega := now();
    end if;

    if new.estado = 'cancelado' and coalesce(trim(new.motivo_cancelacion), '') = '' then
      raise exception 'Cancelar una orden exige registrar el motivo'
        using errcode = 'check_violation';
    end if;
  end if;

  return new;
end;
$fn$;

create trigger mch_ordenes_guard
  before insert or update on public.ordenes_servicio
  for each row execute function public.mch_ordenes_guard();

create or replace function public.mch_ordenes_bitacora()
returns trigger
language plpgsql
security definer
set search_path = public
as $fn$
begin
  if tg_op = 'INSERT' then
    insert into public.orden_eventos (taller_id, orden_id, estado_anterior, estado_nuevo, usuario_id)
    values (new.taller_id, new.id, null, new.estado, auth.uid());
  elsif new.estado is distinct from old.estado then
    insert into public.orden_eventos (taller_id, orden_id, estado_anterior, estado_nuevo, usuario_id, comentario)
    values (new.taller_id, new.id, old.estado, new.estado, auth.uid(),
            case when new.estado = 'cancelado' then new.motivo_cancelacion end);
  end if;
  return null;
end;
$fn$;

create trigger mch_ordenes_bitacora
  after insert or update on public.ordenes_servicio
  for each row execute function public.mch_ordenes_bitacora();

-- -----------------------------------------------------------------------------
-- RLS
-- -----------------------------------------------------------------------------

alter table public.ordenes_servicio enable row level security;
alter table public.ordenes_servicio force  row level security;
alter table public.orden_eventos    enable row level security;

create policy ordenes_select on public.ordenes_servicio
  for select to authenticated
  using (taller_id = public.mch_taller_actual());

create policy ordenes_insert on public.ordenes_servicio
  for insert to authenticated
  with check (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'asesor_servicio')
  );

-- La política deja escribir a todo el taller; qué puede cambiar cada rol lo
-- resuelve mch_ordenes_guard (estados) y el backend (campos administrativos).
-- Separarlo así evita duplicar la matriz de transiciones dentro de la política.
create policy ordenes_update on public.ordenes_servicio
  for update to authenticated
  using (taller_id = public.mch_taller_actual())
  with check (taller_id = public.mch_taller_actual());

create policy ordenes_delete on public.ordenes_servicio
  for delete to authenticated
  using (
    taller_id = public.mch_taller_actual()
    and public.mch_es_admin()
    and estado = 'recibido'
  );

-- Solo lectura. Sin políticas de INSERT/UPDATE/DELETE: la bitácora la escribe
-- exclusivamente el trigger.
create policy orden_eventos_select on public.orden_eventos
  for select to authenticated
  using (taller_id = public.mch_taller_actual());
