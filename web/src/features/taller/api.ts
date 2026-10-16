import { api } from '@/lib/api';

/**
 * Configuración del taller de la sesión.
 *
 * No lleva id en la ruta: el taller es el del token. Lo leen todos los roles,
 * porque la moneda hace falta para escribir cualquier cifra y la tarifa y el
 * impuesto para anticipar lo que el servidor va a aplicar por omisión.
 */
export interface Taller {
  id: string;
  nombre: string;
  /** Identificador global del taller. No se edita. */
  slug: string;
  identificacion_fiscal: string | null;
  telefono: string | null;
  email: string | null;
  direccion: string | null;
  zona_horaria: string;
  /** Código ISO 4217. Con él se formatea todo el dinero de la interfaz. */
  moneda: string;
  tarifa_hora_default: string;
  impuesto_pct: string;
  prefijo_orden: string;
  dias_validez_presupuesto: number;
  activo: boolean;
  creado_en: string;
  actualizado_en: string;
}

export interface DatosTaller {
  nombre?: string;
  identificacion_fiscal?: string | null;
  telefono?: string | null;
  email?: string | null;
  direccion?: string | null;
  moneda?: string;
  tarifa_hora_default?: number;
  impuesto_pct?: number;
  prefijo_orden?: string;
  dias_validez_presupuesto?: number;
}

/** Clave de react-query. La comparten `Layout` y la página de configuración. */
export const CLAVE_TALLER = ['taller'] as const;

export const obtenerTaller = () => api.get<Taller>('/taller');

export const editarTaller = (datos: DatosTaller) => api.patch<Taller>('/taller', datos);
