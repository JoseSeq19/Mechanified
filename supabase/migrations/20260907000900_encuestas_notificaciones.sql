-- =============================================================================
-- Mechanified · 000900 · Encuestas de satisfacción y cola de notificaciones
-- =============================================================================

create table public.encuestas (
  id                uuid primary key default gen_random_uuid(),
  taller_id         uuid not null references public.talleres(id) on delete cascade,
  orden_id          uuid not null references public.ordenes_servicio(id) on delete cascade,
  token_publico     text not null default public.mch_token_publico(),
  enviada_en        timestamptz,
  respondida_en     timestamptz,
  puntaje_atencion  int check (puntaje_atencion between 1 and 5),
  puntaje_tiempo    int check (puntaje_tiempo   between 1 and 5),
  puntaje_calidad   int check (puntaje_calidad  between 1 and 5),
  recomendaria      int check (recomendaria between 0 and 10),
  comentario        text,
  creado_en         timestamptz not null default now()
);

-- Una encuesta por orden: reenviarla actualiza `enviada_en`, no crea otra fila.
create unique index encuestas_orden_uidx on public.encuestas (orden_id);
create unique index encuestas_token_uidx on public.encuestas (token_publico);
create index encuestas_taller_idx on public.encuestas (taller_id, respondida_en);

comment on table public.encuestas is
  'La fila la crea el backend al pasar la orden a entregado (Fase 4). No se '
  'genera por trigger porque la tabla lleva `force row level security` y un '
  'trigger `security definer` quedaría bloqueado por sus propias políticas.';

create trigger mch_encuestas_guard
  before insert or update of orden_id, taller_id on public.encuestas
  for each row execute function public.mch_hijo_orden_guard();

-- Sella la fecha de respuesta la primera vez que el cliente contesta.
create or replace function public.mch_encuestas_respuesta()
returns trigger
language plpgsql
as $fn$
begin
  if new.respondida_en is null
     and (new.puntaje_atencion is not null
          or new.puntaje_tiempo is not null
          or new.puntaje_calidad is not null
          or new.recomendaria is not null) then
    new.respondida_en := now();
  end if;
  return new;
end;
$fn$;

create trigger mch_encuestas_respuesta
  before update on public.encuestas
  for each row execute function public.mch_encuestas_respuesta();

-- -----------------------------------------------------------------------------
-- Cola de notificaciones
--
-- El envío no ocurre dentro de la transacción que cambia el estado de la orden:
-- se encola aquí y un worker la procesa. Si el proveedor de correo falla, la
-- orden ya quedó guardada y el reintento es responsabilidad del worker.
--
-- WhatsApp queda para una fase posterior, con la API oficial de WhatsApp
-- Business. Por eso `canal_notificacion` es un enum: sumar el canal será una
-- migración de una línea.
-- -----------------------------------------------------------------------------

create table public.notificaciones (
  id               uuid primary key default gen_random_uuid(),
  taller_id        uuid not null references public.talleres(id) on delete cascade,
  orden_id         uuid references public.ordenes_servicio(id) on delete cascade,
  canal            public.canal_notificacion not null default 'email',
  destinatario     text not null,
  plantilla        text not null,
  datos            jsonb not null default '{}'::jsonb,
  estado           public.estado_notificacion not null default 'pendiente',
  intentos         int not null default 0 check (intentos >= 0),
  ultimo_error     text,
  programada_para  timestamptz not null default now(),
  enviada_en       timestamptz,
  creado_en        timestamptz not null default now()
);

-- Índice que consulta el worker en cada ciclo.
create index notificaciones_pendientes_idx
  on public.notificaciones (programada_para)
  where estado = 'pendiente';
create index notificaciones_taller_idx on public.notificaciones (taller_id, creado_en desc);
create index notificaciones_orden_idx  on public.notificaciones (orden_id);

-- -----------------------------------------------------------------------------
-- RLS
-- -----------------------------------------------------------------------------

alter table public.encuestas      enable row level security;
alter table public.encuestas      force  row level security;
alter table public.notificaciones enable row level security;
alter table public.notificaciones force  row level security;

-- El taller lee sus encuestas; quien las responde es el cliente, sin sesión,
-- a través de un endpoint público que resuelve el token con el rol de servicio.
create policy encuestas_select on public.encuestas
  for select to authenticated
  using (taller_id = public.mch_taller_actual());

create policy encuestas_escritura on public.encuestas
  for all to authenticated
  using (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'asesor_servicio')
  )
  with check (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'asesor_servicio')
  );

create policy notificaciones_select on public.notificaciones
  for select to authenticated
  using (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'asesor_servicio')
  );

-- Encolar sí; marcar como enviada no. El avance de estado de la cola es
-- exclusivo del worker, que corre con el rol de servicio.
create policy notificaciones_insert on public.notificaciones
  for insert to authenticated
  with check (
    taller_id = public.mch_taller_actual()
    and public.mch_es_rol('admin_taller', 'asesor_servicio')
    and estado = 'pendiente'
  );
