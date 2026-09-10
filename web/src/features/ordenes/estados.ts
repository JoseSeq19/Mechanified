import type { EstadoOrden } from './api';

/**
 * Presentación de los estados.
 *
 * El color no es decorativo: agrupa el flujo en tres momentos que el taller
 * distingue de un vistazo.
 *
 *   - Petróleo  → la orden está en manos del taller (recepción, diagnóstico,
 *                 reparación, calidad).
 *   - Ámbar     → la pelota está en el tejado del cliente o del asesor: hay algo
 *                 esperando una decisión o una entrega.
 *   - Apagado   → cerrada, ya no exige atención.
 */
export type TonoEstado = 'taller' | 'espera' | 'cerrado';

export const TONO: Record<EstadoOrden, TonoEstado> = {
  recibido: 'taller',
  en_diagnostico: 'taller',
  presupuesto_pendiente: 'espera',
  aprobado: 'taller',
  en_reparacion: 'taller',
  control_calidad: 'taller',
  listo_para_entrega: 'espera',
  entregado: 'cerrado',
  cancelado: 'cerrado',
};

export const ETIQUETA: Record<EstadoOrden, string> = {
  recibido: 'Recibido',
  en_diagnostico: 'En diagnóstico',
  presupuesto_pendiente: 'Presupuesto pendiente',
  aprobado: 'Aprobado',
  en_reparacion: 'En reparación',
  control_calidad: 'Control de calidad',
  listo_para_entrega: 'Listo para entrega',
  entregado: 'Entregado',
  cancelado: 'Cancelado',
};

/** Los estados que exigen escribir un motivo antes de confirmar. */
export const EXIGE_COMENTARIO: ReadonlySet<EstadoOrden> = new Set<EstadoOrden>(['cancelado']);

export function formatearMoneda(valor: string | number): string {
  const n = typeof valor === 'string' ? Number(valor) : valor;
  return Number.isFinite(n) ? n.toLocaleString('es', { minimumFractionDigits: 2 }) : '—';
}

export function formatearFecha(iso: string | null, conHora = false): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('es', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    ...(conHora ? { hour: '2-digit', minute: '2-digit' } : {}),
  });
}

/** "hace 3 días", para la bitácora y las tarjetas del tablero. */
export function haceCuanto(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const minutos = Math.floor(ms / 60000);
  if (minutos < 1) return 'ahora mismo';
  if (minutos < 60) return `hace ${minutos} min`;
  const horas = Math.floor(minutos / 60);
  if (horas < 24) return `hace ${horas} h`;
  const dias = Math.floor(horas / 24);
  return dias === 1 ? 'ayer' : `hace ${dias} días`;
}
