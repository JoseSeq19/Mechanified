/**
 * Pone el ejecutable a descargar en el sitio.
 *
 *     npm run publicar
 *
 * Sube dist/Mechanified/Mechanified.exe al bucket privado `mch-descargas`, en
 * `windows/Mechanified.exe`, que es de donde lo saca la página de la cuenta
 * (web/src/features/portal/descarga.ts). Sustituye al que hubiera.
 *
 * Es una tarea de sistema y usa la llave de servicio de backend/.env, que es la
 * única que puede escribir en ese bucket: la política de la migración
 * 20261020000100_organizaciones.sql solo deja leerlo. Corre en el equipo de
 * quien publica; la llave no viaja a ningún otro sitio que a Supabase.
 */
import { existsSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const EJECUTABLE = path.join(RAIZ, 'dist', 'Mechanified', 'Mechanified.exe');
const BUCKET = 'mch-descargas';
const RUTA = 'windows/Mechanified.exe';

function abortar(mensaje, remedio) {
  console.error(`\x1b[31m${mensaje}\x1b[0m\n  ${remedio}\n`);
  process.exit(1);
}

function leerEnv(archivo) {
  if (!existsSync(archivo)) return {};
  const valores = {};
  for (const linea of readFileSync(archivo, 'utf8').split(/\r?\n/)) {
    const m = linea.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (m) valores[m[1]] = m[2].replace(/^(['"])(.*)\1$/, '$2');
  }
  return valores;
}

if (!existsSync(EJECUTABLE)) abortar('No hay ejecutable que publicar.', 'npm run empaquetar');

const env = { ...leerEnv(path.join(RAIZ, 'backend', '.env')), ...process.env };
const supabase = env.MCH_SUPABASE_URL?.replace(/\/+$/, '');
const llave = env.MCH_SUPABASE_SERVICE_ROLE_KEY;
if (!supabase || !llave) {
  abortar(
    'Faltan MCH_SUPABASE_URL o MCH_SUPABASE_SERVICE_ROLE_KEY en backend/.env.',
    'Son las mismas que usa python -m app.alta_taller.',
  );
}

const bytes = readFileSync(EJECUTABLE);
const megas = (statSync(EJECUTABLE).size / 1024 / 1024).toFixed(1);
console.log(`Publicando ${megas} MB en ${supabase} → ${BUCKET}/${RUTA}…`);

const respuesta = await fetch(`${supabase}/storage/v1/object/${BUCKET}/${RUTA}`, {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${llave}`,
    apikey: llave,
    'Content-Type': 'application/vnd.microsoft.portable-executable',
    // Sustituye al anterior. Y que no se quede en caché mucho tiempo: quien lo
    // descargue después de publicar tiene que recibir este, no el viejo.
    'x-upsert': 'true',
    'cache-control': 'max-age=60',
  },
  body: bytes,
});

if (!respuesta.ok) {
  const detalle = await respuesta.text();
  const remedio = detalle.includes('Bucket not found')
    ? 'El bucket no existe: falta aplicar la migración 20261020000100_organizaciones.sql.'
    : 'Revisa la llave de servicio y el límite de tamaño de archivo del proyecto.';
  abortar(`Supabase respondió ${respuesta.status}: ${detalle}`, remedio);
}

console.log('Publicado. Ya se descarga desde la página de la cuenta del sitio.');
