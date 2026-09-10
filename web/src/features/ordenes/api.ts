import { api, type Pagina } from '@/lib/api';

export type EstadoOrden =
  | 'recibido'
  | 'en_diagnostico'
  | 'presupuesto_pendiente'
  | 'aprobado'
  | 'en_reparacion'
  | 'control_calidad'
  | 'listo_para_entrega'
  | 'entregado'
  | 'cancelado';

export interface OrdenResumen {
  id: string;
  folio: string;
  estado: EstadoOrden;
  estado_etiqueta: string;
  cliente_id: string;
  cliente_nombre: string;
  vehiculo_id: string;
  vehiculo_placa: string;
  vehiculo_descripcion: string;
  tecnico_nombre: string | null;
  asesor_nombre: string | null;
  fecha_ingreso: string;
  fecha_promesa: string | null;
  total: string;
  atrasada: boolean;
}

export interface Orden extends OrdenResumen {
  taller_id: string;
  motivo_ingreso: string;
  kilometraje_ingreso: number | null;
  nivel_combustible: number | null;
  inventario_ingreso: Record<string, unknown>;
  fecha_entrega: string | null;
  total_mano_obra: string;
  total_repuestos: string;
  notas_internas: string | null;
  motivo_cancelacion: string | null;
  creado_en: string;
  actualizado_en: string;
  /** Estados a los que este usuario puede mover esta orden ahora mismo. */
  transiciones_posibles: EstadoOrden[];
}

export interface Evento {
  id: string;
  estado_anterior: EstadoOrden | null;
  estado_nuevo: EstadoOrden;
  estado_nuevo_etiqueta: string;
  usuario_nombre: string | null;
  comentario: string | null;
  creado_en: string;
}

export interface ColumnaTablero {
  estado: EstadoOrden;
  etiqueta: string;
  cantidad: number;
}

export interface ResumenTablero {
  columnas: ColumnaTablero[];
  total_abiertas: number;
}

export interface DatosOrden {
  cliente_id: string;
  vehiculo_id: string;
  motivo_ingreso: string;
  asesor_id?: string | null;
  tecnico_id?: string | null;
  kilometraje_ingreso?: number | null;
  nivel_combustible?: number | null;
  fecha_promesa?: string | null;
  notas_internas?: string | null;
}

export interface FiltrosOrdenes {
  busqueda?: string;
  estados?: EstadoOrden[];
  vehiculoId?: string;
  clienteId?: string;
  tecnicoId?: string;
  incluirCerradas?: boolean;
  limite: number;
  desplazamiento: number;
}

export function listarOrdenes(f: FiltrosOrdenes): Promise<Pagina<OrdenResumen>> {
  const p = new URLSearchParams({
    limite: String(f.limite),
    desplazamiento: String(f.desplazamiento),
  });
  if (f.busqueda) p.set('busqueda', f.busqueda);
  for (const e of f.estados ?? []) p.append('estado', e);
  if (f.vehiculoId) p.set('vehiculo_id', f.vehiculoId);
  if (f.clienteId) p.set('cliente_id', f.clienteId);
  if (f.tecnicoId) p.set('tecnico_id', f.tecnicoId);
  if (f.incluirCerradas) p.set('incluir_cerradas', 'true');
  return api.get<Pagina<OrdenResumen>>(`/ordenes?${p}`);
}

export const obtenerTablero = () => api.get<ResumenTablero>('/ordenes/tablero');
export const obtenerOrden = (id: string) => api.get<Orden>(`/ordenes/${id}`);
export const obtenerEventos = (id: string) => api.get<Evento[]>(`/ordenes/${id}/eventos`);
export const crearOrden = (datos: DatosOrden) => api.post<Orden>('/ordenes', datos);
export const editarOrden = (id: string, datos: Partial<DatosOrden>) =>
  api.patch<Orden>(`/ordenes/${id}`, datos);

export const cambiarEstado = (id: string, estado: EstadoOrden, comentario?: string) =>
  api.post<Orden>(`/ordenes/${id}/estado`, { estado, comentario: comentario || null });
