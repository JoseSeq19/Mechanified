/**
 * Descarga del instalador de Mechanified para Windows.
 *
 * El archivo vive en el bucket privado `mch-descargas`, cuya única política es
 * de lectura para cualquier cuenta con sesión (ver la migración
 * 20261020000100_organizaciones.sql). Sin sesión no hay enlace: es lo que hace
 * que el producto se entregue a quien tiene cuenta, y no a quien encuentre una
 * URL.
 *
 * Como las fotos de la orden, va del navegador al almacén con la sesión de
 * Supabase, sin pasar por la API: hacer pasar el ejecutable por FastAPI no
 * añadiría ninguna comprobación que la política del bucket no haga ya.
 */
import { supabase } from '@/lib/supabase';

export const BUCKET_DESCARGAS = 'mch-descargas';

/** Ruta del instalador dentro del bucket. La escribe `npm run publicar`. */
export const RUTA_INSTALADOR = 'windows/Mechanified.exe';

/** Pide un enlace firmado de un minuto y arranca la descarga. */
export async function descargarInstalador(): Promise<void> {
  const { data, error } = await supabase.storage
    .from(BUCKET_DESCARGAS)
    .createSignedUrl(RUTA_INSTALADOR, 60, { download: 'Mechanified.exe' });

  if (error || !data) {
    const m = (error?.message ?? '').toLowerCase();
    if (m.includes('not found')) {
      throw new Error('La descarga todavía no está publicada. Vuelve a intentarlo en un rato.');
    }
    throw new Error('No se pudo preparar la descarga. Vuelve a intentarlo.');
  }

  window.location.assign(data.signedUrl);
}
