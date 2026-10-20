/**
 * Nombre del producto y del sitio.
 *
 * Mechanified es el producto. Quien lo usa es una organización, y para su
 * gente la aplicación se presenta con el nombre de esa organización: la de
 * Grupo La Meseta ve "Grupo La Meseta". "Mechanified" queda para donde todavía
 * no se sabe de quién es la sesión —el sitio, la pantalla de acceso— y como
 * firma discreta al pie.
 */

export const PRODUCTO = 'Mechanified';

/**
 * Si este código corre como el sitio público y no como la aplicación. Se fija
 * al compilar (`vite build --mode sitio`): ver `vite.config.ts`.
 */
export const ES_SITIO = import.meta.env.MODE === 'sitio';

/**
 * Dirección pública del sitio de Mechanified, sin barra final.
 *
 * La aplicación de escritorio la necesita para mandar a crear cuenta u
 * organización, y para que el enlace de recuperación de contraseña aterrice en
 * un sitio que se abre desde cualquier dispositivo —el correo se suele leer en
 * el móvil—, no en `localhost`. Sin configurar, vale el origen actual.
 */
export const URL_SITIO = (import.meta.env.VITE_URL_SITIO || window.location.origin).replace(
  /\/+$/,
  '',
);

/**
 * Hasta dos iniciales para el glifo de la marca.
 *
 * Se saltan las palabras de enlace para que "Grupo La Meseta" dé "GM" y no
 * "GL", y "Taller de los Andes" dé "TA".
 */
export function iniciales(nombre: string): string {
  const enlaces = new Set(['de', 'del', 'la', 'las', 'el', 'los', 'y', 'e', '&']);
  const palabras = nombre
    .split(/\s+/)
    .map((p) => p.replace(/[^\p{L}\p{N}]/gu, ''))
    .filter((p) => p && !enlaces.has(p.toLowerCase()));

  if (palabras.length === 0) return PRODUCTO[0];
  if (palabras.length === 1) return palabras[0][0].toUpperCase();
  return (palabras[0][0] + palabras[palabras.length - 1][0]).toUpperCase();
}
