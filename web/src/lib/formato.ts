/** Formateo de fechas y dinero, compartido por todos los módulos. */

export function formatearMoneda(valor: string | number): string {
  const n = typeof valor === 'string' ? Number(valor) : valor;
  return Number.isFinite(n) ? n.toLocaleString('es', { minimumFractionDigits: 2 }) : '—';
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
