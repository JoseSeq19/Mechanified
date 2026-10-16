# Matriz de permisos por rol

Lo que aparece aquí está implementado en las políticas RLS de
`supabase/migrations/`. El backend replicará estas reglas en
`app/core/permissions.py` para responder 403 con un mensaje claro, pero quien
las hace cumplir es Postgres.

Roles: **AD** admin_taller · **AS** asesor_servicio · **TE** tecnico ·
**ER** encargado_repuestos

`L` lectura · `E` escritura (insert/update) · `B` borrado · `—` sin acceso

| Recurso | AD | AS | TE | ER |
|---|:--:|:--:|:--:|:--:|
| `talleres` (configuración) | L E | L | L | L |
| `perfiles` | L E B | L | L | L |
| `clientes` | L E B | L E | L | L |
| `vehiculos` | L E B | L E | L E | L |
| `ordenes_servicio` | L E B | L E | L E | L E |
| `orden_eventos` | L | L | L | L |
| `diagnosticos` / `diagnostico_hallazgos` | L E | L | L E | L |
| `orden_mano_obra` | L E | L E | L E | L |
| `repuestos` (catálogo) | L E | L | L | L E |
| `orden_repuestos` | L E B | L E B | L (+ insert) | L E B |
| `presupuestos` / `presupuesto_items` | L E | L E | L | L |
| `checklist_plantillas` / items | L E | L | L | L |
| `controles_calidad` / respuestas | L E | L E | L E | L |
| `encuestas` | L E | L E | L | L |
| `notificaciones` | L (+ encolar) | L (+ encolar) | — | — |
| `adjuntos` | L E B | L E | L E | L E |

Notas sobre casos que no caben en la tabla:

- **`ordenes_servicio`** deja escribir a todo el taller. Qué puede cambiar cada
  rol lo decide `mch_ordenes_guard` para los estados (ver
  [flujo de estados](flujo-estados.md)) y el backend para los campos
  administrativos. Duplicar la matriz de transiciones dentro de la política la
  volvería ilegible y difícil de mantener sincronizada.
- **`orden_repuestos`**: el técnico puede *solicitar* piezas desde el móvil
  (INSERT) pero no modificar precios ni estados; eso queda para repuestos y
  asesoría.
- **Borrado de órdenes**: solo el administrador y solo mientras siga en
  `recibido`. Después el registro es historia y se cancela, no se borra.
- **Cada usuario** puede editar su propia fila de `perfiles` (nombre, teléfono).
  El trigger `mch_perfiles_guard` impide que se cambie el rol o el taller a sí
  mismo.
- **`notificaciones`**: encolar sí, marcar como enviada no. El avance de la cola
  es exclusivo del worker, que corre con el rol de servicio.
- **`adjuntos`** tiene políticas de SELECT, INSERT y DELETE, y **ninguna de
  UPDATE**: la evidencia no se corrige, se quita y se vuelve a subir. Borrar solo
  lo puede hacer quien subió el archivo o la administración del taller. La `E` de
  la tabla de arriba es, en esta fila, solo insertar.
- **`talleres`** no tiene política de INSERT para nadie. Crear un taller es
  tarea de sistema (`python -m app.alta_taller`), con el rol de servicio, porque
  el producto no es de registro abierto: las cuentas las crea el administrador de
  cada taller. Editar la configuración sí está en la aplicación, y solo para
  administración.
- **El objeto del bucket y su fila son dos barreras distintas.** La fila la
  filtra RLS por `taller_id`; el archivo lo filtra la política de
  `storage.objects` comparando la primera carpeta de su ruta. Lo que impide que
  las dos se contradigan es el trigger `mch_adjuntos_ruta_guard`.

## Roles de base de datos

| Rol | Uso |
|---|---|
| `anon` | Sin privilegio sobre ninguna tabla de `public`. Revocado explícitamente, incluidos los objetos futuros. |
| `authenticated` | Rol de las sesiones de usuario. Tiene privilegio de tabla; el filtrado real lo hacen las políticas. |
| `service_role` | Omite RLS. Reservado al worker de notificaciones, a los endpoints públicos por token y al alta de talleres. **Nunca** en el camino de un request de usuario. |
| `supabase_auth_admin` | Solo `select` sobre `perfiles`, para el hook que arma los claims. |
