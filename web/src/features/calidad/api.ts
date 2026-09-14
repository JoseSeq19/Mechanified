import { api } from '@/lib/api';

export type ResultadoCheck = 'ok' | 'no_ok' | 'no_aplica';
export type ResultadoControl = 'pendiente' | 'aprobado' | 'rechazado';

export interface Punto {
  id: string;
  plantilla_id: string;
  categoria: string | null;
  descripcion: string;
  obligatorio: boolean;
  orden_visual: number;
}

export interface Plantilla {
  id: string;
  taller_id: string;
  nombre: string;
  descripcion: string | null;
  activo: boolean;
  puntos: Punto[];
  obligatorios: number;
  creado_en: string;
}

export interface PuntoNuevo {
  descripcion: string;
  categoria?: string | null;
  obligatorio: boolean;
}

export interface RespuestaControl {
  id: string;
  control_id: string;
  item_id: string | null;
  descripcion: string;
  resultado: ResultadoCheck;
  resultado_etiqueta: string;
  obligatorio: boolean;
  comentario: string | null;
  evidencia_url: string | null;
  orden_visual: number;
}

export interface Control {
  id: string;
  taller_id: string;
  orden_id: string;
  plantilla_id: string | null;
  inspector_id: string | null;
  inspector_nombre: string | null;
  resultado: ResultadoControl;
  resultado_etiqueta: string;
  observaciones: string | null;
  respuestas: RespuestaControl[];
  /** Obligatorios sin conformidad. Mientras haya alguno, aprobar falla. */
  pendientes: number;
  creado_en: string;
  cerrado_en: string | null;
}

/* --- Plantillas ----------------------------------------------------------- */

export const listarPlantillas = (incluirInactivas = false) =>
  api.get<Plantilla[]>(`/calidad/plantillas${incluirInactivas ? '?incluir_inactivas=true' : ''}`);

export const crearPlantilla = (datos: {
  nombre: string;
  descripcion?: string | null;
  puntos: PuntoNuevo[];
}) => api.post<Plantilla>('/calidad/plantillas', datos);

export const editarPlantilla = (
  id: string,
  datos: { nombre?: string; descripcion?: string | null; activo?: boolean },
) => api.patch<Plantilla>(`/calidad/plantillas/${id}`, datos);

export const borrarPlantilla = (id: string) => api.delete(`/calidad/plantillas/${id}`);

export const agregarPunto = (plantillaId: string, datos: PuntoNuevo) =>
  api.post<Plantilla>(`/calidad/plantillas/${plantillaId}/puntos`, datos);

export const editarPunto = (id: string, datos: Partial<PuntoNuevo>) =>
  api.patch<Plantilla>(`/calidad/puntos/${id}`, datos);

export const borrarPunto = (id: string) => api.delete(`/calidad/puntos/${id}`);

/* --- Controles ------------------------------------------------------------ */

export const listarControles = (ordenId: string) =>
  api.get<Control[]>(`/ordenes/${ordenId}/controles`);

export const iniciarControl = (ordenId: string, plantillaId: string) =>
  api.post<Control>(`/ordenes/${ordenId}/controles`, { plantilla_id: plantillaId });

export const marcarPunto = (
  respuestaId: string,
  datos: { resultado?: ResultadoCheck; comentario?: string | null },
) => api.patch<Control>(`/control-respuestas/${respuestaId}`, datos);

export const cerrarControl = (controlId: string, aprobado: boolean, observaciones?: string) =>
  api.post<Control>(`/controles/${controlId}/cerrar`, {
    aprobado,
    observaciones: observaciones || null,
  });
