# Mechanified — convenciones del proyecto

Producto propio y original. No replicar nombres, textos, flujos ni interfaces de
productos comerciales existentes.

## Idioma

- **Dominio en español**: tablas, columnas, enums, módulos, esquemas Pydantic,
  rutas de API y textos de UI (`ordenes_servicio`, `estado`, `presupuesto`).
- **Inglés solo donde lo impone el framework**: palabras clave de SQL, nombres de
  librerías, `main.py`, `router`, `schemas`, `model_config`.
- Sin acentos ni `ñ` en identificadores de código o base de datos
  (`diagnosticos`, no `diagnósticos`). Los acentos van en textos visibles.

## Base de datos

- La fuente de verdad del esquema es `supabase/migrations/*.sql`. **Nunca**
  generar migraciones desde los modelos SQLAlchemy: esos modelos son mapeo de
  lectura para el backend, no definen el esquema.
- Toda migración es aditiva y versionada. No editar una migración ya aplicada;
  crear una nueva.
- Prefijo `mch_` para funciones y triggers propios, para distinguirlos de los
  objetos de Supabase.
- Toda tabla de negocio lleva `taller_id` denormalizado, aunque se pueda deducir
  por JOIN. Es lo que permite que cada política RLS sea una comparación simple
  con índice.
- Toda tabla de negocio: `enable row level security` + `force row level security`.
  Las dos excepciones (`orden_eventos`, `secuencias_folio`) están documentadas en
  sus migraciones y existen porque triggers `security definer` deben escribir en
  ellas.

## Backend

- Un paquete por entidad en `app/modules/<entidad>/` con
  `models.py`, `schemas.py`, `service.py`, `router.py`.
- La lógica de negocio vive en `service.py`. Los routers solo validan, delegan y
  serializan.
- **Nunca** usar la llave `service_role` para tráfico de usuarios. Cada request
  abre transacción con `SET LOCAL role authenticated` y los claims JWT del
  usuario, de modo que RLS es la barrera real. `service_role` se reserva para el
  worker de notificaciones y tareas de sistema.
- Credenciales siempre por variable de entorno. Nada de valores por defecto
  reales en el código.

## Frontend

- Sistema de diseño propio en `web/src/components/ui/`, con tokens en
  `web/src/styles/tokens.css`. No incorporar librerías de componentes con
  identidad visual propia.
- Una carpeta por dominio en `src/features/<entidad>/`.

## Pruebas

- `tests/unit/` para lógica pura sin base de datos: máquina de estados,
  calculadora de presupuestos, matriz de permisos.
- `tests/integration/` contra Supabase local. Todo módulo con datos de taller
  incluye una prueba que verifica que el taller A no puede leer ni escribir
  datos del taller B.
