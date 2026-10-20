/**
 * Empaqueta Mechanified para Windows.
 *
 *     npm run empaquetar
 *
 * Deja dist/Mechanified/Mechanified.exe: la aplicación web compilada y un
 * servidor mínimo que la sirve en el propio equipo y reenvía `/api` a la API
 * central (ver escritorio/mechanified.py). No lleva credenciales: se puede dar
 * a cualquier cliente, y es lo que se publica para descargar con
 * `npm run publicar`.
 *
 * Lo que queda fijo al empaquetar sale de escritorio/.env:
 *
 *   MCH_API_URL    la API central a la que se reenvía `/api`
 *   MCH_URL_SITIO  el sitio público, para los enlaces de "crear cuenta" y la
 *                  vuelta del correo de recuperación de contraseña
 *
 * y de web/.env, como en cualquier `vite build`: la URL y la llave anónima de
 * Supabase, que son públicas por diseño.
 *
 * Igual que dev.mjs, invoca los ejecutables por ruta absoluta y sin shell, para
 * que funcione con `C:\Windows\System32` fuera del PATH.
 */
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const BACKEND = path.join(RAIZ, 'backend');
const WEB = path.join(RAIZ, 'web');
const ESCRITORIO = path.join(RAIZ, 'escritorio');
const SALIDA = path.join(RAIZ, 'dist', 'Mechanified');
const CONSTRUCCION = path.join(RAIZ, 'build', 'escritorio');

if (process.platform !== 'win32') {
  console.error('El ejecutable es para Windows: hay que empaquetarlo desde Windows.');
  process.exit(1);
}

// PyInstaller vive en el entorno del backend por comodidad: el cliente de
// escritorio solo usa la biblioteca estándar y no necesita uno propio.
const python = path.join(BACKEND, '.venv', 'Scripts', 'python.exe');
const tsc = path.join(WEB, 'node_modules', 'typescript', 'bin', 'tsc');
const vite = path.join(WEB, 'node_modules', 'vite', 'bin', 'vite.js');

function abortar(mensaje, remedio) {
  console.error(`\x1b[31m${mensaje}\x1b[0m\n  ${remedio}\n`);
  process.exit(1);
}

function correr(titulo, comando, argumentos, cwd, env = process.env) {
  console.log(`\n\x1b[36m» ${titulo}\x1b[0m`);
  const r = spawnSync(comando, argumentos, { cwd, env, stdio: 'inherit' });
  if (r.error) abortar(`${titulo}: no arrancó.`, r.error.message);
  if (r.status !== 0) abortar(`${titulo}: terminó con código ${r.status}.`, 'Revisa la salida de arriba.');
}

/** Lee un .env sencillo: CLAVE=valor, comentarios con #. */
function leerEnv(archivo) {
  if (!existsSync(archivo)) return {};
  const valores = {};
  for (const linea of readFileSync(archivo, 'utf8').split(/\r?\n/)) {
    const m = linea.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (m) valores[m[1]] = m[2].replace(/^(['"])(.*)\1$/, '$2');
  }
  return valores;
}

if (!existsSync(python)) {
  abortar(
    'No encuentro el entorno virtual del backend.',
    'cd backend && python -m venv .venv && .venv\\Scripts\\python.exe -m pip install -e ".[dev,empaquetado]"',
  );
}
if (!existsSync(vite)) abortar('Faltan las dependencias de la web.', 'npm --prefix web install');
if (!existsSync(path.join(WEB, '.env'))) {
  abortar(
    'Falta web/.env: la URL y la llave anónima de Supabase se fijan al compilar la web.',
    'copy web\\.env.example web\\.env   y completa los valores',
  );
}

const conPyInstaller = spawnSync(python, ['-c', 'import PyInstaller'], { stdio: 'ignore' });
if (conPyInstaller.status !== 0) {
  abortar(
    'Falta PyInstaller en el entorno del backend.',
    'backend\\.venv\\Scripts\\python.exe -m pip install -e "backend[empaquetado]"',
  );
}

// Las variables de entorno mandan sobre escritorio/.env, para poder empaquetar
// contra otra API sin tocar el archivo.
const config = { ...leerEnv(path.join(ESCRITORIO, '.env')), ...process.env };
const api = config.MCH_API_URL;
const sitio = config.MCH_URL_SITIO;

if (!api) {
  abortar(
    'Falta MCH_API_URL: el ejecutable tiene que saber a qué API reenviar.',
    'copy escritorio\\.env.example escritorio\\.env   y completa los valores',
  );
}
if (!/^https?:\/\/[^/]+/.test(api)) abortar(`MCH_API_URL no es una dirección: ${api}`, 'Ejemplo: https://api.tu-dominio.com');
if (!sitio) {
  console.warn(
    '\x1b[33mSin MCH_URL_SITIO: los enlaces a "crear cuenta" y la vuelta del correo de\n' +
      'recuperación apuntarán al propio equipo en vez de al sitio.\x1b[0m',
  );
}

// La aplicación siempre habla con `/api`: el ejecutable es quien la reenvía.
const entornoWeb = { ...process.env, VITE_API_URL: '/api', VITE_URL_SITIO: sitio ?? '' };
correr('Web: comprobación de tipos', process.execPath, [tsc, '-b'], WEB);
correr('Web: compilación de la aplicación', process.execPath, [vite, 'build'], WEB, entornoWeb);

mkdirSync(CONSTRUCCION, { recursive: true });
const configuracion = path.join(CONSTRUCCION, 'configuracion.json');
writeFileSync(
  configuracion,
  JSON.stringify({ api, sitio: sitio ?? null, empaquetado: new Date().toISOString() }, null, 2),
);

correr('Ejecutable', python, [
  '-m', 'PyInstaller',
  '--noconfirm',
  '--clean',
  '--onefile',
  '--console',
  '--name', 'Mechanified',
  '--icon', path.join(ESCRITORIO, 'mechanified.ico'),
  '--distpath', SALIDA,
  '--workpath', path.join(CONSTRUCCION, 'pyinstaller'),
  '--specpath', CONSTRUCCION,
  // Separador de --add-data: ';' en Windows.
  '--add-data', `${path.join(WEB, 'dist')};web`,
  '--add-data', `${configuracion};.`,
  path.join(ESCRITORIO, 'mechanified.py'),
], RAIZ);

console.log(`
  Listo: ${path.join(SALIDA, 'Mechanified.exe')}
    API   ${api}
    Sitio ${sitio ?? '(sin configurar)'}

  No lleva credenciales. Para ponerlo a descargar en el sitio: npm run publicar
`);
