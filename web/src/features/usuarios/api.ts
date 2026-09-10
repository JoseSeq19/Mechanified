import { api } from '@/lib/api';
import type { Rol } from '@/app/sesion';

export interface Usuario {
  id: string;
  nombre_completo: string;
  rol: Rol;
  rol_etiqueta: string;
  telefono: string | null;
  activo: boolean;
}

export function listarUsuarios(rol?: Rol): Promise<Usuario[]> {
  const p = new URLSearchParams();
  if (rol) p.set('rol', rol);
  return api.get<Usuario[]>(`/usuarios${p.toString() ? `?${p}` : ''}`);
}
