import { NavLink, Outlet } from 'react-router-dom';

import { Aviso, Marca } from '@/components/ui';
import { ETIQUETA_ROL, useSesion } from './sesion';

/** Módulos aún no construidos. Se listan para que el alcance quede visible. */
const PROXIMAMENTE = ['Informes'];

export function Layout() {
  const { sesion, claims, salir } = useSesion();

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
          <NavLink to="/clientes" className="mch-nav__enlace">
            Clientes
          </NavLink>
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
          <button className="mch-rail__salir" onClick={() => void salir()}>
            Cerrar sesión
          </button>
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
    </div>
  );
}
