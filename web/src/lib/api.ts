/**
 * Cliente HTTP de la API de Mechanified.
 *
 * Adjunta el token de la sesión de Supabase a cada petición y traduce los dos
 * formatos de error que devuelve el backend a un mensaje legible:
 *
 *   - Errores de dominio:  { error: { codigo, mensaje, detalles } }
 *   - Validación de FastAPI: { detail: [{ loc, msg, type }] }
 *
 * Sin esta traducción, la interfaz mostraría objetos JSON en pantalla.
 */
import { supabase } from './supabase';

/**
 * Base de las peticiones. En desarrollo es `/api`, una ruta del mismo origen
 * que sirve el proxy de Vite: así el navegador nunca hace una petición cruzada
 * y CORS no interviene. En producción se apunta a la URL absoluta de la API con
 * VITE_API_URL.
 */
const BASE = import.meta.env.VITE_API_URL ?? '/api';

export class ErrorApi extends Error {
  constructor(
    readonly estado: number,
    mensaje: string,
    readonly codigo?: string,
    readonly detalles?: unknown,
  ) {
    super(mensaje);
    this.name = 'ErrorApi';
  }

  /** True cuando el problema es lo que escribió el usuario, no un fallo. */
  get esDeUsuario(): boolean {
    return this.estado >= 400 && this.estado < 500;
  }
}

interface DetalleValidacion {
  loc: (string | number)[];
  msg: string;
  type: string;
}

/** Traduce los mensajes de Pydantic que más se ven en los formularios. */
function traducirValidacion(d: DetalleValidacion): string {
  const campo = d.loc.filter((p) => p !== 'body').join('.') || 'el dato';
  const traducciones: Record<string, string> = {
    string_too_short: 'es demasiado corto',
    string_too_long: 'es demasiado largo',
    missing: 'es obligatorio',
    value_error: 'no tiene un formato válido',
    enum: 'no es un valor permitido',
  };
  const motivo = traducciones[d.type] ?? d.msg;
  return `${campo}: ${motivo}`;
}

function construirError(estado: number, cuerpo: unknown): ErrorApi {
  if (cuerpo && typeof cuerpo === 'object') {
    const c = cuerpo as Record<string, unknown>;

    if (c.error && typeof c.error === 'object') {
      const e = c.error as Record<string, unknown>;
      return new ErrorApi(
        estado,
        String(e.mensaje ?? 'Error inesperado'),
        e.codigo as string | undefined,
        e.detalles,
      );
    }

    if (Array.isArray(c.detail)) {
      const mensajes = (c.detail as DetalleValidacion[]).map(traducirValidacion);
      return new ErrorApi(estado, mensajes.join('. '), 'validacion', c.detail);
    }

    if (typeof c.detail === 'string') {
      return new ErrorApi(estado, c.detail);
    }
  }

  if (estado === 0) {
    // `fetch` lanza el mismo TypeError si el servidor no responde y si el
    // navegador bloqueó la respuesta por CORS, así que el mensaje tiene que
    // nombrar las dos causas. Decir solo "¿está corriendo el backend?" manda a
    // buscar donde no es cuando el problema real es el origen.
    const porProxy = BASE.startsWith('/');
    return new ErrorApi(
      0,
      porProxy
        ? 'No se pudo contactar la API. El backend no está respondiendo: ' +
          'arráncalo con `npm run dev` desde la raíz del proyecto.'
        : `No se pudo contactar la API en ${BASE}. O no está respondiendo, o ` +
          `rechazó el origen ${window.location.origin} por CORS.`,
      'sin_conexion',
    );
  }

  return new ErrorApi(estado, `Error ${estado} al contactar la API.`);
}

async function peticion<T>(ruta: string, opciones: RequestInit = {}): Promise<T> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;

  let respuesta: Response;
  try {
    respuesta = await fetch(`${BASE}${ruta}`, {
      ...opciones,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...opciones.headers,
      },
    });
  } catch {
    throw construirError(0, null);
  }

  if (respuesta.status === 204) return undefined as T;

  const texto = await respuesta.text();
  let cuerpo: unknown = null;
  if (texto) {
    try {
      cuerpo = JSON.parse(texto);
    } catch {
      cuerpo = { detail: texto };
    }
  }

  if (!respuesta.ok) throw construirError(respuesta.status, cuerpo);
  return cuerpo as T;
}

export const api = {
  get: <T>(ruta: string) => peticion<T>(ruta),
  post: <T>(ruta: string, cuerpo: unknown) =>
    peticion<T>(ruta, { method: 'POST', body: JSON.stringify(cuerpo) }),
  patch: <T>(ruta: string, cuerpo: unknown) =>
    peticion<T>(ruta, { method: 'PATCH', body: JSON.stringify(cuerpo) }),
  delete: (ruta: string) => peticion<void>(ruta, { method: 'DELETE' }),
};

export interface Pagina<T> {
  items: T[];
  total: number;
  limite: number;
  desplazamiento: number;
}

/**
 * Cliente para las rutas públicas, sin token de sesión.
 *
 * Existe aparte del normal por la misma razón que el backend tiene dos routers:
 * lo que abre un cliente desde su enlace no debe arrastrar por descuido la
 * identidad de quien tenga sesión abierta en ese navegador. Aquí la
 * autorización es el token de la URL y nada más.
 */
async function peticionPublica<T>(ruta: string, opciones: RequestInit = {}): Promise<T> {
  let respuesta: Response;
  try {
    respuesta = await fetch(`${BASE}/publico${ruta}`, {
      ...opciones,
      headers: { 'Content-Type': 'application/json', ...opciones.headers },
    });
  } catch {
    throw construirError(0, null);
  }

  const texto = await respuesta.text();
  let cuerpo: unknown = null;
  if (texto) {
    try {
      cuerpo = JSON.parse(texto);
    } catch {
      cuerpo = { detail: texto };
    }
  }

  if (!respuesta.ok) throw construirError(respuesta.status, cuerpo);
  return cuerpo as T;
}

export const apiPublica = {
  get: <T>(ruta: string) => peticionPublica<T>(ruta),
  post: <T>(ruta: string, cuerpo: unknown) =>
    peticionPublica<T>(ruta, { method: 'POST', body: JSON.stringify(cuerpo) }),
};
