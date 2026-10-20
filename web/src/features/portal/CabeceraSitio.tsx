import { useEffect, useId, useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';

import { RUTA_CUENTA, useSesion } from '@/app/sesion';
import { PRODUCTO } from '@/lib/marca';
import { IconoCerrar, IconoMenu } from './iconos';
import { LogoSitio } from './LogoSitio';

/** Las secciones de la presentación a las que se puede saltar. */
const SECCIONES = [
  { id: 'recorrido', texto: 'Cómo funciona' },
  { id: 'sedes', texto: 'Varias sedes' },
  { id: 'empezar', texto: 'Empezar' },
];

/** Si la página ya no está arriba del todo: la cabecera se vuelve translúcida. */
function useDesplazada(): boolean {
  const [desplazada, setDesplazada] = useState(() => window.scrollY > 8);

  useEffect(() => {
    const alDesplazar = () => setDesplazada(window.scrollY > 8);
    window.addEventListener('scroll', alDesplazar, { passive: true });
    return () => window.removeEventListener('scroll', alDesplazar);
  }, []);

  return desplazada;
}

/**
 * Enlace a una sección de la presentación. En la propia presentación es un
 * ancla y el navegador hace el resto; desde otra página lleva a `/` con la
 * sección en la dirección, y `PaginaInicio` baja hasta ella al abrirse.
 */
function EnlaceSeccion({ id, children }: { id: string; children: ReactNode }) {
  const enInicio = useLocation().pathname === '/';
  return enInicio ? <a href={`#${id}`}>{children}</a> : <Link to={`/#${id}`}>{children}</Link>;
}

/**
 * Cabecera común del sitio, negra en todas las páginas. Con sesión abierta, el
 * atajo es a la cuenta; sin ella, a entrar o crear una. En las páginas que ya
 * son eso —entrar, la cuenta— los botones sobran y se quitan con `sinAcciones`.
 *
 * En pantallas estrechas las secciones y los botones pasan a un menú
 * desplegable.
 */
export function CabeceraSitio({
  conSecciones = false,
  sinAcciones = false,
}: {
  conSecciones?: boolean;
  sinAcciones?: boolean;
}) {
  const { sesion } = useSesion();
  const desplazada = useDesplazada();
  const [menuAbierto, setMenuAbierto] = useState(false);
  const idMenu = useId();
  const hayMenu = conSecciones || !sinAcciones;

  useEffect(() => {
    if (!menuAbierto) return;
    const alPulsar = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuAbierto(false);
    };
    document.addEventListener('keydown', alPulsar);
    return () => document.removeEventListener('keydown', alPulsar);
  }, [menuAbierto]);

  const cerrar = () => setMenuAbierto(false);

  const acciones = (alElegir?: () => void) =>
    sinAcciones ? null : sesion ? (
      <Link to={RUTA_CUENTA} className="mch-boton mch-boton--oscuro" onClick={alElegir}>
        Mi cuenta
      </Link>
    ) : (
      <>
        <Link to="/entrar" className="mch-sitio-cabecera__enlace" onClick={alElegir}>
          Entrar
        </Link>
        <Link to="/entrar?registro" className="mch-boton mch-boton--oscuro" onClick={alElegir}>
          Crear cuenta
        </Link>
      </>
    );

  // Con el menú abierto, negra del todo: arriba de la página lo que queda
  // detrás de la cabecera es el fondo claro, y translúcida se vería gris.
  const clases = ['mch-sitio-cabecera'];
  if (menuAbierto) clases.push('mch-sitio-cabecera--abierta');
  else if (desplazada) clases.push('mch-sitio-cabecera--desplazada');

  return (
    <header className={clases.join(' ')}>
      <div className="mch-sitio-ancho mch-sitio-cabecera__fila">
        <Link to="/" className="mch-sitio-cabecera__marca" aria-label={`${PRODUCTO}, inicio`}>
          <LogoSitio />
        </Link>

        {conSecciones && (
          <nav className="mch-sitio-cabecera__secciones" aria-label="Secciones">
            {SECCIONES.map((s) => (
              <a key={s.id} href={`#${s.id}`}>
                {s.texto}
              </a>
            ))}
          </nav>
        )}

        {!sinAcciones && <div className="mch-sitio-cabecera__acciones">{acciones()}</div>}

        {hayMenu && (
          <button
            type="button"
            className="mch-sitio-cabecera__menu"
            aria-expanded={menuAbierto}
            aria-controls={idMenu}
            aria-label={menuAbierto ? 'Cerrar el menú' : 'Abrir el menú'}
            onClick={() => setMenuAbierto((abierto) => !abierto)}
          >
            {menuAbierto ? <IconoCerrar /> : <IconoMenu />}
          </button>
        )}
      </div>

      {hayMenu && (
        <div id={idMenu} className="mch-sitio-cabecera__desplegable" hidden={!menuAbierto}>
          <div className="mch-sitio-ancho">
            {conSecciones && (
              <nav className="mch-sitio-cabecera__desplegable-secciones" aria-label="Secciones">
                {SECCIONES.map((s) => (
                  <a key={s.id} href={`#${s.id}`} onClick={cerrar}>
                    {s.texto}
                  </a>
                ))}
              </nav>
            )}
            {!sinAcciones && (
              <div className="mch-sitio-cabecera__desplegable-acciones">{acciones(cerrar)}</div>
            )}
          </div>
        </div>
      )}
    </header>
  );
}

export function PieSitio() {
  const { sesion } = useSesion();

  return (
    <footer className="mch-sitio-pie">
      <div className="mch-sitio-cuadricula mch-sitio-pie__cuadricula" aria-hidden="true" />
      <div className="mch-sitio-ancho mch-sitio-pie__contenido">
        <div className="mch-sitio-pie__fila">
          <div className="mch-sitio-pie__marca">
            <LogoSitio conLema />
            <p>Gestión de talleres mecánicos, para un taller solo o para un grupo con varias sedes.</p>
          </div>

          <nav className="mch-sitio-pie__columnas" aria-label="Pie de página">
            <div>
              <h2>El producto</h2>
              <ul>
                {SECCIONES.map((s) => (
                  <li key={s.id}>
                    <EnlaceSeccion id={s.id}>{s.texto}</EnlaceSeccion>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h2>Tu cuenta</h2>
              <ul>
                {sesion ? (
                  <li>
                    <Link to={RUTA_CUENTA}>Mi cuenta</Link>
                  </li>
                ) : (
                  <>
                    <li>
                      <Link to="/entrar">Entrar</Link>
                    </li>
                    <li>
                      <Link to="/entrar?registro">Crear cuenta</Link>
                    </li>
                  </>
                )}
              </ul>
            </div>
          </nav>
        </div>

        <div className="mch-sitio-pie__base">
          <span>
            © {new Date().getFullYear()} {PRODUCTO}
          </span>
          <span>Para Windows 10 u 11</span>
        </div>
      </div>
    </footer>
  );
}

/**
 * Cabecera y pie del sitio alrededor de una página que no es solo del sitio:
 * la de contraseña nueva, que también usa la aplicación.
 */
export function MarcoSitio({ children }: { children: ReactNode }) {
  return (
    <div className="mch-sitio">
      <CabeceraSitio sinAcciones />
      {children}
      <PieSitio />
    </div>
  );
}
