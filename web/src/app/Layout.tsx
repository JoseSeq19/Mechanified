import { useState, type FormEvent } from 'react';
import { NavLink, Outlet } from 'react-router-dom';

import { Aviso, Boton, Campo, Dialogo, Marca } from '@/components/ui';
import { ETIQUETA_ROL, useSesion } from './sesion';

/** Módulos aún no construidos. Se listan para que el alcance quede visible. */
const PROXIMAMENTE: string[] = [];

export function Layout() {
  const { sesion, claims, salir } = useSesion();
  const [cambiandoClave, setCambiandoClave] = useState(false);

  return (
    <div className="mch-app">
      <aside className="mch-rail">
        <Marca />

        <nav className="mch-nav">
          <span className="mch-nav__titulo">Taller</span>
          <NavLink to="/ordenes" className="mch-nav__enlace">
            Órdenes
          </NavLink>
          <NavLink to="/vehiculos" className="mch-nav__enlace">
            Vehículos
          </NavLink>
          <NavLink to="/repuestos" className="mch-nav__enlace">
            Repuestos
          </NavLink>
          <NavLink to="/calidad" className="mch-nav__enlace">
            Control de calidad
          </NavLink>
          <NavLink to="/encuestas" className="mch-nav__enlace">
            Satisfacción
          </NavLink>
          <NavLink to="/clientes" className="mch-nav__enlace">
            Clientes
          </NavLink>
          {claims?.rol === 'admin_taller' && (
            <>
              <NavLink to="/informes" className="mch-nav__enlace">
                Panel
              </NavLink>
              <NavLink to="/personal" className="mch-nav__enlace">
                Personal
              </NavLink>
            </>
          )}
          {PROXIMAMENTE.map((m) => (
            <span key={m} className="mch-nav__enlace mch-nav__enlace--inerte">
              {m}
              <span className="mch-nav__pronto">pronto</span>
            </span>
          ))}
        </nav>

        <div className="mch-rail__pie">
          <div>
            <div className="mch-rail__usuario">{claims?.email ?? sesion?.user.email}</div>
            <div className="mch-rail__rol">
              {claims?.rol ? ETIQUETA_ROL[claims.rol] : 'Sin rol'}
            </div>
          </div>
          <div style={{ display: 'grid', gap: 2 }}>
            <button className="mch-rail__salir" onClick={() => setCambiandoClave(true)}>
              Cambiar contraseña
            </button>
            <button className="mch-rail__salir" onClick={() => void salir()}>
              Cerrar sesión
            </button>
          </div>
        </div>
      </aside>

      <main className="mch-contenido">
        {!claims?.taller_id && (
          <div style={{ marginBottom: 'var(--mch-esp-6)' }}>
            <Aviso tono="alerta">
              Tu sesión no trae taller asignado, así que la API va a rechazar todo. Suele
              significar que el hook de Auth está apagado en Supabase, o que tu usuario no
              tiene perfil activo.
            </Aviso>
          </div>
        )}
        <Outlet />
      </main>

      {cambiandoClave && <DialogoClave onCerrar={() => setCambiandoClave(false)} />}
    </div>
  );
}

/**
 * Cambio de contraseña de quien tiene la sesión abierta.
 *
 * Es la otra mitad del alta de personal: a cada quien se le entrega una clave
 * temporal, y esto es lo que le permite dejar de usarla. Va directo a Supabase,
 * sin pasar por la API, para que el backend no vea nunca una contraseña.
 */
function DialogoClave({ onCerrar }: { onCerrar: () => void }) {
  const { cambiarClave } = useSesion();
  const [error, setError] = useState<string | null>(null);
  const [listo, setListo] = useState(false);
  const [guardando, setGuardando] = useState(false);

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
      setListo(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo cambiar la contraseña.');
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Dialogo
      titulo="Cambiar contraseña"
      onCerrar={onCerrar}
      pie={
        listo ? (
          <Boton onClick={onCerrar}>Hecho</Boton>
        ) : (
          <>
            <Boton variante="secundario" type="button" onClick={onCerrar}>
              Cancelar
            </Boton>
            <Boton type="submit" form="formulario-clave" cargando={guardando}>
              Cambiar
            </Boton>
          </>
        )
      }
    >
      {listo ? (
        <Aviso tono="info">
          Contraseña cambiada. La próxima vez que entres, usa la nueva.
        </Aviso>
      ) : (
        <form id="formulario-clave" onSubmit={alEnviar} style={{ display: 'grid', gap: 'var(--mch-esp-4)' }}>
          {error && <Aviso tono="error">{error}</Aviso>}
          <Campo etiqueta="Contraseña nueva" name="nueva" type="password" required autoFocus />
          <Campo etiqueta="Repítela" name="repetida" type="password" required />
        </form>
      )}
    </Dialogo>
  );
}
