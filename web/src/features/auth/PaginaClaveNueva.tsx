/**
 * Donde aterriza el enlace del correo de recuperación.
 *
 * Supabase verifica el token del correo y redirige aquí con la sesión en el
 * fragmento de la URL (`#access_token=…&type=recovery`). El cliente de este
 * proyecto tiene `detectSessionInUrl` apagado a propósito —la aplicación no usa
 * enlaces mágicos ni OAuth—, así que ese fragmento lo lee esta página, y solo
 * esta, y solo cuando el tipo es `recovery`.
 *
 * También se contempla el otro formato posible, `?code=…`, que es el que usa
 * Supabase cuando el proyecto trabaja con el flujo PKCE. Son dos líneas y
 * evitan que un cambio de configuración del proyecto deje a la gente sin poder
 * recuperar su cuenta.
 */
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { Aviso, Boton, Campo, Cargando, Logo } from '@/components/ui';
import { ES_SITIO } from '@/lib/marca';
import { supabase } from '@/lib/supabase';
import { RUTA_CUENTA, useSesion } from '@/app/sesion';

type Estado = 'abriendo' | 'listo-para-cambiar' | 'enlace-invalido' | 'cambiada';

export function PaginaClaveNueva() {
  const { cambiarClave } = useSesion();
  const navegar = useNavigate();

  const [estado, setEstado] = useState<Estado>('abriendo');
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    let vigente = true;

    async function abrirSesionDeRecuperacion() {
      const hash = new URLSearchParams(window.location.hash.replace(/^#/, ''));
      const consulta = new URLSearchParams(window.location.search);

      const descripcion = hash.get('error_description') ?? consulta.get('error_description');
      const accessToken = hash.get('access_token');
      const refreshToken = hash.get('refresh_token');
      const codigo = consulta.get('code');

      // El fragmento lleva la sesión en claro: se quita de la barra de
      // direcciones en cuanto se ha leído, para que no quede en el historial
      // ni se copie al compartir el enlace.
      if (window.location.hash || codigo) {
        window.history.replaceState(null, '', window.location.pathname);
      }

      if (descripcion) {
        if (vigente) {
          setError(traducirErrorEnlace(descripcion));
          setEstado('enlace-invalido');
        }
        return;
      }

      if (accessToken && refreshToken) {
        const { error: fallo } = await supabase.auth.setSession({
          access_token: accessToken,
          refresh_token: refreshToken,
        });
        if (vigente) {
          setError(fallo ? fallo.message : null);
          setEstado(fallo ? 'enlace-invalido' : 'listo-para-cambiar');
        }
        return;
      }

      if (codigo) {
        const { error: fallo } = await supabase.auth.exchangeCodeForSession(codigo);
        if (vigente) {
          setError(fallo ? fallo.message : null);
          setEstado(fallo ? 'enlace-invalido' : 'listo-para-cambiar');
        }
        return;
      }

      // Sin tokens en la URL: o el enlace se usó ya, o alguien llegó aquí a
      // mano. Si por lo que sea hay sesión abierta, cambiar la contraseña sigue
      // siendo una operación válida, así que se deja continuar.
      const { data } = await supabase.auth.getSession();
      if (vigente) setEstado(data.session ? 'listo-para-cambiar' : 'enlace-invalido');
    }

    void abrirSesionDeRecuperacion();
    return () => {
      vigente = false;
    };
  }, []);

  async function alEnviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const nueva = String(f.get('nueva') ?? '');
    const repetida = String(f.get('repetida') ?? '');

    if (nueva !== repetida) {
      setError('Las dos contraseñas no coinciden.');
      return;
    }

    setError(null);
    setGuardando(true);
    try {
      await cambiarClave(nueva);
      setEstado('cambiada');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo cambiar la contraseña.');
    } finally {
      setGuardando(false);
    }
  }

  return (
    <main className="mch-acceso">
      <div className="mch-acceso__caja">
        {/* En el sitio la marca ya está en la cabecera (ver `MarcoSitio`). */}
        <div style={{ marginBottom: 'var(--mch-esp-6)' }}>
          {ES_SITIO ? (
            <h1 className="mch-sitio-titulo-pagina">Contraseña nueva</h1>
          ) : (
            <>
              <Logo />
              <p className="mch-acceso__nota">Contraseña nueva</p>
            </>
          )}
        </div>

        {estado === 'abriendo' && (
          <div className="mch-panel">
            <Cargando texto="Comprobando el enlace…" />
          </div>
        )}

        {estado === 'enlace-invalido' && (
          <div className="mch-panel" style={{ padding: 'var(--mch-esp-6)' }}>
            <Aviso tono="error">
              {error ?? 'Este enlace ya no sirve. Los de recuperación caducan y valen una vez.'}
            </Aviso>
            <p style={{ marginTop: 'var(--mch-esp-4)', fontSize: 'var(--mch-txt-sm)' }}>
              <Link to={ES_SITIO ? '/entrar' : '/'}>Volver a pedir uno</Link>
            </p>
          </div>
        )}

        {estado === 'listo-para-cambiar' && (
          <form
            onSubmit={alEnviar}
            className="mch-panel"
            style={{ padding: 'var(--mch-esp-6)', display: 'grid', gap: 'var(--mch-esp-4)' }}
          >
            <p style={{ margin: 0, fontSize: 'var(--mch-txt-sm)' }}>
              Escribe la contraseña con la que vas a entrar de ahora en adelante.
            </p>
            {error && <Aviso tono="error">{error}</Aviso>}
            <Campo
              etiqueta="Contraseña nueva"
              name="nueva"
              type="password"
              autoComplete="new-password"
              required
              autoFocus
            />
            <Campo
              etiqueta="Repítela"
              name="repetida"
              type="password"
              autoComplete="new-password"
              required
            />
            <Boton type="submit" cargando={guardando}>
              Guardar y entrar
            </Boton>
          </form>
        )}

        {/* En el sitio no hay taller al que entrar: el trabajo se hace en la
            aplicación de escritorio, que es donde hay que usar la contraseña. */}
        {estado === 'cambiada' && ES_SITIO && (
          <div className="mch-panel" style={{ padding: 'var(--mch-esp-6)' }}>
            <Aviso tono="info">
              Contraseña cambiada. Úsala para entrar en Mechanified desde tu computador.
            </Aviso>
            <div style={{ marginTop: 'var(--mch-esp-4)' }}>
              <Boton onClick={() => navegar(RUTA_CUENTA, { replace: true })}>Ir a mi cuenta</Boton>
            </div>
          </div>
        )}

        {estado === 'cambiada' && !ES_SITIO && (
          <div className="mch-panel" style={{ padding: 'var(--mch-esp-6)' }}>
            <Aviso tono="info">
              Contraseña cambiada. La sesión ya está abierta con la cuenta del enlace.
            </Aviso>
            <div style={{ marginTop: 'var(--mch-esp-4)' }}>
              <Boton onClick={() => navegar('/ordenes', { replace: true })}>
                Entrar al taller
              </Boton>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

function traducirErrorEnlace(descripcion: string): string {
  const d = descripcion.toLowerCase();
  if (d.includes('expired')) {
    return 'El enlace caducó. Pide otro desde la pantalla de acceso.';
  }
  if (d.includes('invalid') || d.includes('not found')) {
    return 'Este enlace no es válido. Puede que ya se haya usado: solo sirve una vez.';
  }
  return descripcion;
}
