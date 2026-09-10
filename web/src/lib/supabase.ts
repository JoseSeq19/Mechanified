/**
 * Cliente de Supabase, usado **solo para autenticación**.
 *
 * Los datos de negocio nunca se piden desde aquí: van por la API de
 * Mechanified, que es donde vive la lógica. Este cliente existe para abrir y
 * mantener la sesión, y para renovar el token antes de que caduque.
 */
import { createClient } from '@supabase/supabase-js';

const url = import.meta.env.VITE_SUPABASE_URL;
const llaveAnonima = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!url || !llaveAnonima) {
  throw new Error(
    'Faltan VITE_SUPABASE_URL o VITE_SUPABASE_ANON_KEY. Copia web/.env.example a web/.env.',
  );
}

export const supabase = createClient(url, llaveAnonima, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    // La aplicación no usa enlaces mágicos ni OAuth, así que no hay tokens que
    // recoger de la URL.
    detectSessionInUrl: false,
  },
});
