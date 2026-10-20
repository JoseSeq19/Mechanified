import { api } from '@/lib/api';
import type { Rol } from '@/app/sesion';

/** La organización de la sesión: da nombre al producto para su gente. */
export interface Organizacion {
  id: string;
  nombre: string;
  slug: string;
}

export type EstadoSolicitud = 'pendiente' | 'atendida' | 'descartada';

export interface Solicitud {
  id: string;
  nombre_organizacion: string;
  estado: EstadoSolicitud;
  creado_en: string;
  atendida_en: string | null;
}

/** Dónde está la cuenta: su organización, su sede y su rol. */
export interface Pertenencia {
  organizacion_id: string;
  organizacion_nombre: string;
  taller_id: string;
  taller_nombre: string;
  rol: Rol;
  /** False si la administración de su sede la dio de baja. */
  activo: boolean;
}

/**
 * Lo que el sitio necesita para decidir qué ofrecerle a una cuenta.
 *
 * Funciona aunque el token no lleve taller, que es justo el caso de quien
 * acaba de registrarse o de crear su organización.
 */
export interface EstadoCuenta {
  email: string | null;
  organizacion: Pertenencia | null;
  solicitud: Solicitud | null;
}

export interface DatosOrganizacion {
  nombre: string;
  sede?: string | null;
  nombre_completo: string;
  telefono?: string | null;
  moneda?: string;
  tarifa_hora_default?: number;
  impuesto_pct?: number;
}

export interface DatosSolicitud {
  nombre_organizacion: string;
  nombre_contacto: string;
  telefono?: string | null;
  sedes?: number | null;
  mensaje?: string | null;
}

export const CLAVE_ORGANIZACION = ['organizacion'] as const;
export const CLAVE_CUENTA = ['cuenta'] as const;

export const obtenerOrganizacion = () => api.get<Organizacion>('/organizacion');

export const obtenerCuenta = () => api.get<EstadoCuenta>('/cuenta');

export const crearOrganizacion = (datos: DatosOrganizacion) =>
  api.post<EstadoCuenta>('/cuenta/organizacion', datos);

export const solicitarOrganizacion = (datos: DatosSolicitud) =>
  api.post<EstadoCuenta>('/cuenta/solicitud', datos);
