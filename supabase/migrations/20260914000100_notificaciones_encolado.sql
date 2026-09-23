-- =============================================================================
-- Mechanified · 20260914000100 · Encolado acotado de notificaciones
--
-- La política de inserción original (000900) dejaba encolar a administración y
-- asesoría, con cualquier destinatario y cualquier plantilla. Dos problemas:
--
--   1. Quien avisa de que el vehículo está listo es, casi siempre, el técnico
--      que acaba de aprobar el control de calidad. La política lo rechazaba, y
--      el aviso más útil para el cliente era justo el que no podía salir.
--
--   2. `authenticated` tiene privilegio de tabla, así que cualquiera con sesión
--      podía insertar filas directo por PostgREST, saltándose la API, y usar el
--      remitente del producto para escribir a una dirección arbitraria con el
--      texto que quisiera. La cola era un relé de correo abierto.
--
-- La regla nueva abre el encolado a todo el taller y a cambio ata la fila: el
-- destinatario tiene que ser el correo del cliente de esa orden, y la plantilla
-- una de las conocidas. En el peor caso, un empleado le reenvía a su propio
-- cliente un aviso legítimo de su propio taller.
--
-- El contenido no viaja en la fila: `datos` solo lleva referencias (qué
-- presupuesto, qué encuesta) y el worker arma el correo leyendo la base al
-- momento de enviar. Así, inventarse un `datos` no permite inventarse un texto
-- ni un enlace.
-- =============================================================================

alter table public.notificaciones
  add constraint notificaciones_plantilla_conocida
  check (plantilla in ('presupuesto_enviado', 'vehiculo_listo', 'encuesta_satisfaccion'));

comment on column public.notificaciones.datos is
  'Solo referencias (presupuesto_id, encuesta_id). El cuerpo del correo lo arma '
  'el worker leyendo la base: lo que se escriba aquí no acaba en el mensaje.';

drop policy notificaciones_insert on public.notificaciones;

create policy notificaciones_insert on public.notificaciones
  for insert to authenticated
  with check (
    taller_id = public.mch_taller_actual()
    -- El avance de la cola es exclusivo del worker, que corre con el rol de
    -- servicio: desde una sesión de usuario solo se puede encolar.
    and estado = 'pendiente'
    and intentos = 0
    and enviada_en is null
    and ultimo_error is null
    and orden_id is not null
    and exists (
      select 1
        from public.ordenes_servicio o
        join public.clientes c on c.id = o.cliente_id
       where o.id = notificaciones.orden_id
         and o.taller_id = notificaciones.taller_id
         and lower(c.email) = lower(notificaciones.destinatario)
    )
  );
