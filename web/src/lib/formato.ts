/** Formateo de fechas y dinero, compartido por todos los módulos. */

/**
 * Moneda con la que se escriben las cifras.
 *
 * Es estado de módulo y no de React a propósito: `formatearMoneda` se llama
 * desde docenas de sitios —tablas, totales, ayudas de formulario— y ninguno
 * tiene por qué recibir la moneda del taller por props hasta la última celda.
 *
 * La fija quien sabe cuál es: `Layout` con la configuración del taller, y la
 * página pública del presupuesto con la moneda que viene en el documento, que
 * es la que se le prometió al cliente. Ambas lo hacen durante el render y no en
 * un efecto, porque los efectos corren después de pintar y las cifras ya
 * estarían escritas.
 *
 * Mientras no se sepa cuál es, se escribe el número solo: una cifra sin símbolo
 * es mejor que una cifra con el símbolo de otra moneda.
 */
let monedaActual: string | null = null;

export function fijarMoneda(codigo: string | null): void {
  monedaActual = codigo;
}

export function formatearMoneda(valor: string | number, moneda = monedaActual): string {
  const n = typeof valor === 'string' ? Number(valor) : valor;
  if (!Number.isFinite(n)) return '—';
  if (!moneda) return n.toLocaleString('es', { minimumFractionDigits: 2 });

  try {
    return n.toLocaleString('es', { style: 'currency', currency: moneda });
  } catch {
    // Intl exige un código bien formado y estalla con cualquier otro. No vale
    // la pena perder la cifra por el símbolo: se escribe el código detrás.
    return `${n.toLocaleString('es', { minimumFractionDigits: 2 })} ${moneda}`;
  }
}

export function formatearNumero(valor: string | number, decimales = 2): string {
  const n = typeof valor === 'string' ? Number(valor) : valor;
  return Number.isFinite(n) ? n.toLocaleString('es', { maximumFractionDigits: decimales }) : '—';
}

export function formatearFecha(iso: string | null, conHora = false): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('es', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    ...(conHora ? { hour: '2-digit', minute: '2-digit' } : {}),
  });
}

/** "hace 3 días", para la bitácora y las tarjetas del tablero. */
export function haceCuanto(iso: string): string {
  const minutos = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutos < 1) return 'ahora mismo';
  if (minutos < 60) return `hace ${minutos} min`;
  const horas = Math.floor(minutos / 60);
  if (horas < 24) return `hace ${horas} h`;
  const dias = Math.floor(horas / 24);
  return dias === 1 ? 'ayer' : `hace ${dias} días`;
}
