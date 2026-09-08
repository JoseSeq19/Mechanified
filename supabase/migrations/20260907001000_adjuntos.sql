-- =============================================================================
-- Mechanified · 001000 · Adjuntos y almacenamiento
--
-- Los archivos viven en Supabase Storage; esta tabla guarda solo los metadatos
-- para poder consultarlos con las mismas reglas de tenant que el resto.
--
-- Convención de rutas, y es la que sostiene la seguridad del bucket:
--     {taller_id}/{orden_id}/{uuid}-{nombre_archivo}
-- La primera carpeta es el tenant, así que la política de storage compara ese
-- segmento contra el taller del usuario.
-- =============================================================================

create table public.adjuntos (
  id             uuid primary key default gen_random_uuid(),
  taller_id      uuid not null references public.talleres(id) on delete cascade,
  orden_id       uuid not null references public.ordenes_servicio(id) on delete cascade,
  contexto       public.contexto_adjunto not null default 'ingreso',
  ruta_storage   text not null,
  nombre_archivo text not null,
  mime           text,
  tamano_bytes   bigint check (tamano_bytes >= 0),
  descripcion    text,
  subido_por     uuid references public.perfiles(id) on delete set null,
  creado_en      timestamptz not null default now()
);

create unique index adjuntos_ruta_uidx on public.adjuntos (ruta_storage);
create index adjuntos_orden_idx  on public.adjuntos (orden_id, contexto);
create index adjuntos_taller_idx on public.adjuntos (taller_id);

create trigger mch_adjuntos_guard
  before insert or update of orden_id, taller_id on public.adjuntos
  for each row execute function public.mch_hijo_orden_guard();

-- La ruta tiene que empezar por el taller declarado en la fila; de lo contrario
-- los metadatos podrían apuntar a un archivo de otro tenant.
create or replace function public.mch_adjuntos_ruta_guard()
returns trigger
language plpgsql
as $fn$
begin
  if split_part(new.ruta_storage, '/', 1) <> new.taller_id::text then
    raise exception 'La ruta % no comienza con el taller %',
      new.ruta_storage, new.taller_id
      using errcode = 'check_violation';
  end if;
  return new;
end;
$fn$;

create trigger mch_adjuntos_ruta_guard
  before insert or update of ruta_storage, taller_id on public.adjuntos
  for each row execute function public.mch_adjuntos_ruta_guard();

alter table public.adjuntos enable row level security;
alter table public.adjuntos force  row level security;

create policy adjuntos_select on public.adjuntos
  for select to authenticated
  using (taller_id = public.mch_taller_actual());

-- Cualquier rol del taller puede documentar: el técnico sube evidencia del
-- diagnóstico, el asesor las fotos de recepción.
create policy adjuntos_insert on public.adjuntos
  for insert to authenticated
  with check (taller_id = public.mch_taller_actual());

create policy adjuntos_delete on public.adjuntos
  for delete to authenticated
  using (
    taller_id = public.mch_taller_actual()
    and (public.mch_es_admin() or subido_por = auth.uid())
  );

-- -----------------------------------------------------------------------------
-- Bucket privado y sus políticas
-- -----------------------------------------------------------------------------

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'mch-evidencias',
  'mch-evidencias',
  false,
  26214400,  -- 25 MiB
  array['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'application/pdf']
)
on conflict (id) do nothing;

create policy mch_evidencias_select on storage.objects
  for select to authenticated
  using (
    bucket_id = 'mch-evidencias'
    and (storage.foldername(name))[1] = public.mch_taller_actual()::text
  );

create policy mch_evidencias_insert on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'mch-evidencias'
    and (storage.foldername(name))[1] = public.mch_taller_actual()::text
  );

create policy mch_evidencias_update on storage.objects
  for update to authenticated
  using (
    bucket_id = 'mch-evidencias'
    and (storage.foldername(name))[1] = public.mch_taller_actual()::text
  );

create policy mch_evidencias_delete on storage.objects
  for delete to authenticated
  using (
    bucket_id = 'mch-evidencias'
    and (storage.foldername(name))[1] = public.mch_taller_actual()::text
  );
