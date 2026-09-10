/**
 * Sesión del usuario: estado global de autenticación.
 *
 * Además del token, expone `taller_id` y `rol`, que viajan como claims dentro
 * del propio JWT (los inyecta el hook `mch_hook_access_token` de Supabase). Que
 * falten no es un detalle cosmético: sin ellos el backend responde 401 a todo,
 * así que la interfaz lo detecta y lo dice, en vez de dejar al usuario ante
 * pantallas vacías sin explicación.
 */
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import type { Session } from '@supabase/supabase-js';

import { supabase } from '@/lib/supabase';

export type Rol = 'admin_taller' | 'asesor_servicio' | 'tecnico' | 'encargado_repuestos';

export const ETIQUETA_ROL: Record<Rol, string> = {
  admin_taller: 'Administración',
  asesor_servicio: 'Asesoría de servicio',
  tecnico: 'Técnico',
  encargado_repuestos: 'Repuestos',
};

interface ClaimsMechanified {
  taller_id?: string;
  rol?: Rol;
  email?: string;
}

interface ValorSesion {
  sesion: Session | null;
  claims: ClaimsMechanified | null;
  cargando: boolean;
  entrar: (correo: string, clave: string) => Promise<void>;
  salir: () => Promise<void>;
}

const Contexto = createContext<ValorSesion | null>(null);

/** Lee el cuerpo del JWT sin verificar la firma: la verifica el backend. */
function leerClaims(token: string | undefined): ClaimsMechanified | null {
  if (!token) return null;
  try {
    // base64url -> base64, y de ahí a bytes, para decodificar como UTF-8. Un
    // atob() a secas rompería cualquier acento en el nombre o el correo.
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes)) as ClaimsMechanified;
  } catch {
    return null;
  }
}

export function ProveedorSesion({ children }: { children: ReactNode }) {
  const [sesion, setSesion] = useState<Session | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSesion(data.session);
      setCargando(false);
    });

    // Cubre el refresco automático del token y el cierre de sesión en otra
    // pestaña, no solo el login de esta.
    const { data: sub } = supabase.auth.onAuthStateChange((_evento, s) => setSesion(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  const valor = useMemo<ValorSesion>(
    () => ({
      sesion,
      claims: leerClaims(sesion?.access_token),
      cargando,
      entrar: async (correo, clave) => {
        const { error } = await supabase.auth.signInWithPassword({
          email: correo.trim(),
          password: clave,
        });
        if (error) throw new Error(traducirErrorAuth(error.message));
      },
      salir: async () => {
        await supabase.auth.signOut();
      },
    }),
    [sesion, cargando],
  );

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

function traducirErrorAuth(mensaje: string): string {
  const m = mensaje.toLowerCase();
  if (m.includes('invalid login credentials')) return 'Correo o contraseña incorrectos.';
  if (m.includes('email logins are disabled')) {
    return 'El acceso por correo está desactivado en el proyecto de Supabase.';
  }
  if (m.includes('email not confirmed')) return 'La cuenta aún no está confirmada.';
  if (m.includes('failed to fetch')) return 'No se pudo contactar a Supabase.';
  return mensaje;
}

export function useSesion(): ValorSesion {
  const valor = useContext(Contexto);
  if (!valor) throw new Error('useSesion debe usarse dentro de <ProveedorSesion>');
  return valor;
}
