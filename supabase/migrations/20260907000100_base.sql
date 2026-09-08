-- =============================================================================
-- Mechanified · 000100 · Base
-- Extensiones, tipos enumerados y funciones de contexto.
--
-- Las funciones mch_taller_actual() y mch_rol_actual() son el cimiento de toda
-- la multi-tenancy: leen el tenant y el rol desde los claims del JWT, NO desde
-- una consulta a `perfiles`. Esto tiene dos razones:
--
--   1. Evita recursión infinita. Si el helper consultara `perfiles`, y las
--      políticas de `perfiles` llamaran al helper, Postgres entra en bucle.
--   2. Rendimiento. Una política se evalúa por fila; una consulta dentro del
--      helper multiplicaría el costo de cada SELECT.
--
-- Los claims los inyecta el hook de Auth definido en 001200_hook_auth.sql.
-- Si el hook no está activo, los helpers devuelven NULL y todas las políticas
-- deniegan: el sistema falla cerrado, nunca abierto.
-- =============================================================================

create extension if not exists pgcrypto with schema extensions;

-- -----------------------------------------------------------------------------
-- Tipos enumerados del dominio
-- -----------------------------------------------------------------------------

create type public.rol_usuario as enum (
  'admin_taller',
  'asesor_servicio',
  'tecnico',
  'encargado_repuestos'
);

create type public.estado_orden as enum (
  'recibido',
  'en_diagnostico',
  'presupuesto_pendiente',
  'aprobado',
  'en_reparacion',
  'control_calidad',
  'listo_para_entrega',
  'entregado',
  'cancelado'
);

create type public.estado_presupuesto as enum (
  'borrador',
  'enviado',
  'aprobado',
  'rechazado',
  'vencido'
);

create type public.severidad_hallazgo as enum ('leve', 'moderada', 'critica');

create type public.estado_item_repuesto as enum (
  'solicitado',
  'cotizado',
  'aprobado',
  'recibido',
  'instalado'
);

create type public.resultado_check as enum ('ok', 'no_ok', 'no_aplica');

create type public.tipo_cliente as enum ('persona', 'empresa');

create type public.canal_notificacion as enum ('email', 'webhook');

create type public.estado_notificacion as enum ('pendiente', 'enviada', 'fallida');

create type public.contexto_adjunto as enum (
  'ingreso',
  'diagnostico',
  'reparacion',
  'calidad',
  'entrega'
);

-- -----------------------------------------------------------------------------
-- Contexto de la sesión: claims del JWT
-- -----------------------------------------------------------------------------

create or replace function public.mch_claims()
returns jsonb
language sql
stable
as $$
  select coalesce(
    nullif(current_setting('request.jwt.claims', true), '')::jsonb,
    '{}'::jsonb
  );
$$;

comment on function public.mch_claims() is
  'Claims del JWT de la sesión actual, o un objeto vacío si no hay sesión.';

create or replace function public.mch_taller_actual()
returns uuid
language sql
stable
as $$
  select nullif(
    coalesce(
      public.mch_claims() ->> 'taller_id',
      public.mch_claims() -> 'app_metadata' ->> 'taller_id'
    ),
    ''
  )::uuid;
$$;

comment on function public.mch_taller_actual() is
  'Taller (tenant) del usuario autenticado. NULL fuera de una sesión de usuario.';

create or replace function public.mch_rol_actual()
returns public.rol_usuario
language sql
stable
as $$
  with reclamado as (
    select nullif(
      coalesce(
        public.mch_claims() ->> 'rol',
        public.mch_claims() -> 'app_metadata' ->> 'rol'
      ),
      ''
    ) as valor
  )
  -- Se valida contra enum_range antes de castear: un claim manipulado con un
  -- valor arbitrario devolvería NULL en vez de abortar la consulta con error.
  select case
           when r.valor = any (enum_range(null::public.rol_usuario)::text[])
             then r.valor::public.rol_usuario
         end
  from reclamado r;
$$;

comment on function public.mch_rol_actual() is
  'Rol del usuario autenticado. NULL si no hay sesión o el claim es inválido.';

create or replace function public.mch_es_rol(variadic p_roles public.rol_usuario[])
returns boolean
language sql
stable
as $$
  select coalesce(public.mch_rol_actual() = any (p_roles), false);
$$;

create or replace function public.mch_es_admin()
returns boolean
language sql
stable
as $$
  select public.mch_es_rol('admin_taller');
$$;

-- -----------------------------------------------------------------------------
-- Utilidades compartidas
-- -----------------------------------------------------------------------------

create or replace function public.mch_set_actualizado_en()
returns trigger
language plpgsql
as $$
begin
  new.actualizado_en := now();
  return new;
end;
$$;

-- Token opaco de 64 caracteres hexadecimales para los enlaces públicos de
-- aprobación de presupuesto y de encuesta. Se construye con gen_random_uuid()
-- para no depender del esquema donde viva pgcrypto.
create or replace function public.mch_token_publico()
returns text
language sql
volatile
as $$
  select replace(gen_random_uuid()::text, '-', '')
      || replace(gen_random_uuid()::text, '-', '');
$$;
