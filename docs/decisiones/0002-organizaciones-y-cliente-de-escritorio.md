# ADR 0002 — Organizaciones, alta por cuenta propia y un ejecutable sin credenciales

**Fecha:** 2026-10-20 · **Estado:** aceptada

## Contexto

El sistema nació como herramienta interna de Grupo La Meseta y pasa a ser un
producto, Mechanified, que usan varios clientes. Tres cosas cambian a la vez:

1. Quien usa el producto ya no es "el grupo" sino una **organización** por
   cliente, y el producto tiene que presentarse con su nombre: la gente de
   Grupo La Meseta ve "Grupo La Meseta".
2. Un cliente nuevo se registra, descarga el programa y crea su organización
   solo, o pide que se la creemos.
3. El programa se entrega como un ejecutable de Windows.

## Decisiones

### La organización está encima del taller, y no lo sustituye

`organizaciones` agrupa talleres; el taller sigue siendo el inquilino de RLS.
La organización da identidad (el nombre del producto), no acceso: dos sedes del
mismo grupo siguen sin verse. Sustituir el taller por la organización como
unidad de RLS habría tocado todas las políticas del esquema y habría abierto
justo la barrera entre sedes que el sistema garantizaba desde el principio.

Un taller que se inserta sin organización funda una con su nombre. Es el caso
más común —el taller independiente— y deja funcionando sin cambios todo lo que
ya insertaba talleres.

### El alta por cuenta propia es una función, no la llave de servicio

`mch_crear_mi_organizacion()` es `security definer`, saca la cuenta de
`auth.uid()` y solo actúa si esa cuenta aún no tiene perfil. Se llama desde la
sesión RLS del propio usuario. La alternativa —un endpoint que usara la sesión
de servicio— habría puesto la llave que se salta RLS en el camino de un request
de usuario, que es lo que este proyecto prohíbe.

El núcleo, `mch_crear_organizacion(cuenta, …)`, recibe la cuenta por parámetro y
por eso no está al alcance de `authenticated`: lo usa el equipo al atender una
solicitud.

### El ejecutable no lleva la API

La primera versión de `LaMeseta.exe` llevaba la API dentro y un `.env` al lado,
con la cadena de conexión a Postgres y la llave de servicio. Para un sistema
interno era aceptable; para un producto que se reparte, no: quien tiene esas
credenciales se salta RLS —puede fijar los claims que quiera en su propia
conexión— y lee los datos de todos los clientes.

`Mechanified.exe` es un cliente ligero: sirve la aplicación web ya compilada y
reenvía `/api` a la API central. No lleva credenciales; lo único que fija al
empaquetar es la dirección de la API y la del sitio, que son públicas. La API,
con sus secretos, vive solo en el servidor.

Se eligió reenviar `/api` en lugar de que la aplicación llame a la API por su
dirección absoluta para conservar lo que ya resolvía el proxy de Vite: la
aplicación se compila igual en los dos casos y el navegador nunca hace
peticiones a otro origen, así que no hay CORS que configurar por equipo.

### La descarga exige sesión, en el almacén

El instalador vive en el bucket privado `mch-descargas`, legible por cualquier
cuenta con sesión. No protege ningún secreto —el ejecutable no lleva ninguno—:
es la forma de que el producto se entregue a quien tiene cuenta y no a quien
encuentre una URL, sin poner un servidor de descargas aparte.

## Consecuencias

- Hace falta una API y un sitio en internet. El repositorio los construye pero
  no los publica (ver *Despliegue* en el README).
- El registro de cuentas en Supabase Auth tiene que estar abierto: el sitio crea
  cuentas. Una cuenta sin perfil no ve ningún dato de taller, así que abrirlo no
  abre datos.
- Renombrar una organización o mover sedes entre organizaciones no tiene
  pantalla; desde una sesión de usuario está bloqueado por trigger.
- Las solicitudes no avisan al equipo cuando llegan; se consultan con
  `python -m app.solicitudes`.
