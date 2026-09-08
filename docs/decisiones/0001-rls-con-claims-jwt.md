# ADR 0001 — El tenant se resuelve desde los claims del JWT

**Fecha:** 2026-09-07 · **Estado:** aceptada

## Contexto

Toda política RLS necesita responder "¿de qué taller es este usuario?". Hay dos
formas de averiguarlo:

1. Consultar `perfiles` dentro de una función auxiliar.
2. Llevar `taller_id` y `rol` dentro del propio JWT y leerlos de ahí.

## Decisión

La opción 2. `mch_taller_actual()` y `mch_rol_actual()` leen
`current_setting('request.jwt.claims')`. Los claims los inyecta
`mch_hook_access_token()`, registrada como *custom access token hook* de
Supabase Auth, que sí consulta `perfiles` — una vez por emisión de token, no por
fila evaluada.

## Razones

**Recursión.** Si el helper consultara `perfiles`, y las políticas de `perfiles`
llamaran al helper, Postgres entra en bucle. Es el error más común al montar
multi-tenancy con RLS en Supabase.

**Costo.** Una política se evalúa por fila candidata. Un `SELECT` dentro del
helper multiplicaría el costo de cada consulta sobre tablas grandes como
`ordenes_servicio`.

**Falla cerrada.** Sin claims, los helpers devuelven NULL y toda política
deniega. Un hook mal configurado deja el sistema inaccesible, no abierto.

## Consecuencias

**Los cambios de rol no son inmediatos.** Los claims viajan dentro del token; si
un administrador cambia el rol de alguien, el cambio surte efecto al renovarse
el token (una hora por defecto). Cuando deba aplicarse ya, el backend tiene que
invalidar las sesiones de ese usuario. Queda pendiente para la Fase 2.

**El hook es infraestructura crítica.** Si se desactiva, nadie ve nada. Está en
`config.toml` para el entorno local y hay que activarlo también en
Authentication > Hooks al desplegar un proyecto hospedado.

**`perfiles` no lleva `force row level security` para `supabase_auth_admin`.**
Ese rol recibe una política de solo lectura sobre `perfiles` y el permiso de
ejecutar el hook, y nada más.

## Alternativa descartada

Consultar `perfiles` en una función `security definer` con caché de sesión.
Resolvía el costo pero no la recursión, y añadía un estado de sesión que el
pool de conexiones vuelve difícil de razonar.
