# Grupo La Meseta

Sistema interno del grupo para gestionar sus talleres: recepción de vehículos,
diagnóstico, cotización de repuestos, aprobación de presupuestos, reparación,
control de calidad y entrega.

No es un producto que se venda a terceros. Quien entra es gente del grupo —
administración, asesoría de servicio, técnicos y repuestos— y los clientes son
los dueños de los vehículos, que no tienen cuenta: lo único que ven son dos
enlaces que les llegan por correo, el del presupuesto y el de la encuesta.

Aun así, cada taller es un **inquilino** con sus propios usuarios y datos,
aislados en la base de datos con Row Level Security de PostgreSQL. No es una
herencia de haberlo pensado como SaaS: una sede no tiene por qué ver las
órdenes, los precios ni la productividad de otra, y esa barrera es la que impide
que un `WHERE` olvidado se convierta en una fuga entre sedes. Abrir un taller
nuevo es dar de alta un inquilino más (ver
[Dar de alta un taller](#dar-de-alta-un-taller)).

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

> **Si ya tenías el entorno local levantado de antes del cambio de nombre**: el
> `project_id` de `supabase/config.toml` es el que nombra los contenedores y el
> volumen de Docker, y ahora es `meseta`. La primera vez hay que parar el
> entorno viejo y arrancar el nuevo, que nace vacío:
>
> ```bash
> supabase stop          # para los contenedores del id anterior
> supabase start
> supabase db reset      # migraciones + seed otra vez
> ```
>
> Los datos locales anteriores siguen en el volumen viejo; eran del seed, así
> que `db reset` los deja igual. No afecta a ningún entorno hospedado.

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

El sistema no tiene endpoint de login propio: la sesión la abre Supabase Auth
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
ficha con todo su flujo (fotos, diagnóstico, mano de obra, repuestos,
presupuesto, control de calidad, encuesta y avisos al cliente), catálogo de
repuestos, plantillas de checklist, satisfacción, clientes, personal,
configuración del taller y el panel. La orden se puede imprimir.

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

Lo mismo que corre el CI:

```powershell
npm run lint
npm run typecheck
npm run build
```

> La configuración del linter está en [web/eslint.config.js](web/eslint.config.js),
> en formato plano, que es el único que acepta ESLint 10. No usa reglas con
> información de tipos: eso ya lo cubre `npm run typecheck`, y pedirle al linter
> que compile el proyecto entero en cada pasada solo lo haría lento.

La autenticación la resuelve `@supabase/supabase-js` directamente contra
Supabase; los datos de negocio siempre pasan por la API de La Meseta. El
navegador nunca consulta tablas por su cuenta.

### 4. Móvil

Requiere el SDK de Flutter, que se instala aparte.

```powershell
cd mobile
flutter create . --org com.meseta --platforms android,ios
flutter pub get
copy .env.example .env     # y pega la llave anónima de `supabase status`
flutter run --dart-define-from-file=.env
```

Las carpetas `android/` e `ios/` no están versionadas: las genera
`flutter create .` sobre el proyecto que ya existe, y no se toca nada de lo que
hay en `lib/`.

> La configuración **no se lee en marcha**: se compila dentro con
> `--dart-define-from-file=.env`. En un móvil el paquete instalado es el que es,
> y un `.env` dentro del bundle sería un archivo de texto que cualquiera abre.
> Si falta algún valor, la app lo dice en la primera pantalla en vez de fallar
> al primer toque.

Después de `flutter create .`, para que la cámara funcione en iOS hay que añadir
a `ios/Runner/Info.plist` las dos razones de uso que exige Apple:

```xml
<key>NSCameraUsageDescription</key>
<string>Para fotografiar el estado del vehículo en la orden de servicio.</string>
<key>NSPhotoLibraryUsageDescription</key>
<string>Para adjuntar fotos del vehículo a la orden de servicio.</string>
```

**Qué hace la app.** Es la herramienta de quien está junto al coche, no una copia
de la web en pequeño:

- **Mis órdenes.** Para un técnico, por omisión solo las asignadas a él; un
  interruptor muestra el taller entero. La búsqueda por folio, placa o cliente
  entra también en lo ya entregado, porque la pregunta de campo suele ser "¿qué
  le hicimos a este coche?".
- **Ficha.** Mover la orden al paso siguiente —los botones son los que manda
  `transiciones_posibles`, así que la máquina de estados no se replica aquí—,
  registrar diagnóstico y hallazgos, cargar horas de trabajo y pedir piezas.
- **Fotos.** Con la cámara del móvil, marcando a qué momento pertenecen
  (recepción, diagnóstico, reparación, calidad, entrega). Es la razón de ser de
  la app: la constancia del estado del vehículo la hace quien lo tiene delante.
- **Mi cuenta.** Cambiar la contraseña temporal del alta y cerrar sesión.

Lo que no está es trabajo de mostrador —presupuestos, control de calidad,
catálogo, panel—, y se hace mejor en una pantalla grande.

La app habla con la API de La Meseta para todo lo que es dato de negocio, y
con Supabase solo para dos cosas: la identidad y el almacén de las fotos. No usa
el SDK de Supabase; son cuatro peticiones HTTP y están en
[mobile/lib/nucleo/auth.dart](mobile/lib/nucleo/auth.dart) y
[evidencias.dart](mobile/lib/nucleo/evidencias.dart).

## Fotos y archivos de la orden

Cada orden puede llevar fotos y PDF, marcados con el momento al que pertenecen:
recepción, diagnóstico, reparación, control de calidad o entrega. Es la
constancia del estado del vehículo, que es lo que el taller necesita poder poner
sobre la mesa cuando alguien dice que el golpe del parachoques no estaba al
entregarlo.

Dos decisiones que conviene conocer antes de tocar ese código:

- **El archivo no pasa por la API.** Va del navegador —o del móvil— al bucket
  privado `mch-evidencias` con la sesión de Supabase de quien lo sube, y después
  se registran los metadatos en la API. Hacer pasar 25 MiB de foto por FastAPI no
  añadiría ninguna comprobación que la política del bucket no haga ya, y ocuparía
  un trabajador del servidor al ritmo de la cobertura del taller.
- **La ruta es el contrato que sostiene el aislamiento**:

  ```
  {taller_id}/{orden_id}/{uuid}-{nombre}
  ```

  La primera carpeta es lo que compara la política del bucket; la segunda la
  valida el backend. Las dos cosas se verifican otra vez en la base, con el
  trigger `mch_adjuntos_ruta_guard`.

La tabla `adjuntos` **no tiene política de UPDATE**, y la API no expone ningún
PATCH: la evidencia no se corrige, se quita y se vuelve a subir. Quitarla la
puede hacer quien la subió o la administración del taller.

El bucket es privado, así que no hay URL que se pueda reenviar: lo que se ve son
enlaces firmados que caducan en diez minutos y los pide el propio cliente.

## Imprimir

La orden tiene documento propio en `/ordenes/{id}/impresion`: encabezado con los
datos del taller —los de **Configuración**—, cliente, vehículo, kilometraje,
hallazgos, trabajo, piezas, totales y dos huecos para firmar. Las notas internas
no salen: ese papel se lo lleva el cliente.

El presupuesto que recibe el cliente por enlace también se imprime, desde su
propia página.

Las reglas de papel están en
[web/src/styles/impresion.css](web/src/styles/impresion.css) y valen para toda la
aplicación: cualquier pantalla sale razonable con Ctrl+P, sin la barra lateral ni
los botones.

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

## Configuración del taller

En **Configuración** vive lo que el sistema necesita saber del taller para poder
calcular. Son cuatro grupos:

| Grupo | Qué contiene |
|---|---|
| Identidad | Nombre e identificación fiscal. |
| Contacto | Teléfono, correo y dirección. **Esto lo ve el cliente** en el presupuesto que recibe por enlace. |
| Dinero | Moneda, tarifa por hora e impuesto. |
| Operación | Prefijo del folio y días de validez del presupuesto. |

La tarifa y el impuesto son valores **por omisión**, no fijos: quien registra una
línea de mano de obra o emite un presupuesto puede indicar otros. Lo que importa
es lo que pasa después:

- **Nada de esto reescribe historia.** Cada línea de mano de obra se queda con la
  tarifa que tenía al crearse y cada presupuesto con el impuesto con el que se
  emitió. Es deliberado: un documento que el cliente ya vio no puede cambiar de
  monto. Subir la tarifa afecta a lo que se registre de ahí en adelante.
- **Cambiar el prefijo no renumera nada.** El contador de folios sigue donde
  estaba; las órdenes existentes conservan el suyo y solo las nuevas estrenan el
  prefijo nuevo.
- **La moneda es con la que la interfaz escribe cada cifra.** Hasta que se sabe
  cuál es, los números van sin símbolo: una cifra sin símbolo es mejor que una
  cifra con el símbolo de otra moneda.

Cambiarla es cosa de administración (`PATCH /taller`); leerla la puede hacer todo
el taller (`GET /taller`), porque el técnico que mira un subtotal necesita saber
en qué moneda está y con qué tarifa salió.

El `slug` del taller y su zona horaria no se editan desde la aplicación: el
primero es el identificador global con el que se le nombra desde fuera, y la
segunda todavía no la lee nadie —las fechas se formatean con la zona del
navegador—, así que ofrecer el control daría a entender que cambia algo.

El alta de un taller nuevo se hace con la herramienta de línea de comandos del
backend (ver [Dar de alta un taller](#dar-de-alta-un-taller)), que es tarea de
sistema: `talleres` no tiene política de INSERT, así que esa fila solo la puede
escribir el rol de servicio.

## Usuarios

Las cuentas no se autoregistran: las crea el administrador de un taller, que es
quien decide a qué taller pertenecen y con qué rol. Sin perfil asignado, un
usuario puede autenticarse pero RLS le niega todo.

### Dar de alta un taller

Es lo que arranca un despliegue, y no tiene pantalla a propósito: `talleres` no
tiene política de INSERT, así que la fila solo la escribe el rol de servicio.
Exponerlo por HTTP sería poner esa llave detrás de una puerta, y aquí no hace
falta ninguna puerta: abrir una sede es una decisión del grupo, no algo que
nadie vaya a hacer por su cuenta.

```powershell
cd backend
.venv\Scripts\python -m app.alta_taller `
  --nombre "La Meseta Sur" `
  --admin-correo marisol@lameseta.test `
  --admin-nombre "Marisol Peñaranda" `
  --moneda USD --tarifa 18 --impuesto 16
```

Deja creados el taller, la cuenta de su primer administrador y su perfil, e
imprime **una sola vez** la contraseña temporal. El identificador global
(`--slug`) y el prefijo de folio (`--prefijo`) se derivan del nombre si no se
indican: "La Meseta Sur" da `la-meseta-sur` y `LAM`. El resto de la configuración
se ajusta después en la aplicación, en **Configuración**.

Son tres escrituras en dos sistemas distintos —la fila del taller y el perfil en
Postgres, la cuenta en Supabase Auth— y pueden fallar a medias, así que cada
paso deshace los anteriores: un taller sin administrador no se podría terminar de
dar de alta por ninguna otra vía, y además su identificador quedaría ocupado
para el segundo intento.

### Si alguien olvida su contraseña

Hay dos caminos, y conviene saber cuál es cuál:

- **Por su cuenta**, desde *No recuerdo mi contraseña* en la pantalla de acceso.
  Supabase manda un correo con un enlace que aterriza en `/clave`, donde se pone
  la nueva. Ese correo lo manda Supabase con su propia plantilla, **no** el
  worker de La Meseta: quien ha olvidado su contraseña no tiene sesión, y sin
  sesión RLS no le deja encolar nada en `notificaciones`. Si pudiera, cualquiera
  podría provocar correos con el remitente del producto.
- **Por su administrador**, desde **Personal**, que le genera una temporal en el
  momento. Es la salida cuando el correo no llega o la dirección ya no existe.

En desarrollo los correos de Supabase quedan en el buzón local que levanta
`supabase start` (puerto 54324). En producción hay que configurarle SMTP al
proyecto de Supabase, que es independiente del `MCH_SMTP_*` del worker.

La dirección de retorno tiene que estar autorizada en el proyecto; en local ya
lo está, en `supabase/config.toml`.

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

`supabase/seed.sql` crea la sede ficticia **La Meseta Centro** con cuatro
usuarios, uno por rol, todos con la contraseña `LaMeseta123!`:

| Correo                    | Rol                   |
|---------------------------|-----------------------|
| `admin@lameseta.test`     | `admin_taller`        |
| `asesor@lameseta.test`    | `asesor_servicio`     |
| `tecnico@lameseta.test`   | `tecnico`             |
| `repuestos@lameseta.test` | `encargado_repuestos` |

> Estas cuentas existen **solo en local**, tras `supabase db reset` con Docker.
> El seed no debe correr nunca contra un proyecto hospedado: pondría contraseñas
> conocidas en una base accesible desde internet.

## Documentación

- [Modelo de datos](docs/modelo-datos.md)
- [Flujo de estados de la orden](docs/flujo-estados.md)
- [Matriz de permisos por rol](docs/permisos.md)
- [Decisiones de arquitectura](docs/decisiones/)
