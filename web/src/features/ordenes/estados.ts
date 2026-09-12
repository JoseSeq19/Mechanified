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
