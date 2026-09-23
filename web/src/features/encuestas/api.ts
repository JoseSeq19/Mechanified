import { api, apiPublica, type Pagina } from '@/lib/api';

export interface Encuesta {
  id: string;
  orden_id: string;
  /** Cuándo salió el correo. Lo marca el worker al entregarlo, no al encolarlo. */
  enviada_en: string | null;
  respondida_en: string | null;
  respondida: boolean;
  puntaje_atencion: number | null;
  puntaje_tiempo: number | null;
  puntaje_calidad: number | null;
  recomendaria: number | null;
  comentario: string | null;
  creado_en: string;
  /** Para compartirlo a mano cuando el cliente no tiene correo. */
  enlace_publico: string;
}

export interface EncuestaEnviada extends Encuesta {
  /** A quién se le encoló, o null si el cliente no tiene correo registrado. */
  encolada_a: string | null;
}

export interface EncuestaFila extends Encuesta {
  folio: string;
  placa: string;
  vehiculo: string;
  cliente_nombre: string;
  fecha_entrega: string | null;
}

export interface ResumenEncuestas {
  enviadas: number;
  respondidas: number;
  tasa_respuesta: number;
  promedio_atencion: number | null;
  promedio_tiempo: number | null;
  promedio_calidad: number | null;
  /** De -100 a 100. Null mientras nadie haya contestado. */
  nps: number | null;
  promotores: number;
  pasivos: number;
  detractores: number;
}

/** Lo que ve el cliente al abrir su enlace. Deliberadamente escueto. */
export interface EncuestaPublica {
  taller_nombre: string;
  taller_telefono: string | null;
  folio_orden: string;
  vehiculo: string;
  placa: string;
  fecha_entrega: string | null;
  respondida: boolean;
  respondida_en: string | null;
  puntaje_atencion: number | null;
  puntaje_tiempo: number | null;
  puntaje_calidad: number | null;
  recomendaria: number | null;
  comentario: string | null;
}

export interface RespuestaEncuesta {
  puntaje_atencion: number;
  puntaje_tiempo: number;
  puntaje_calidad: number;
  recomendaria: number;
  comentario?: string | null;
}

/** `null` mientras la orden no se haya entregado. */
export const obtenerEncuesta = (ordenId: string) =>
  api.get<Encuesta | null>(`/ordenes/${ordenId}/encuesta`);

export const enviarEncuesta = (ordenId: string) =>
  api.post<EncuestaEnviada>(`/ordenes/${ordenId}/encuesta`, {});

export const listarEncuestas = (filtros: {
  soloRespondidas?: boolean;
  limite?: number;
  desplazamiento?: number;
}) => {
  const p = new URLSearchParams();
  if (filtros.soloRespondidas) p.set('solo_respondidas', 'true');
  if (filtros.limite) p.set('limite', String(filtros.limite));
  if (filtros.desplazamiento) p.set('desplazamiento', String(filtros.desplazamiento));
  return api.get<Pagina<EncuestaFila>>(`/encuestas?${p}`);
};

export const resumenEncuestas = () => api.get<ResumenEncuestas>('/encuestas/resumen');

/* --- Sin sesión: lo que usa la página que abre el cliente ----------------- */

export const verEncuestaPublica = (token: string) =>
  apiPublica.get<EncuestaPublica>(`/encuestas/${token}`);

export const responderEncuestaPublica = (token: string, datos: RespuestaEncuesta) =>
  apiPublica.post<EncuestaPublica>(`/encuestas/${token}/respuesta`, datos);
