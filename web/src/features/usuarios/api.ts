import { api } from '@/lib/api';
import type { Rol } from '@/app/sesion';

export interface Usuario {
  id: string;
  nombre_completo: string;
  /** Con el que entra. Copia del correo de la cuenta, para poder listarlo. */
  email: string | null;
  rol: Rol;
  rol_etiqueta: string;
  telefono: string | null;
  activo: boolean;
  creado_en: string | null;
}

export interface UsuarioCreado extends Usuario {
  /** Solo viene aquí, y solo esta vez. No se puede volver a consultar. */
  clave_temporal: string;
}

export interface DatosAlta {
  nombre_completo: string;
  email: string;
  rol: Rol;
  telefono?: string | null;
}

export interface DatosEdicion {
  nombre_completo?: string;
  telefono?: string | null;
  rol?: Rol;
  activo?: boolean;
}

export function listarUsuarios(rol?: Rol, incluirInactivos = false): Promise<Usuario[]> {
  const p = new URLSearchParams();
  if (rol) p.set('rol', rol);
  if (incluirInactivos) p.set('incluir_inactivos', 'true');
  return api.get<Usuario[]>(`/usuarios${p.toString() ? `?${p}` : ''}`);
}

export const crearUsuario = (datos: DatosAlta) => api.post<UsuarioCreado>('/usuarios', datos);

export const editarUsuario = (id: string, datos: DatosEdicion) =>
  api.patch<Usuario>(`/usuarios/${id}`, datos);

export const restablecerClave = (id: string) =>
  api.post<{ clave_temporal: string }>(`/usuarios/${id}/clave`, {});

export const cambiarCorreo = (id: string, email: string) =>
  api.patch<Usuario>(`/usuarios/${id}/correo`, { email });
