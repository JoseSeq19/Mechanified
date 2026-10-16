/**
 * Adjuntos de una orden: fotos de recepción, del diagnóstico y de la entrega.
 *
 * El archivo **no pasa por la API de La Meseta**. Va directo al bucket privado
 * `mch-evidencias` con la sesión de Supabase de quien lo sube, y después se
 * registran los metadatos en la API. Son dos sistemas con la misma regla: la
 * política del bucket compara la primera carpeta de la ruta contra el taller de
 * quien pide, y RLS filtra la fila por `taller_id`.
 *
 * Por eso la convención de la ruta es un contrato, igual que las rutas públicas
 * de los enlaces por correo:
 *
 *     {taller_id}/{orden_id}/{uuid}-{nombre}
 *
 * La valida `app/modules/adjuntos/service.py` y la refuerza el trigger
 * `mch_adjuntos_ruta_guard`. Cambiarla aquí sin cambiarla allí deja de poder
 * registrar nada.
 */
import { api } from '@/lib/api';
import { supabase } from '@/lib/supabase';

const BUCKET = 'mch-evidencias';

/** Lo que acepta el bucket. Declarado en la migración 001000. */
export const MIMES_PERMITIDOS = [
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/heic',
  'application/pdf',
] as const;

/** 25 MiB, el tope del bucket. */
export const TAMANO_MAXIMO = 26_214_400;

export type ContextoAdjunto = 'ingreso' | 'diagnostico' | 'reparacion' | 'calidad' | 'entrega';

export const ETIQUETA_CONTEXTO: Record<ContextoAdjunto, string> = {
  ingreso: 'Recepción',
  diagnostico: 'Diagnóstico',
  reparacion: 'Reparación',
  calidad: 'Control de calidad',
  entrega: 'Entrega',
};

export interface Adjunto {
  id: string;
  orden_id: string;
  contexto: ContextoAdjunto;
  contexto_etiqueta: string;
  ruta_storage: string;
  nombre_archivo: string;
  mime: string | null;
  tamano_bytes: number | null;
  descripcion: string | null;
  autor_nombre: string | null;
  /** Lo calcula la API con la misma regla que la política de borrado. */
  puede_borrar: boolean;
  creado_en: string;
}

export const listarAdjuntos = (ordenId: string) =>
  api.get<Adjunto[]>(`/ordenes/${ordenId}/adjuntos`);

/**
 * Deja el nombre como puede ir dentro de una ruta del bucket.
 *
 * El último tramo de la ruta se escribe tal cual en una URL firmada, así que un
 * espacio o un acento ahí rompen la descarga. El nombre bonito viaja aparte, en
 * los metadatos, que es lo que se le muestra a la gente.
 */
function nombreParaRuta(nombre: string): string {
  const limpio = nombre
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^A-Za-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '');
  // 180 es el tope del backend para el tramo completo, y delante va un uuid.
  return (limpio || 'archivo').slice(0, 120);
}

/**
 * Identificador único para el nombre del objeto.
 *
 * `crypto.randomUUID` solo existe en contexto seguro —https o localhost—, y un
 * taller que se sirva la aplicación por http en una IP de su red local se
 * quedaría sin poder subir nada, con un error que no explica nada. El respaldo
 * usa `getRandomValues`, que sí está siempre, y si tampoco, la hora: la ruta
 * lleva delante el taller y la orden, así que lo único que se arriesga es un
 * choque de nombres dentro de la misma orden, y eso la API lo responde como
 * conflicto.
 */
function identificador(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  }
  return `${Date.now().toString(16)}${Math.random().toString(16).slice(2, 10)}`;
}

export function componerRuta(tallerId: string, ordenId: string, nombre: string): string {
  return `${tallerId}/${ordenId}/${identificador()}-${nombreParaRuta(nombre)}`;
}

/** Qué le pasa al archivo antes de salir del navegador. */
export function revisarArchivo(archivo: File): string | null {
  if (!MIMES_PERMITIDOS.includes(archivo.type as (typeof MIMES_PERMITIDOS)[number])) {
    return `${archivo.name}: solo se admiten fotos (JPG, PNG, WebP, HEIC) y PDF.`;
  }
  if (archivo.size > TAMANO_MAXIMO) {
    return `${archivo.name}: pasa de 25 MB. Hazle una foto de menos resolución.`;
  }
  if (archivo.size === 0) return `${archivo.name}: el archivo está vacío.`;
  return null;
}

/**
 * Sube el archivo y registra sus metadatos.
 *
 * Si el registro falla, se borra el objeto que acababa de subirse. Sin esa
 * compensación el bucket acumularía archivos que ninguna ficha menciona y que
 * nadie puede encontrar para borrar.
 */
export async function subirAdjunto(opciones: {
  tallerId: string;
  ordenId: string;
  archivo: File;
  contexto: ContextoAdjunto;
  descripcion?: string | null;
}): Promise<Adjunto> {
  const { tallerId, ordenId, archivo, contexto, descripcion } = opciones;
  const ruta = componerRuta(tallerId, ordenId, archivo.name);

  const { error } = await supabase.storage
    .from(BUCKET)
    .upload(ruta, archivo, { contentType: archivo.type, upsert: false });

  if (error) throw new Error(traducirErrorStorage(error.message, archivo.name));

  try {
    return await api.post<Adjunto>(`/ordenes/${ordenId}/adjuntos`, {
      contexto,
      ruta_storage: ruta,
      nombre_archivo: archivo.name,
      mime: archivo.type,
      tamano_bytes: archivo.size,
      descripcion: descripcion || null,
    });
  } catch (err) {
    await supabase.storage.from(BUCKET).remove([ruta]);
    throw err;
  }
}

/**
 * Borra el registro y después el archivo.
 *
 * En ese orden: la fila es la que tiene la política estricta —solo quien lo
 * subió o administración—, así que si la API dice que no, el archivo se queda
 * donde está.
 */
export async function borrarAdjunto(adjunto: Adjunto): Promise<void> {
  await api.delete(`/adjuntos/${adjunto.id}`);
  await supabase.storage.from(BUCKET).remove([adjunto.ruta_storage]);
}

/** Minutos que vive una URL firmada. Se renueva al volver a cargar la ficha. */
const VIGENCIA_URL_SEG = 600;

/**
 * URLs temporales para mostrar los archivos.
 *
 * El bucket es privado: no hay URL pública que poner en un `<img>`. Se piden
 * todas de una vez porque una ficha con doce fotos haría doce viajes.
 */
export async function urlsFirmadas(rutas: string[]): Promise<Record<string, string>> {
  if (rutas.length === 0) return {};

  const { data, error } = await supabase.storage
    .from(BUCKET)
    .createSignedUrls(rutas, VIGENCIA_URL_SEG);

  if (error) throw new Error(`No se pudieron abrir los archivos: ${error.message}`);

  const porRuta: Record<string, string> = {};
  for (const fila of data ?? []) {
    if (fila.signedUrl && fila.path) porRuta[fila.path] = fila.signedUrl;
  }
  return porRuta;
}

function traducirErrorStorage(mensaje: string, nombre: string): string {
  const m = mensaje.toLowerCase();
  if (m.includes('exceeded the maximum allowed size')) {
    return `${nombre}: pasa del tamaño que acepta el bucket (25 MB).`;
  }
  if (m.includes('mime type') || m.includes('invalid_mime_type')) {
    return `${nombre}: el bucket no acepta ese tipo de archivo.`;
  }
  if (m.includes('duplicate') || m.includes('already exists')) {
    return `${nombre}: ya hay un archivo con ese nombre. Vuelve a intentarlo.`;
  }
  if (m.includes('row-level security') || m.includes('unauthorized')) {
    return 'Tu sesión no tiene permiso para subir archivos a este taller.';
  }
  if (m.includes('failed to fetch')) {
    return `${nombre}: no se pudo contactar el almacenamiento de Supabase.`;
  }
  return `${nombre}: ${mensaje}`;
}
