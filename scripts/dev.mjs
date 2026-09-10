/**
 * Levanta la API y la web juntas, con un solo comando desde la raíz.
 *
 *     npm run dev
 *
 * Por qué un script propio en vez de `concurrently` o `npm-run-all`: esas
 * herramientas lanzan cada comando a través de `cmd.exe`, que resuelven por
 * PATH. En una máquina Windows donde `C:\Windows\System32` no esté en el PATH
 * —cosa que pasa— fallan con `spawn cmd.exe ENOENT` y no arranca nada.
 *
 * Aquí se invocan los ejecutables por ruta absoluta y sin intérprete de por
 * medio: el python del entorno virtual y el vite del node_modules de la web.
 * Sin shell no hay nada que resolver, así que funciona igual con el PATH roto.
 */
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ES_WINDOWS = process.platform === 'win32';

const COLOR = { api: '\x1b[36m', web: '\x1b[35m', err: '\x1b[31m', fin: '\x1b[0m' };

const pythonVenv = ES_WINDOWS
  ? path.join(RAIZ, 'backend', '.venv', 'Scripts', 'python.exe')
  : path.join(RAIZ, 'backend', '.venv', 'bin', 'python');

const viteBin = path.join(RAIZ, 'web', 'node_modules', 'vite', 'bin', 'vite.js');

function abortar(mensaje, remedio) {
  console.error(`${COLOR.err}${mensaje}${COLOR.fin}\n  ${remedio}\n`);
  process.exit(1);
}

if (!existsSync(pythonVenv)) {
  abortar(
    'No encuentro el entorno virtual del backend.',
    'cd backend && python -m venv .venv && .venv\\Scripts\\python.exe -m pip install -e ".[dev]"',
  );
}
if (!existsSync(viteBin)) {
  abortar('Faltan las dependencias de la web.', 'npm --prefix web install');
}

const hijos = [];
let cerrando = false;

function arrancar(nombre, comando, argumentos, cwd) {
  const hijo = spawn(comando, argumentos, { cwd, stdio: ['ignore', 'pipe', 'pipe'] });

  const escribir = (destino) => (trozo) => {
    for (const linea of trozo.toString().split(/\r?\n/)) {
      if (linea.trim()) destino.write(`${COLOR[nombre]}[${nombre}]${COLOR.fin} ${linea}\n`);
    }
  };
  hijo.stdout.on('data', escribir(process.stdout));
  hijo.stderr.on('data', escribir(process.stderr));

  hijo.on('error', (e) => {
    console.error(`${COLOR.err}[${nombre}] no arrancó: ${e.message}${COLOR.fin}`);
    detenerTodo(1);
  });

  // Si uno de los dos se cae, el otro sobra: arrastrarlo evita dejar un
  // servidor huérfano ocupando el puerto.
  hijo.on('exit', (codigo) => {
    if (!cerrando) {
      console.error(`${COLOR.err}[${nombre}] terminó con código ${codigo}${COLOR.fin}`);
      detenerTodo(codigo ?? 1);
    }
  });

  hijos.push(hijo);
  return hijo;
}

function detenerTodo(codigo) {
  if (cerrando) return;
  cerrando = true;
  for (const h of hijos) {
    if (!h.killed) h.kill();
  }
  setTimeout(() => process.exit(codigo), 300);
}

process.on('SIGINT', () => detenerTodo(0));
process.on('SIGTERM', () => detenerTodo(0));

console.log(`
  Mechanified

    API   http://localhost:8000        docs en /docs
    Web   http://localhost:5173

  Ctrl+C para detener los dos.
`);

arrancar(
  'api',
  pythonVenv,
  ['-m', 'uvicorn', 'app.main:app', '--reload', '--port', '8000'],
  path.join(RAIZ, 'backend'),
);

arrancar('web', process.execPath, [viteBin], path.join(RAIZ, 'web'));
