import { api } from '@/lib/api';
import type { ResumenEncuestas } from '@/features/encuestas/api';

export interface ConteoEstado {
  estado: string;
  etiqueta: string;
  cantidad: number;
}

export interface TrabajoVivo {
  abiertas: number;
  atrasadas: number;
  por_estado: ConteoEstado[];
  repuestos_bajo_minimo: number;
}

export interface Produccion {
  recibidas: number;
  entregadas: number;
  canceladas: number;
  facturado: string;
  /** null cuando no se entregó nada: un cero se leería como una caída. */
  ticket_promedio: string | null;
  mano_obra: string;
  repuestos: string;
  horas_ciclo_promedio: number | null;
  horas_ciclo_mediana: number | null;
}

export interface EtapaTiempo {
  estado: string;
  etiqueta: string;
  horas_promedio: number;
  /** Cuántas transiciones sostienen el promedio. Con dos o tres, no dice nada. */
  transiciones: number;
}

export interface PresupuestosMetrica {
  emitidos: number;
  aprobados: number;
  rechazados: number;
  tasa_aprobacion: number | null;
  horas_respuesta_promedio: number | null;
}

export interface CalidadMetrica {
  controles: number;
  aprobados: number;
  rechazados: number;
  tasa_rechazo: number | null;
}

export interface TecnicoProductivo {
  tecnico_id: string;
  nombre: string;
  entregadas: number;
  facturado: string;
}

export interface PanelMetricas {
  dias: number;
  desde: string;
  trabajo_vivo: TrabajoVivo;
  produccion: Produccion;
  etapas: EtapaTiempo[];
  presupuestos: PresupuestosMetrica;
  calidad: CalidadMetrica;
  satisfaccion: ResumenEncuestas;
  tecnicos: TecnicoProductivo[];
}

export const obtenerPanel = (dias: number) =>
  api.get<PanelMetricas>(`/metricas/panel?dias=${dias}`);
