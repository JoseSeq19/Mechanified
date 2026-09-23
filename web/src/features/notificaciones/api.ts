import { api } from '@/lib/api';

export type EstadoAviso = 'pendiente' | 'enviada' | 'fallida';

export interface Notificacion {
  id: string;
  taller_id: string;
  orden_id: string | null;
  canal: string;
  destinatario: string;
  plantilla: string;
  plantilla_etiqueta: string;
  estado: EstadoAviso;
  estado_etiqueta: string;
  intentos: number;
  /** Mensaje del servidor de correo, en crudo: el detalle es lo que se necesita. */
  ultimo_error: string | null;
  programada_para: string;
  enviada_en: string | null;
  creado_en: string;
}

export interface VistaPreviaCorreo {
  asunto: string;
  texto: string;
  html: string;
  destinatario: string;
}

export const listarNotificaciones = (ordenId: string) =>
  api.get<Notificacion[]>(`/ordenes/${ordenId}/notificaciones`);

export const vistaPreviaCorreo = (id: string) =>
  api.get<VistaPreviaCorreo>(`/notificaciones/${id}/vista-previa`);

/** Encola una copia con el correo que el cliente tenga ahora. */
export const reintentarAviso = (id: string) =>
  api.post<{ encolada_a: string }>(`/notificaciones/${id}/reintentar`, {});
