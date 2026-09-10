import { api, type Pagina } from '@/lib/api';

export type TipoCliente = 'persona' | 'empresa';

export interface Cliente {
  id: string;
  taller_id: string;
  tipo: TipoCliente;
  nombre: string;
  documento: string | null;
  telefono: string | null;
  email: string | null;
  direccion: string | null;
  notas: string | null;
  activo: boolean;
  creado_en: string;
  actualizado_en: string;
}

export interface DatosCliente {
  nombre: string;
  tipo: TipoCliente;
  documento?: string | null;
  telefono?: string | null;
  email?: string | null;
  direccion?: string | null;
  notas?: string | null;
  activo?: boolean;
}

export interface FiltrosClientes {
  busqueda?: string;
  incluirInactivos?: boolean;
  limite: number;
  desplazamiento: number;
}

export function listarClientes(f: FiltrosClientes): Promise<Pagina<Cliente>> {
  const p = new URLSearchParams({
    limite: String(f.limite),
    desplazamiento: String(f.desplazamiento),
  });
  if (f.busqueda) p.set('busqueda', f.busqueda);
  if (f.incluirInactivos) p.set('incluir_inactivos', 'true');
  return api.get<Pagina<Cliente>>(`/clientes?${p}`);
}

export const crearCliente = (datos: DatosCliente) => api.post<Cliente>('/clientes', datos);

export const editarCliente = (id: string, datos: Partial<DatosCliente>) =>
  api.patch<Cliente>(`/clientes/${id}`, datos);

export const borrarCliente = (id: string) => api.delete(`/clientes/${id}`);
