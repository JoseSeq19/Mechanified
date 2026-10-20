# Mechanified

Gestión de talleres mecánicos: recepción de vehículos, diagnóstico, cotización
de repuestos, aprobación de presupuestos, reparación, control de calidad y
entrega.

Quien usa Mechanified es una **organización**: un grupo con varias sedes, como
Grupo La Meseta, que es el primer cliente, o un taller independiente con una
sola. Para su gente el producto se presenta con el nombre de la organización
—quien entra de Grupo La Meseta ve "Grupo La Meseta", no "Mechanified"—, y
dentro trabajan administración, asesoría de servicio, técnicos y repuestos. Los
dueños de los vehículos no tienen cuenta: lo único que ven son dos enlaces que
les llegan por correo, el del presupuesto y el de la encuesta.

Cada sede (cada taller) es un **inquilino** con sus propios usuarios y datos,
aislados en la base de datos con Row Level Security de PostgreSQL. La
organización está por encima y no cambia eso: dos sedes del mismo grupo siguen
sin ver las órdenes, los precios ni la productividad de la otra, y esa barrera
es la que impide que un `WHERE` olvidado se convierta en una fuga entre sedes,
y con más razón entre clientes.

## Cómo llega un cliente

1. **Se registra en el sitio** de Mechanified, con su correo.
2. **Descarga `Mechanified.exe`**. Solo se entrega con sesión: sale de un bucket
   privado que solo leen las cuentas registradas.
3. **Crea su organización** con su primera sede, y queda como administrador. O,
   si prefiere, **pide que la cree el equipo** de Mechanified, que la atiende
   desde la línea de comandos (ver [Organizaciones](#organizaciones)).
4. **Abre `Mechanified.exe` y entra** con la misma cuenta. La aplicación pasa a
   llamarse como su organización.
5. Da de alta a su gente desde **Personal**. A ellos no les hace falta pasar por
   el sitio.

Los pasos 3 y 4 se pueden dar en cualquier orden: si alguien abre el ejecutable
sin organización, la aplicación le ofrece crearla ahí mismo.

## Estructura

| Carpeta       | Contenido                                                          |
|---------------|--------------------------------------------------------------------|
| `backend/`    | API REST en FastAPI (Python 3.12), organizada por módulos           |
| `web/`        | React + Vite + TypeScript. Dos destinos del mismo código: la aplicación y el sitio |
| `escritorio/` | `Mechanified.exe`: sirve la aplicación en el equipo y reenvía `/api` a la API central |
| `mobile/`     | Aplicación Flutter para técnicos y asesores en campo                |
| `supabase/`   | Esquema SQL versionado, políticas RLS, seed y Edge Functions        |
| `docs/`       | Modelo de datos, flujo de estados, matriz de permisos, ADRs         |

La web compila dos cosas distintas:

- **La aplicación** (`npm run build`, sale en `web/dist/`): lo que usa la gente
  de cada sede. Va dentro de `Mechanified.exe`.
- **El sitio** (`npm run build:sitio`, sale en `web/dist-sitio/`): presentación,
  registro, descarga y cuenta, más las dos páginas que abre el dueño del
  vehículo. Es lo que se publica en internet.

Comparten sistema de diseño, sesión y cliente de la API; cambia el punto de
entrada (`src/main.tsx` o `src/sitio.tsx`, ver
[web/vite.config.ts](web/vite.config.ts)).

## Requisitos

- Python 3.12+
- Node.js 20+
- Flutter 3.24+
- Docker Desktop (para Supabase local)
- Supabase CLI (`npm i -g supabase` o `scoop install supabase`)

## Arrancar todo

Desde la raíz del repositorio, un solo comando levanta la API, la aplicación y
el sitio:

```powershell
npm run dev
```

```
  API     http://localhost:8000        docs en /docs
  Web     http://localhost:5173        la aplicación (lo que va en Mechanified.exe)
  Sitio   http://localhost:5174        presentación, registro, descarga y cuenta
```

`Ctrl+C` detiene los tres procesos.

> `npm run dev` **desde la raíz**. Dentro de `web/` también existe, pero solo
> levanta la interfaz, y sin la API detrás no carga ningún dato.

El lanzador vive en [scripts/dev.mjs](scripts/dev.mjs) y llama a los ejecutables
por ruta absoluta, sin pasar por `cmd.exe`. Es a propósito: en Windows con
`C:\Windows\System32` fuera del PATH, las herramientas habituales de arranque
paralelo fallan con `spawn cmd.exe ENOENT`.

La primera vez hay que preparar cada parte (ver más abajo): entorno virtual y
dependencias del backend, y `npm install` en `web/`.

## Mechanified.exe

```powershell
copy escritorio\.env.example escritorio\.env    # MCH_API_URL y MCH_URL_SITIO
npm run empaquetar                               # deja dist/Mechanified/Mechanified.exe
npm run publicar                                 # lo pone a descargar en el sitio
```

Es un cliente ligero de unos 9 MB: lleva la aplicación web ya compilada y un
servidor mínimo, escrito solo con la biblioteca estándar de Python
([escritorio/mechanified.py](escritorio/mechanified.py)), que:

- la sirve en http://127.0.0.1:5180, solo para ese equipo, y abre el navegador;
- reenvía lo que empieza por `/api` a la API central, con el token de quien
  tiene la sesión abierta. Es el mismo reparto que hace el proxy de Vite en
  desarrollo, así que la aplicación se compila igual y nunca pide nada a otro
  origen.

**No lleva credenciales**, y es lo que permite dárselo a cualquier cliente. La
primera versión llevaba la API dentro y, al lado, un `.env` con la cadena de
conexión a Postgres y la llave de servicio, que se saltan RLS: repartirla era
darle a cada cliente las llaves de los datos de todos los demás. Ahora todo eso
vive solo en el servidor de la API.

Otros detalles:

- El puerto es fijo porque la sesión de Supabase se guarda por origen en el
  navegador: con otro puerto en cada arranque habría que entrar cada vez.
- Abrirlo dos veces no choca: la segunda copia reconoce a la primera y solo abre
  el navegador.
- Solo atiende peticiones dirigidas a `127.0.0.1` o `localhost` por su nombre,
  para que una página de internet no pueda usarlo apuntando su dominio al equipo.
- No está firmado: Windows SmartScreen avisa la primera vez ("Más información →
  Ejecutar de todos modos"). La página de la cuenta lo explica.

El icono lo dibuja [escritorio/generar_icono.py](escritorio/generar_icono.py); se
versiona ya hecho. PyInstaller vive en el entorno del backend
(`pip install -e ".[dev,empaquetado]"`) por no mantener otro.

## Despliegue

Producción vive en dos proyectos de Vercel y en el proyecto de Supabase:

| Pieza | Dónde | Se actualiza con |
|---|---|---|
| Sitio | https://mechanified.vercel.app · proyecto `mechanified` (`web/`) | `npx vercel deploy --prod --cwd web` |
| API | https://mechanified-api.vercel.app · proyecto `mechanified-api` (`backend/`) | `npx vercel deploy --prod --cwd backend` |
| Base de datos, Auth y archivos | Supabase `ziajrnpghfjlvgpvazzw` | `supabase db push` |
| `Mechanified.exe` | bucket `mch-descargas` | `npm run empaquetar` y `npm run publicar` |

Los dos proyectos se despliegan desde este equipo con la CLI, no desde Git.
Conectarlos a un repositorio (`vercel git connect`) haría que cada `push`
desplegara solo.

**La API** es una función de Python ([backend/vercel.json](backend/vercel.json)),
en la región `pdx1` (Oregón), al lado de la base de datos de Supabase
(`us-west-2`): cada petición hace varias idas y vueltas a Postgres, y con la
función en la costa este cada una costaba decenas de milisegundos más. Su
configuración son variables del proyecto en Vercel, no un archivo: la cadena
de Postgres y la llave de servicio van como *sensitive*, que no se pueden volver
a leer. `.vercelignore` impide que se suba el `.env` de este equipo. Además de lo
habitual lleva:

- `MCH_ENTORNO=produccion`, que oculta `/salud/base-datos`.
- `MCH_URL_PUBLICA_WEB` = el sitio: ahí llevan los enlaces de presupuesto y
  encuesta, y el dueño del vehículo los abre desde su móvil.
- `MCH_WORKER_EMBEBIDO=false`: una función de Vercel no sigue viva entre
  peticiones, así que el worker de correos no puede ir dentro (ver abajo).
- `MCH_DB_POOL_TAMANO=2` y `MCH_DB_POOL_DESBORDE=3`: cada instancia abre su
  propio pool contra el pooler de Supabase.

**El sitio** ([web/vercel.json](web/vercel.json)) compila con
`npm run build:sitio`, sirve `index.html` para cualquier ruta que no sea un
archivo y reenvía `/api/*` a la API, sin caché: el navegador nunca sale de su
dominio y no hace falta CORS. Sus `VITE_*` son variables del proyecto.

**Supabase Auth** tiene el registro abierto, la confirmación por correo
desactivada, *Site URL* = el sitio y, como direcciones de retorno, el sitio y
las de desarrollo local. El hook `mch_hook_access_token` sigue activo.

### Lo que falta para un uso comercial

- **Los correos al cliente no salen.** En Vercel no hay proceso que viva entre
  peticiones, así que nada vacía la cola de `notificaciones`: los avisos se
  quedan pendientes. Mientras tanto, los enlaces de presupuesto y encuesta están
  en la ficha de la orden para compartirlos a mano. Hace falta un servidor SMTP
  (`MCH_EMAIL_MODO=smtp`) y algo que llame al worker con regularidad: un proceso
  aparte, o una tarea programada.
- **Supabase solo envía sus propios correos al equipo del proyecto**, y como
  mucho dos por hora. Por eso el registro no pide confirmar el correo, y por eso
  la recuperación de contraseña no le llega a un cliente. Hasta configurar un
  SMTP propio en Authentication → Emails, a la gente de una sede le restablece
  la contraseña su administrador desde Personal.
- **El plan Hobby de Vercel es para uso personal, no comercial.** Para cobrar a
  clientes hay que pasar los proyectos a Pro.

## Organizaciones

La organización da el nombre; el taller (la sede) es el inquilino. Todo taller
pertenece a una organización, y una cuenta pertenece a un solo taller, así que
también a una sola organización.

Hay tres maneras de que nazca una:

- **Por cuenta propia**, desde el sitio o desde la aplicación. La hace
  `mch_crear_mi_organizacion()`, una función `security definer` que saca la
  cuenta del token: no hace falta la llave de servicio, y nadie puede fundar
  una organización a nombre de otro.
- **Pidiéndosela al equipo.** Queda una fila en `solicitudes_organizacion`, y el
  equipo la atiende:

  ```powershell
  cd backend
  .venv\Scripts\python -m app.solicitudes                    # las pendientes
  .venv\Scripts\python -m app.solicitudes atender 3f9a1c2e --sede "Taller Centro" --moneda VES
  .venv\Scripts\python -m app.solicitudes descartar 3f9a1c2e
  ```

  Atenderla deja como administrador a quien la pidió, con su propia cuenta: no
  hay contraseña que entregarle, pero **sí hay que avisarle**, porque el comando
  no le escribe. Tampoco hay aviso automático al equipo cuando entra una
  solicitud: hoy se consulta con el primer comando.
- **Al dar de alta un taller** con `python -m app.alta_taller` sin indicar
  organización: el taller funda una con su mismo nombre. Con
  `--organizacion grupo-la-meseta` se suma como sede a una que ya existe (ver
  [Dar de alta un taller](#dar-de-alta-un-taller)).

Cambiarle el nombre a una organización o mover una sede de una a otra no tiene
pantalla todavía: lo hace el equipo directamente en la base. Desde una sesión de
usuario está bloqueado a propósito (trigger `mch_talleres_organizacion_guard`).

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
npm run dev          # la aplicación, en http://localhost:5173
npm run dev:sitio    # el sitio, en http://localhost:5174
```

Las dos necesitan el backend corriendo en el 8000.

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
calificar el servicio. Viven en el sitio, que es lo que está en internet, y por
eso `MCH_URL_PUBLICA_WEB` es la dirección del sitio. Esas rutas son parte del
contrato con el backend: `backend/app/shared/enlaces.py` las usa para componer
los enlaces de los correos, así que cambiarlas rompe los mensajes ya enviados.

El sitio tiene además `/` (la presentación), `/entrar` (entrar o crear cuenta),
`/cuenta` (descargar el ejecutable y crear o pedir la organización) y `/clave`,
donde aterriza el correo de recuperación de contraseña también cuando se pide
desde el ejecutable: el correo suele abrirse en otro dispositivo, y ahí
`localhost` no lleva a ninguna parte.

Lo mismo que corre el CI:

```powershell
npm run lint
npm run typecheck
npm run build
npm run build:sitio
```

> La configuración del linter está en [web/eslint.config.js](web/eslint.config.js),
> en formato plano, que es el único que acepta ESLint 10. No usa reglas con
> información de tipos: eso ya lo cubre `npm run typecheck`, y pedirle al linter
> que compile el proyecto entero en cada pasada solo lo haría lento.

La autenticación la resuelve `@supabase/supabase-js` directamente contra
Supabase; los datos de negocio siempre pasan por la API de Mechanified. El
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

La app habla con la API de Mechanified para todo lo que es dato de negocio, y
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

Una organización nueva nace con su primer taller (ver
[Organizaciones](#organizaciones)). Las sedes siguientes las suma el equipo de
Mechanified (ver [Dar de alta un taller](#dar-de-alta-un-taller)): `talleres` no
tiene política de INSERT, así que fuera del alta de la organización esa fila
solo la escribe el rol de servicio.

## Usuarios

Hay dos clases de cuenta, y conviene no confundirlas:

- **Quien funda una organización** se registra solo, en el sitio. Su cuenta nace
  sin taller y sirve para descargar y para crear o pedir la organización.
- **El resto de la gente** no se registra: la crea el administrador de su sede
  desde Personal, que es quien decide a qué taller pertenece y con qué rol.

Sin perfil, una cuenta puede autenticarse pero RLS le niega todo dato de taller.
Lo único que alcanza son las rutas `/cuenta` de la API, que comparan con
`auth.uid()` y no con el taller.

### Dar de alta un taller

Es la herramienta del equipo de Mechanified, y no tiene pantalla a propósito:
además del taller crea la cuenta de su administrador en Supabase Auth, y eso
solo se hace con la llave de servicio. Exponerlo por HTTP sería poner esa llave
detrás de una puerta. Su uso típico es sumar una sede a una organización:

```powershell
cd backend
.venv\Scripts\python -m app.alta_taller `
  --nombre "La Meseta Sur" `
  --organizacion grupo-la-meseta `
  --admin-correo gerencia.sur@lameseta.test `
  --admin-nombre "Óscar Rangel" `
  --moneda USD --tarifa 18 --impuesto 16
```

Deja creados el taller, la cuenta de su primer administrador y su perfil, e
imprime **una sola vez** la contraseña temporal. Sin `--organizacion`, el taller
funda una organización con su mismo nombre; con `--organizacion-nombre` estrena
una con otro. El identificador global (`--slug`) y el prefijo de folio
(`--prefijo`) se derivan del nombre si no se indican: "La Meseta Sur" da
`la-meseta-sur` y `LAM`. El resto de la configuración se ajusta después en la
aplicación, en **Configuración**.

Son tres escrituras en dos sistemas distintos —la fila del taller y el perfil en
Postgres, la cuenta en Supabase Auth— y pueden fallar a medias, así que cada
paso deshace los anteriores: un taller sin administrador no se podría terminar de
dar de alta por ninguna otra vía, y además su identificador quedaría ocupado
para el segundo intento.

### Si alguien olvida su contraseña

Hay dos caminos, y conviene saber cuál es cuál:

- **Por su cuenta**, desde *No recuerdo mi contraseña* en la pantalla de acceso.
  Supabase manda un correo con un enlace que aterriza en `/clave` del sitio
  (`VITE_URL_SITIO`), donde se pone la nueva. Ese correo lo manda Supabase con su propia plantilla, **no** el
  worker de Mechanified: quien ha olvidado su contraseña no tiene sesión, y sin
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

`supabase/seed.sql` crea la organización **Grupo La Meseta** con su sede ficticia
**La Meseta Centro** y cuatro usuarios, uno por rol, todos con la contraseña
`LaMeseta123!`:

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
