import { Link } from 'react-router-dom';

import { Marca } from '@/components/ui';
import { RUTA_CUENTA, useSesion } from '@/app/sesion';
import { PRODUCTO } from '@/lib/marca';

/**
 * Cabecera común del sitio. Con sesión abierta, el atajo es a la cuenta; sin
 * ella, a entrar o crear una. En las páginas que ya son eso —entrar, la
 * cuenta— los botones sobran y se quitan con `sinAcciones`.
 */
export function CabeceraSitio({
  conSecciones = false,
  sinAcciones = false,
}: {
  conSecciones?: boolean;
  sinAcciones?: boolean;
}) {
  const { sesion } = useSesion();

  return (
    <header className="mch-sitio-cabecera">
      <div className="mch-sitio-ancho mch-sitio-cabecera__fila">
        <Link to="/" className="mch-sitio-cabecera__marca" aria-label={`${PRODUCTO}, inicio`}>
          <Marca />
        </Link>

        {conSecciones && (
          <nav className="mch-sitio-cabecera__secciones" aria-label="Secciones">
            <a href="#recorrido">Cómo funciona</a>
            <a href="#sedes">Varias sedes</a>
            <a href="#empezar">Empezar</a>
          </nav>
        )}

        <div className="mch-sitio-cabecera__acciones">
          {sinAcciones ? null : sesion ? (
            <Link to={RUTA_CUENTA} className="mch-boton">
              Mi cuenta
            </Link>
          ) : (
            <>
              <Link to="/entrar" className="mch-boton mch-boton--fantasma">
                Entrar
              </Link>
              <Link to="/entrar?registro" className="mch-boton">
                Crear cuenta
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

export function PieSitio() {
  return (
    <footer className="mch-sitio-pie">
      <div className="mch-sitio-ancho mch-sitio-pie__fila">
        <Marca />
        <span>Gestión de talleres mecánicos · © {new Date().getFullYear()}</span>
      </div>
    </footer>
  );
}
