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

Lo que hay hoy: inicio de sesión contra Supabase Auth y la pantalla de clientes
(listado con búsqueda y paginación, alta, edición, activar/desactivar y borrado).
El resto de los módulos aparecen en el menú marcados como pendientes.

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

## Usuarios

Las cuentas no se autoregistran: las crea el administrador de un taller, que es
quien decide a qué taller pertenecen y con qué rol. Sin perfil asignado, un
usuario puede autenticarse pero RLS le niega todo.

### En el proyecto hospedado

Se crean con la llave de servicio: primero el usuario en Supabase Auth, después
su fila en `perfiles` apuntando al taller y al rol. Hasta que exista el endpoint
de alta de usuarios, se hace desde el panel de Supabase o por su API de
administración.

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
