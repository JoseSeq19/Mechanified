# Mechanified

Sistema de gestión integral para talleres mecánicos: recepción de vehículos,
diagnóstico, cotización de repuestos, aprobación de presupuestos, reparación,
control de calidad y entrega.

Multi-tenant: cada taller es una organización con sus propios usuarios y datos,
aislados a nivel de base de datos mediante Row Level Security de PostgreSQL.

## Estructura

| Carpeta     | Contenido                                                     |
|-------------|---------------------------------------------------------------|
| `backend/`  | API REST en FastAPI (Python 3.12), organizada por módulos      |
| `web/`      | Aplicación web en React + Vite + TypeScript                    |
| `mobile/`   | Aplicación Flutter para técnicos y asesores en campo           |
| `supabase/` | Esquema SQL versionado, políticas RLS, seed y Edge Functions   |
| `docs/`     | Modelo de datos, flujo de estados, matriz de permisos, ADRs    |

## Requisitos

- Python 3.12+
- Node.js 20+
- Flutter 3.24+
- Docker Desktop (para Supabase local)
- Supabase CLI (`npm i -g supabase` o `scoop install supabase`)

## Arrancar todo

Desde la raíz del repositorio, un solo comando levanta la API y la web:

```powershell
npm run dev
```

```
  API   http://localhost:8000        docs en /docs
  Web   http://localhost:5173
```

Entra en la web con la cuenta que te dio tu administrador. `Ctrl+C` detiene los
dos procesos.

> `npm run dev` **desde la raíz**. Dentro de `web/` también existe, pero solo
> levanta la interfaz, y sin la API detrás no carga ningún dato.

El lanzador vive en [scripts/dev.mjs](scripts/dev.mjs) y llama a los ejecutables
por ruta absoluta, sin pasar por `cmd.exe`. Es a propósito: en Windows con
`C:\Windows\System32` fuera del PATH, las herramientas habituales de arranque
paralelo fallan con `spawn cmd.exe ENOENT`.

La primera vez hay que preparar cada parte (ver más abajo): entorno virtual y
dependencias del backend, y `npm install` en `web/`.

## Puesta en marcha (desarrollo local)

### 1. Base de datos

```bash
supabase start          # levanta Postgres, Auth, Storage y Studio en Docker
supabase db reset       # aplica migraciones + seed.sql
```

`supabase start` imprime las URLs y llaves locales. Studio queda en
http://localhost:54323 y la API en http://localhost:54321.

> `seed.sql` corre con el rol `postgres`, que omite RLS. Es la única vía por la
> que se insertan datos sin pasar por las políticas, y es exclusiva de
> desarrollo local.

Si `supabase db reset` falla en `20260907001000_adjuntos.sql` con
`must be owner of table objects`, es que esa versión del CLI aplica las
migraciones con un rol sin privilegio sobre `storage.objects`. Las cuatro
políticas del bucket se crean entonces desde Studio (Storage > Policies) con el
mismo predicado que trae el archivo. El resto del esquema no depende de ellas.

### 2. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # PowerShell
pip install -e ".[dev]"
copy .env.example .env              # y completar valores
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Documentación interactiva: http://localhost:8000/docs
- Sonda: http://localhost:8000/salud
- Diagnóstico de conexión y RLS: http://localhost:8000/salud/base-datos

#### Probar los endpoints protegidos

Mechanified no tiene endpoint de login propio: la sesión la abre Supabase Auth
desde la web o el móvil, y el backend solo verifica el token recibido. Para
probar a mano hay que pedirle ese token a Supabase:

```powershell
python scripts/obtener_token.py admin@mechanfied "<contraseña>"
```

Imprime el token por salida estándar y, por error estándar, los claims que
trae — útil para ver de un vistazo si el hook de Auth está activo.

En http://localhost:8000/docs, pulsar **Authorize** arriba a la derecha y pegar
el token (sin la palabra `Bearer`). A partir de ahí las rutas con candado
funcionan desde el navegador.

Pruebas y calidad, lo mismo que corre el CI:

```powershell
pytest tests/unit -v
ruff check .
ruff format --check .
```

> Verificado con Python 3.14.5. Las dependencias declaran pisos de versión, no
> anclajes, así que resuelven a builds con binarios para el intérprete instalado
> (asyncpg 0.31, pydantic 2.13, FastAPI 0.141 en 3.14).

### 3. Web

```powershell
cd web
npm install
copy .env.example .env
npm run dev
```

Queda en http://localhost:5173, y necesita el backend corriendo en el 8000.

Lo que hay hoy: inicio de sesión contra Supabase Auth, tablero de órdenes y
ficha con todo su flujo (diagnóstico, mano de obra, repuestos, presupuesto,
control de calidad, encuesta y avisos al cliente), catálogo de repuestos,
plantillas de checklist, satisfacción, clientes y el panel del taller.

El panel (`/informes`) solo lo ve administración, y el enlace tampoco aparece en
el menú para los demás roles. No es una barrera de seguridad —los números salen
de datos que RLS deja leer a todo el taller— sino una decisión de producto:
facturación, ticket medio y productividad por técnico las comparte quien dirige
el taller, no el producto.

Dos páginas se abren **sin sesión**, desde el enlace que recibe el cliente:
`/presupuesto/:token` para aprobar o rechazar, y `/encuesta/:token` para
calificar el servicio. Esas rutas son parte del contrato con el backend:
`backend/app/shared/enlaces.py` las usa para componer los enlaces de los
correos, así que cambiarlas rompe los mensajes ya enviados.

```powershell
npm run typecheck
npm run build
```

> `npm run lint` todavía no funciona: falta el archivo de configuración de
> ESLint.

La autenticación la resuelve `@supabase/supabase-js` directamente contra
Supabase; los datos de negocio siempre pasan por la API de Mechanified. El
navegador nunca consulta tablas por su cuenta.

### 4. Móvil

Requiere el SDK de Flutter, que se instala aparte. Solo hace falta a partir de
la Fase 6.

```powershell
cd mobile
flutter create . --org com.mechanified --platforms android,ios
flutter pub get
flutter run
```

## Correo y avisos al cliente

Tres momentos del flujo le escriben al cliente, sin que nadie tenga que
acordarse: al **enviar un presupuesto** (con el enlace para aprobarlo), cuando
el vehículo queda **listo para entrega**, y al **entregarlo** (con la encuesta
de satisfacción). Si el cliente no tiene correo registrado no se encola nada y
el enlace queda en la ficha para compartirlo a mano.

El envío no ocurre dentro de la petición: se deja una fila en `notificaciones` y
un worker la procesa. Si el servidor de correo está caído, la orden ya quedó
guardada y el reintento es problema del worker.

### Modos de envío

| `MCH_EMAIL_MODO` | Qué hace                                                        |
|------------------|-----------------------------------------------------------------|
| `buzon` (por omisión) | No envía nada: guarda cada mensaje como `.eml` en `backend/buzon/` |
| `smtp`           | Envía de verdad; exige `MCH_SMTP_HOST` y `MCH_EMAIL_REMITENTE`   |

El buzón no es una simulación: el archivo lleva los mismos encabezados y el
mismo cuerpo que se enviarían, y se abre con cualquier cliente de correo. Es el
modo por omisión para poder desarrollar sin proveedor y, sobre todo, para que
una prueba con datos inventados no acabe escribiéndole a una dirección real.

Desde la ficha de la orden, «Avisos al cliente» muestra qué salió, a qué
dirección y qué dijo el servidor cuando no salió, con la vista previa del correo
tal cual lo recibe el cliente.

### El worker

Va embebido en la API mientras esto sea un despliegue de una sola pieza, así que
en desarrollo no hay que arrancar nada aparte. En producción se apaga y se corre
como proceso propio:

```powershell
$env:MCH_WORKER_EMBEBIDO = "false"   # en la API
python -m app.worker                  # y el worker, aparte
```

Los dos a la vez tampoco rompen nada: la cola se reparte con
`SELECT ... FOR UPDATE SKIP LOCKED`. Un envío fallido se reintenta con espera
creciente (1, 5, 15 y 60 minutos) y se da por perdido al quinto intento; una
dirección que el servidor rechaza no se reintenta.

## Usuarios

Las cuentas no se autoregistran: las crea el administrador de un taller, que es
quien decide a qué taller pertenecen y con qué rol. Sin perfil asignado, un
usuario puede autenticarse pero RLS le niega todo.

### Desde la aplicación

La administración del taller da de alta a su gente en **Personal**: nombre,
correo, rol. El backend crea la cuenta en Supabase Auth y el perfil en la misma
operación, y devuelve una **contraseña temporal que solo se muestra una vez**,
para entregársela a la persona. Ella la cambia desde *Cambiar contraseña*, abajo
en el menú; esa parte va directa a Supabase, así que el backend nunca ve una
contraseña. Si alguien la olvida, su administrador le genera otra.

Dos reglas que la pantalla aplica y conviene conocer:

- **A la gente se le da de baja, no se le borra.** Órdenes, presupuestos y
  bitácora apuntan a su perfil; borrarlo evaporaría la autoría de todo lo que
  hizo. Al darle de baja, su siguiente token sale sin taller ni rol y la API
  deja de aceptarle nada.
- **El último administrador activo está protegido.** Ni puede bajarse el rol a
  sí mismo, ni dejarlo otro sin él. Un taller sin administrador solo se
  arreglaría entrando por Supabase.

Un cambio de rol viaja dentro del token, así que surte efecto cuando la persona
renueva su sesión: como mucho en una hora, o al volver a entrar.

### En desarrollo local

`supabase/seed.sql` crea el taller ficticio **Delta Motors** con cuatro
usuarios, uno por rol, todos con la contraseña `Mechanified123!`:

| Correo                       | Rol                   |
|------------------------------|-----------------------|
| `admin@deltamotors.test`     | `admin_taller`        |
| `asesor@deltamotors.test`    | `asesor_servicio`     |
| `tecnico@deltamotors.test`   | `tecnico`             |
| `repuestos@deltamotors.test` | `encargado_repuestos` |

> Estas cuentas existen **solo en local**, tras `supabase db reset` con Docker.
> El seed no debe correr nunca contra un proyecto hospedado: pondría contraseñas
> conocidas en una base accesible desde internet.

## Documentación

- [Modelo de datos](docs/modelo-datos.md)
- [Flujo de estados de la orden](docs/flujo-estados.md)
- [Matriz de permisos por rol](docs/permisos.md)
- [Decisiones de arquitectura](docs/decisiones/)
