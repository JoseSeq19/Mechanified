import { api } from '@/lib/api';

export type Severidad = 'leve' | 'moderada' | 'critica';

export const SEVERIDADES: { valor: Severidad; texto: string }[] = [
  { valor: 'leve', texto: 'Leve' },
  { valor: 'moderada', texto: 'Moderada' },
  { valor: 'critica', texto: 'Crítica' },
];

export interface Hallazgo {
  id: string;
  diagnostico_id: string;
  sistema: string;
  descripcion: string;
  severidad: Severidad;
  severidad_etiqueta: string;
  requiere_repuesto: boolean;
  orden_visual: number;
}

export interface Diagnostico {
  id: string;
  taller_id: string;
  orden_id: string;
  tecnico_id: string | null;
  tecnico_nombre: string | null;
  resumen: string;
  horas_estimadas: string;
  hallazgos: Hallazgo[];
  creado_en: string;
  actualizado_en: string;
}

export interface HallazgoNuevo {
  sistema: string;
  descripcion: string;
  severidad: Severidad;
  requiere_repuesto: boolean;
}

export interface DiagnosticoNuevo {
  resumen: string;
  horas_estimadas: number;
  tecnico_id?: string | null;
  hallazgos: HallazgoNuevo[];
}

export interface ManoObra {
  id: string;
  orden_id: string;
  descripcion: string;
  horas: string;
  tarifa_hora: string;
  subtotal: string;
  tecnico_id: string | null;
  tecnico_nombre: string | null;
  creado_en: string;
}

export interface ResumenManoObra {
  lineas: ManoObra[];
  total_horas: string;
  total: string;
}

export interface ManoObraNueva {
  descripcion: string;
  horas: number;
  tarifa_hora?: number | null;
  tecnico_id?: string | null;
}

export const listarDiagnosticos = (ordenId: string) =>
  api.get<Diagnostico[]>(`/ordenes/${ordenId}/diagnosticos`);

export const crearDiagnostico = (ordenId: string, datos: DiagnosticoNuevo) =>
  api.post<Diagnostico>(`/ordenes/${ordenId}/diagnosticos`, datos);

export const borrarDiagnostico = (id: string) => api.delete(`/diagnosticos/${id}`);

export const agregarHallazgo = (diagnosticoId: string, datos: HallazgoNuevo) =>
  api.post<Diagnostico>(`/diagnosticos/${diagnosticoId}/hallazgos`, datos);

export const borrarHallazgo = (id: string) => api.delete(`/hallazgos/${id}`);

export const listarManoObra = (ordenId: string) =>
  api.get<ResumenManoObra>(`/ordenes/${ordenId}/mano-obra`);

export const crearManoObra = (ordenId: string, datos: ManoObraNueva) =>
  api.post<ManoObra>(`/ordenes/${ordenId}/mano-obra`, datos);

export const editarManoObra = (id: string, datos: Partial<ManoObraNueva>) =>
  api.patch<ManoObra>(`/mano-obra/${id}`, datos);

export const borrarManoObra = (id: string) => api.delete(`/mano-obra/${id}`);
