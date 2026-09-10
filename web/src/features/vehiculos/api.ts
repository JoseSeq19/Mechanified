import { api, type Pagina } from '@/lib/api';

export interface Vehiculo {
  id: string;
  taller_id: string;
  cliente_id: string;
  cliente_nombre: string | null;
  placa: string;
  vin: string | null;
  marca: string;
  modelo: string;
  anio: number | null;
  color: string | null;
  tipo_combustible: string | null;
  transmision: string | null;
  kilometraje_ultimo: number | null;
  notas: string | null;
  activo: boolean;
  creado_en: string;
  actualizado_en: string;
}

export interface DatosVehiculo {
  cliente_id: string;
  placa: string;
  marca: string;
  modelo: string;
  vin?: string | null;
  anio?: number | null;
  color?: string | null;
  tipo_combustible?: string | null;
  transmision?: string | null;
  kilometraje_ultimo?: number | null;
  notas?: string | null;
  activo?: boolean;
}

export interface FiltrosVehiculos {
  busqueda?: string;
  clienteId?: string;
  incluirInactivos?: boolean;
  limite: number;
  desplazamiento: number;
}

export function listarVehiculos(f: FiltrosVehiculos): Promise<Pagina<Vehiculo>> {
  const p = new URLSearchParams({
    limite: String(f.limite),
    desplazamiento: String(f.desplazamiento),
  });
  if (f.busqueda) p.set('busqueda', f.busqueda);
  if (f.clienteId) p.set('cliente_id', f.clienteId);
  if (f.incluirInactivos) p.set('incluir_inactivos', 'true');
  return api.get<Pagina<Vehiculo>>(`/vehiculos?${p}`);
}

export const crearVehiculo = (datos: DatosVehiculo) => api.post<Vehiculo>('/vehiculos', datos);

export const editarVehiculo = (id: string, datos: Partial<DatosVehiculo>) =>
  api.patch<Vehiculo>(`/vehiculos/${id}`, datos);

export const borrarVehiculo = (id: string) => api.delete(`/vehiculos/${id}`);
