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

Queda en http://localhost:5173

```powershell
npm run typecheck
npm run build
```

> `npm run lint` todavía no funciona: falta el archivo de configuración de
> ESLint, que llega con la Fase 5.

### 4. Móvil

Requiere el SDK de Flutter, que se instala aparte. Solo hace falta a partir de
la Fase 6.

```powershell
cd mobile
flutter create . --org com.mechanified --platforms android,ios
flutter pub get
flutter run
```

## Usuarios de prueba

El seed crea el taller ficticio **Delta Motors** con cuatro usuarios,
todos con la contraseña `Mechanified123!`:

| Correo                      | Rol                   |
|-----------------------------|-----------------------|
| `admin@deltamotors.test`    | `admin_taller`        |
| `asesor@deltamotors.test`   | `asesor_servicio`     |
| `tecnico@deltamotors.test`  | `tecnico`             |
| `repuestos@deltamotors.test`| `encargado_repuestos` |

## Documentación

- [Modelo de datos](docs/modelo-datos.md)
- [Flujo de estados de la orden](docs/flujo-estados.md)
- [Matriz de permisos por rol](docs/permisos.md)
- [Decisiones de arquitectura](docs/decisiones/)
