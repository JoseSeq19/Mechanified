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
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { Session } from '@supabase/supabase-js';

import { URL_SITIO } from '@/lib/marca';
import { supabase } from '@/lib/supabase';

export type Rol = 'admin_taller' | 'asesor_servicio' | 'tecnico' | 'encargado_repuestos';

export const ETIQUETA_ROL: Record<Rol, string> = {
  admin_taller: 'Administración',
  asesor_servicio: 'Asesoría de servicio',
  tecnico: 'Técnico',
  encargado_repuestos: 'Repuestos',
};

interface Claims {
  /** Identificador del usuario. Es también el id de su perfil. */
  sub?: string;
  taller_id?: string;
  rol?: Rol;
  email?: string;
}

/** Cómo termina un registro: con sesión, o esperando a que confirme el correo. */
export type ResultadoRegistro = 'abierta' | 'confirmar-correo';

interface ValorSesion {
  sesion: Session | null;
  claims: Claims | null;
  cargando: boolean;
  entrar: (correo: string, clave: string) => Promise<void>;
  /** Crea una cuenta de Mechanified. Todavía sin organización. */
  registrar: (correo: string, clave: string, nombre: string) => Promise<ResultadoRegistro>;
  /**
   * Pide un token nuevo. Hace falta después de crear la organización: el token
   * en uso se emitió sin taller, y el siguiente ya lo trae.
   */
  renovar: () => Promise<void>;
  salir: () => Promise<void>;
  /** Cambia la contraseña de quien tiene la sesión abierta. */
  cambiarClave: (clave: string) => Promise<void>;
  /** Pide a Supabase el correo con el enlace para poner una contraseña nueva. */
  pedirRecuperacion: (correo: string) => Promise<void>;
}

const Contexto = createContext<ValorSesion | null>(null);

/**
 * Donde aterriza el enlace del correo de recuperación.
 *
 * Tiene que estar en la lista de redirecciones permitidas del proyecto de
 * Supabase (`additional_redirect_urls` en `supabase/config.toml`): si no, Auth
 * manda a la persona al `site_url` y el enlace no sirve para nada.
 */
export const RUTA_CLAVE_NUEVA = '/clave';

/**
 * La página del sitio donde una cuenta descarga Mechanified y crea su
 * organización. Es también a donde vuelve el enlace de confirmación del
 * registro, así que, como la de arriba, tiene que estar autorizada en Auth.
 */
export const RUTA_CUENTA = '/cuenta';

/** Lee el cuerpo del JWT sin verificar la firma: la verifica el backend. */
function leerClaims(token: string | undefined): Claims | null {
  if (!token) return null;
  try {
    // base64url -> base64, y de ahí a bytes, para decodificar como UTF-8. Un
    // atob() a secas rompería cualquier acento en el nombre o el correo.
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes)) as Claims;
  } catch {
    return null;
  }
}

export function ProveedorSesion({ children }: { children: ReactNode }) {
  const [sesion, setSesion] = useState<Session | null>(null);
  const [cargando, setCargando] = useState(true);
  const clienteConsultas = useQueryClient();
  const usuarioAnterior = useRef<string | null>(null);

  // Cuando sale un usuario se vacía la caché de consultas. Si en el mismo equipo
  // sale alguien de una organización y entra alguien de otra, lo guardado —el
  // nombre de la organización, la configuración del taller, las órdenes— es
  // del anterior, y se vería hasta que cada consulta se renovara.
  //
  // Solo al salir, no al entrar: este efecto corre después de los de las
  // páginas, que para entonces ya lanzaron sus consultas. Vaciar ahí dejaba a
  // la página esperando la respuesta de una consulta que ya no existía.
  const usuario = sesion?.user.id ?? null;
  useEffect(() => {
    if (usuarioAnterior.current !== null && usuarioAnterior.current !== usuario) {
      clienteConsultas.clear();
    }
    usuarioAnterior.current = usuario;
  }, [usuario, clienteConsultas]);

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
      registrar: async (correo, clave, nombre) => {
        const { data, error } = await supabase.auth.signUp({
          email: correo.trim(),
          password: clave,
          options: {
            data: { nombre_completo: nombre.trim() },
            // Si el proyecto pide confirmar el correo, el enlace vuelve aquí.
            emailRedirectTo: `${URL_SITIO}${RUTA_CUENTA}`,
          },
        });
        if (error) throw new Error(traducirErrorAuth(error.message));
        return data.session ? 'abierta' : 'confirmar-correo';
      },
      renovar: async () => {
        const { error } = await supabase.auth.refreshSession();
        if (error) throw new Error(traducirErrorAuth(error.message));
      },
      salir: async () => {
        await supabase.auth.signOut();
      },
      // Va directo a Supabase, sin pasar por la API: así el backend nunca ve
      // una contraseña. La sesión abierta es la autorización.
      cambiarClave: async (clave) => {
        const { error } = await supabase.auth.updateUser({ password: clave });
        if (error) throw new Error(traducirErrorAuth(error.message));
      },
      // Este correo lo manda Supabase con su propia plantilla, no el worker de
      // Mechanified. No es una inconsistencia: quien ha olvidado su contraseña
      // no tiene sesión, y sin sesión RLS no le deja encolar nada en
      // `notificaciones`. Si pudiera, cualquiera podría provocar correos con el
      // remitente del producto.
      //
      // El enlace vuelve al sitio y no a `localhost`: desde la aplicación de
      // escritorio, el correo se suele abrir en otro dispositivo.
      pedirRecuperacion: async (correo) => {
        const { error } = await supabase.auth.resetPasswordForEmail(correo.trim(), {
          redirectTo: `${URL_SITIO}${RUTA_CLAVE_NUEVA}`,
        });
        if (error) throw new Error(traducirErrorAuth(error.message));
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
  if (m.includes('for security purposes') || m.includes('rate limit')) {
    return 'Se pidió demasiadas veces seguidas. Espera un minuto y vuelve a intentarlo.';
  }
  if (m.includes('redirect') && m.includes('not allowed')) {
    return 'El proyecto de Supabase no tiene autorizada la dirección de retorno de la aplicación.';
  }
  if (m.includes('password should be at least')) {
    const minimo = mensaje.match(/\d+/)?.[0] ?? '6';
    return `La contraseña necesita al menos ${minimo} caracteres.`;
  }
  if (m.includes('should be different from the old password')) {
    return 'La contraseña nueva tiene que ser distinta de la actual.';
  }
  if (m.includes('user already registered')) {
    return 'Ya hay una cuenta con ese correo. Inicia sesión con ella.';
  }
  if (m.includes('signups not allowed') || m.includes('signup is disabled')) {
    return 'El registro de cuentas nuevas está cerrado en este momento.';
  }
  if (m.includes('invalid format') || (m.includes('email address') && m.includes('invalid'))) {
    return 'Ese correo no tiene un formato válido.';
  }
  return mensaje;
}

export function useSesion(): ValorSesion {
  const valor = useContext(Contexto);
  if (!valor) throw new Error('useSesion debe usarse dentro de <ProveedorSesion>');
  return valor;
}
