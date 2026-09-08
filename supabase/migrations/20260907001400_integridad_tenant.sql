-- =============================================================================
-- Mechanified · 001400 · Integridad de tenant en tablas de segundo nivel
--
-- Las tablas nieto (hallazgos, líneas de presupuesto, ítems de checklist,
-- respuestas de calidad) llevan su propio `taller_id` para que la política RLS
-- sea una comparación directa. El riesgo de esa denormalización es que las dos
-- referencias puedan discrepar: alguien podría insertar una fila con SU
-- taller_id pero apuntando al padre de OTRO taller.
--
-- La llave foránea no lo impide, porque apunta a la fila y no al tenant, y RLS
-- tampoco: la fila nueva pasa la política (su taller_id es el correcto) y el
-- padre solo se lee a través de la FK, que no evalúa políticas.
--
-- Este guard cierra esa vía comparando ambos taller_id en cada escritura.
-- =============================================================================

create or replace function public.mch_padre_taller_guard()
returns trigger
language plpgsql
as $fn$
declare
  v_tabla_padre  text := tg_argv[0];
  v_columna_fk   text := tg_argv[1];
  v_id_padre     uuid;
  v_taller_padre uuid;
begin
  v_id_padre := (to_jsonb(new) ->> v_columna_fk)::uuid;

  if v_id_padre is null then
    return new;
  end if;

  execute format('select taller_id from public.%I where id = $1', v_tabla_padre)
     into v_taller_padre
    using v_id_padre;

  if v_taller_padre is distinct from new.taller_id then
    raise exception '% % no pertenece al taller %',
      v_tabla_padre, v_id_padre, new.taller_id
      using errcode = 'foreign_key_violation';
  end if;

  return new;
end;
$fn$;

comment on function public.mch_padre_taller_guard is
  'Trigger genérico. Argumentos: nombre de la tabla padre y nombre de la '
  'columna de la llave foránea en la tabla hija.';

create trigger mch_hallazgos_taller_guard
  before insert or update of diagnostico_id, taller_id on public.diagnostico_hallazgos
  for each row execute function public.mch_padre_taller_guard('diagnosticos', 'diagnostico_id');

create trigger mch_presupuesto_items_taller_guard
  before insert or update of presupuesto_id, taller_id on public.presupuesto_items
  for each row execute function public.mch_padre_taller_guard('presupuestos', 'presupuesto_id');

create trigger mch_checklist_items_taller_guard
  before insert or update of plantilla_id, taller_id on public.checklist_plantilla_items
  for each row execute function public.mch_padre_taller_guard('checklist_plantillas', 'plantilla_id');

create trigger mch_control_respuestas_taller_guard
  before insert or update of control_id, taller_id on public.control_calidad_respuestas
  for each row execute function public.mch_padre_taller_guard('controles_calidad', 'control_id');

-- El vehículo de una orden ya se valida en mch_ordenes_guard; aquí se cubre el
-- caso inverso, mover un vehículo a un cliente de otro taller, que ya atiende
-- mch_vehiculos_guard. Ambos quedan cubiertos.
