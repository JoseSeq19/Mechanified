import { api, type Pagina } from '@/lib/api';

export type EstadoItem = 'solicitado' | 'cotizado' | 'aprobado' | 'recibido' | 'instalado';

export const ESTADOS_ITEM: { valor: EstadoItem; texto: string }[] = [
  { valor: 'solicitado', texto: 'Solicitado' },
  { valor: 'cotizado', texto: 'Cotizado' },
  { valor: 'aprobado', texto: 'Aprobado' },
  { valor: 'recibido', texto: 'Recibido' },
  { valor: 'instalado', texto: 'Instalado' },
];

/** Las que todavía no están en el taller. Es lo que frena la reparación. */
export const PENDIENTES: ReadonlySet<EstadoItem> = new Set<EstadoItem>([
  'solicitado',
  'cotizado',
  'aprobado',
]);

export interface Repuesto {
  id: string;
  taller_id: string;
  sku: string;
  nombre: string;
  descripcion: string | null;
  categoria: string | null;
  unidad: string;
  costo: string;
  precio_venta: string;
  stock: string;
  stock_minimo: string;
  bajo_minimo: boolean;
  proveedor: string | null;
  activo: boolean;
  creado_en: string;
  actualizado_en: string;
}

export interface DatosRepuesto {
  sku: string;
  nombre: string;
  descripcion?: string | null;
  categoria?: string | null;
  unidad?: string;
  costo?: number;
  precio_venta?: number;
  stock?: number;
  stock_minimo?: number;
  proveedor?: string | null;
  activo?: boolean;
}

export interface ItemOrden {
  id: string;
  orden_id: string;
  repuesto_id: string | null;
  sku: string | null;
  descripcion: string;
  cantidad: string;
  precio_unitario: string;
  subtotal: string;
  estado: EstadoItem;
  estado_etiqueta: string;
  notas: string | null;
  solicitante_nombre: string | null;
  creado_en: string;
}

export interface ResumenRepuestos {
  lineas: ItemOrden[];
  total: string;
  pendientes: number;
}

export interface ItemNuevo {
  repuesto_id?: string | null;
  descripcion?: string | null;
  cantidad: number;
  precio_unitario?: number | null;
  estado?: EstadoItem;
  notas?: string | null;
}

export interface FiltrosCatalogo {
  busqueda?: string;
  incluirInactivos?: boolean;
  soloBajoMinimo?: boolean;
  limite: number;
  desplazamiento: number;
}

export function listarCatalogo(f: FiltrosCatalogo): Promise<Pagina<Repuesto>> {
  const p = new URLSearchParams({
    limite: String(f.limite),
    desplazamiento: String(f.desplazamiento),
  });
  if (f.busqueda) p.set('busqueda', f.busqueda);
  if (f.incluirInactivos) p.set('incluir_inactivos', 'true');
  if (f.soloBajoMinimo) p.set('solo_bajo_minimo', 'true');
  return api.get<Pagina<Repuesto>>(`/repuestos?${p}`);
}

export const crearRepuesto = (datos: DatosRepuesto) => api.post<Repuesto>('/repuestos', datos);
export const editarRepuesto = (id: string, datos: Partial<DatosRepuesto>) =>
  api.patch<Repuesto>(`/repuestos/${id}`, datos);
export const borrarRepuesto = (id: string) => api.delete(`/repuestos/${id}`);

export const listarItems = (ordenId: string) =>
  api.get<ResumenRepuestos>(`/ordenes/${ordenId}/repuestos`);
export const agregarItem = (ordenId: string, datos: ItemNuevo) =>
  api.post<ItemOrden>(`/ordenes/${ordenId}/repuestos`, datos);
export const editarItem = (id: string, datos: Partial<ItemNuevo>) =>
  api.patch<ItemOrden>(`/orden-repuestos/${id}`, datos);
export const borrarItem = (id: string) => api.delete(`/orden-repuestos/${id}`);
