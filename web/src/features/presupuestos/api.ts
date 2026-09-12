import { api, apiPublica } from '@/lib/api';

export type EstadoPresupuesto = 'borrador' | 'enviado' | 'aprobado' | 'rechazado' | 'vencido';

export interface ItemPresupuesto {
  id: string;
  tipo: 'mano_obra' | 'repuesto';
  tipo_etiqueta: string;
  descripcion: string;
  cantidad: string;
  precio_unitario: string;
  subtotal: string;
  orden_visual: number;
}

export interface PresupuestoResumen {
  id: string;
  orden_id: string;
  version: number;
  estado: EstadoPresupuesto;
  estado_etiqueta: string;
  total: string;
  valido_hasta: string | null;
  caducado: boolean;
  enviado_en: string | null;
  respondido_en: string | null;
  creado_en: string;
}

export interface Presupuesto extends PresupuestoResumen {
  taller_id: string;
  subtotal_mano_obra: string;
  subtotal_repuestos: string;
  descuento: string;
  impuesto_pct: string;
  impuesto_monto: string;
  comentario_cliente: string | null;
  autor_nombre: string | null;
  items: ItemPresupuesto[];
  /** Solo aparece una vez enviado: un borrador todavía puede cambiar. */
  enlace_publico: string | null;
}

/** Lo que ve el cliente al abrir su enlace. Deliberadamente escueto. */
export interface PresupuestoPublico {
  taller_nombre: string;
  taller_telefono: string | null;
  moneda: string;
  folio_orden: string;
  vehiculo: string;
  placa: string;
  version: number;
  estado: EstadoPresupuesto;
  estado_etiqueta: string;
  cerrado: boolean;
  valido_hasta: string | null;
  items: ItemPresupuesto[];
  subtotal: string;
  descuento: string;
  impuesto_pct: string;
  impuesto_monto: string;
  total: string;
  comentario_cliente: string | null;
  respondido_en: string | null;
}

export interface DatosEmitir {
  descuento?: number;
  impuesto_pct?: number | null;
  valido_hasta?: string | null;
}

export const listarPresupuestos = (ordenId: string) =>
  api.get<PresupuestoResumen[]>(`/ordenes/${ordenId}/presupuestos`);

export const obtenerPresupuesto = (id: string) => api.get<Presupuesto>(`/presupuestos/${id}`);

export const emitirPresupuesto = (ordenId: string, datos: DatosEmitir) =>
  api.post<Presupuesto>(`/ordenes/${ordenId}/presupuestos`, datos);

export const editarPresupuesto = (id: string, datos: DatosEmitir) =>
  api.patch<Presupuesto>(`/presupuestos/${id}`, datos);

export const enviarPresupuesto = (id: string) =>
  api.post<Presupuesto>(`/presupuestos/${id}/enviar`, {});

export const anotarRespuesta = (id: string, aprobado: boolean, comentario?: string) =>
  api.post<Presupuesto>(`/presupuestos/${id}/respuesta`, {
    aprobado,
    comentario: comentario || null,
  });

/* --- Sin sesión: lo que usa la página que abre el cliente ----------------- */

export const verPresupuestoPublico = (token: string) =>
  apiPublica.get<PresupuestoPublico>(`/presupuestos/${token}`);

export const responderPresupuestoPublico = (
  token: string,
  aprobado: boolean,
  comentario?: string,
) =>
  apiPublica.post<PresupuestoPublico>(`/presupuestos/${token}/respuesta`, {
    aprobado,
    comentario: comentario || null,
  });
