# Modelo de datos

Fuente de verdad: `supabase/migrations/*.sql`. Este documento explica el porqué;
el SQL manda sobre cualquier discrepancia.

## Principios

**El taller es el tenant.** Toda tabla de negocio lleva `taller_id`, incluso
cuando podría deducirse por JOIN. Cuesta una columna y un índice, y a cambio
cada política RLS es una comparación simple sobre una columna indexada en vez
de una subconsulta que se evalúa por fila.

**Los documentos se congelan.** Precios, tarifas e impuestos se copian a la
línea en el momento de crearla. Un cambio en el catálogo o en la tarifa por hora
no puede alterar lo que ya se le cotizó a un cliente.

**El historial es append-only.** `orden_eventos` no admite UPDATE ni DELETE. De
ahí salen las métricas de tiempo del dashboard.

## Tablas

### Tenant e identidad

| Tabla | Propósito |
|---|---|
| `talleres` | Organización raíz. Configuración: moneda, tarifa por hora, impuesto, prefijo de folio, vigencia de presupuestos. |
| `perfiles` | Usuario de la aplicación, 1:1 con `auth.users`. Lleva `taller_id` y `rol`. Es la tabla que lee el hook de Auth. |
| `secuencias_folio` | Contador de folios por taller. Tabla interna, sin políticas: la escriben solo funciones `security definer`. |

### Clientes y vehículos

| Tabla | Notas |
|---|---|
| `clientes` | Persona o empresa. `documento` único dentro del taller. Índice GIN para búsqueda por nombre. |
| `vehiculos` | Único por `(taller_id, placa)` y por `(taller_id, vin)`. El historial del vehículo se obtiene consultando sus órdenes, no con una tabla aparte: así sobrevive a un cambio de dueño. |

### Flujo de servicio

| Tabla | Notas |
|---|---|
| `ordenes_servicio` | Entidad central. `folio` legible y único por taller, asignado por trigger. `total` es columna generada. |
| `orden_eventos` | Bitácora de transiciones. Solo lectura para los usuarios. |
| `diagnosticos` | Cabecera. Se admite más de uno por orden: el trabajo adicional descubierto en reparación se registra como diagnóstico nuevo. |
| `diagnostico_hallazgos` | Detalle. Cada hallazgo se cotiza y aprueba por separado. |
| `orden_mano_obra` | Líneas de trabajo. `subtotal` generado como `horas × tarifa_hora`. |

### Repuestos

| Tabla | Notas |
|---|---|
| `repuestos` | Catálogo del taller. `sku` único por taller. |
| `orden_repuestos` | Piezas de una orden. `repuesto_id` es opcional: buena parte de las piezas se compran para un trabajo puntual y no entran al catálogo. |

### Presupuesto

| Tabla | Notas |
|---|---|
| `presupuestos` | Versionado por orden. Una vez enviado no admite cambios de monto: se emite la versión siguiente. `impuesto_monto` y `total` son columnas generadas. `token_publico` da acceso al enlace de aprobación. |
| `presupuesto_items` | Fotografía de las líneas al emitir. No apunta a `orden_mano_obra` ni a `orden_repuestos`: las copia. |

### Calidad y postventa

| Tabla | Notas |
|---|---|
| `checklist_plantillas` / `checklist_plantilla_items` | Checklist configurable por taller. |
| `controles_calidad` | Ejecución de un checklist. No se puede aprobar con puntos obligatorios sin conformidad; lo impide un trigger. |
| `control_calidad_respuestas` | Respuesta por punto, con evidencia opcional. |
| `encuestas` | Una por orden. Puntajes 1-5 y recomendación 0-10. |

### Soporte

| Tabla | Notas |
|---|---|
| `notificaciones` | Cola con reintentos. Los usuarios encolan; solo el worker avanza el estado. |
| `adjuntos` | Metadatos de archivos en Storage. Ruta: `{taller_id}/{orden_id}/{uuid}-{nombre}`. |

## Relaciones

```
talleres ─┬─ perfiles
          ├─ secuencias_folio (1:1)
          ├─ clientes ── vehiculos
          ├─ repuestos
          ├─ checklist_plantillas ── checklist_plantilla_items
          └─ ordenes_servicio ─┬─ orden_eventos
                               ├─ diagnosticos ── diagnostico_hallazgos
                               ├─ orden_mano_obra
                               ├─ orden_repuestos ──? repuestos
                               ├─ presupuestos ── presupuesto_items
                               ├─ controles_calidad ── control_calidad_respuestas
                               ├─ encuestas (1:1)
                               ├─ notificaciones
                               └─ adjuntos
```

## Row Level Security

Habilitada en las 21 tablas. `force row level security` en 19; las dos
excepciones son deliberadas y están documentadas en su migración:

- **`orden_eventos`** — la escribe un trigger `security definer` que corre como
  `postgres`. Con `force` activo, el dueño también queda sujeto a las políticas
  y, como no existe ninguna de INSERT, el trigger fallaría.
- **`secuencias_folio`** — misma razón, con `mch_siguiente_folio()`.

Ambas quedan igualmente inalcanzables para los usuarios: la primera es solo
lectura por política, y a la segunda se le revocó el privilegio de tabla.

### Cómo resuelve el tenant una política

```sql
using (taller_id = public.mch_taller_actual())
```

`mch_taller_actual()` lee `taller_id` de los claims del JWT, no de una consulta
a `perfiles`. Ver [ADR 0001](decisiones/0001-rls-con-claims-jwt.md).

## Integridad entre tablas

Las llaves foráneas apuntan a una fila, no a un tenant, así que por sí solas no
impiden que una fila hija declare un `taller_id` distinto al de su padre. Lo
cubren estos triggers:

| Trigger | Verifica |
|---|---|
| `mch_hijo_orden_guard` | La fila hija y su orden son del mismo taller. |
| `mch_padre_taller_guard` | Genérico para tablas de segundo nivel (hallazgos, líneas de presupuesto, ítems de checklist, respuestas de calidad). |
| `mch_vehiculos_guard` | El vehículo no queda bajo un cliente de otro taller. |
| `mch_ordenes_guard` | Cliente y vehículo son del taller, y el vehículo es de ese cliente. |
| `mch_orden_repuestos_guard` | El repuesto del catálogo es del mismo taller. |
| `mch_adjuntos_ruta_guard` | La ruta en Storage empieza por el `taller_id` de la fila. |
