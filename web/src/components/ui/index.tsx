/**
 * Sistema de diseño de Mechanified.
 *
 * Componentes propios sobre los tokens de `styles/tokens.css`. No se usa
 * ninguna librería de componentes con identidad visual propia: la apariencia de
 * la aplicación tiene que ser nuestra.
 */
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react';
import { useEffect, useId } from 'react';

/* --- Marca -------------------------------------------------------------- */

export function Marca({ compacta = false }: { compacta?: boolean }) {
  return (
    <span className="mch-marca">
      <span className="mch-marca__glifo" aria-hidden="true">
        M
      </span>
      {!compacta && <span>Mechanified</span>}
    </span>
  );
}

/* --- Botón -------------------------------------------------------------- */

type VarianteBoton = 'primario' | 'secundario' | 'peligro' | 'fantasma';

interface PropsBoton extends ButtonHTMLAttributes<HTMLButtonElement> {
  variante?: VarianteBoton;
  cargando?: boolean;
}

export function Boton({
  variante = 'primario',
  cargando = false,
  disabled,
  children,
  className = '',
  ...resto
}: PropsBoton) {
  const clases = ['mch-boton'];
  if (variante !== 'primario') clases.push(`mch-boton--${variante}`);
  if (className) clases.push(className);

  return (
    <button className={clases.join(' ')} disabled={disabled || cargando} {...resto}>
      {cargando && <span className="mch-cargando" aria-hidden="true" />}
      {children}
    </button>
  );
}

/* --- Campos ------------------------------------------------------------- */

interface PropsCampo extends InputHTMLAttributes<HTMLInputElement> {
  etiqueta: string;
  ayuda?: string;
  error?: string;
}

export function Campo({ etiqueta, ayuda, error, id, ...resto }: PropsCampo) {
  const generado = useId();
  const idCampo = id ?? generado;

  return (
    <div className="mch-campo">
      <label className="mch-campo__etiqueta" htmlFor={idCampo}>
        {etiqueta}
      </label>
      <input
        id={idCampo}
        className="mch-campo__control"
        aria-invalid={error ? true : undefined}
        aria-describedby={ayuda || error ? `${idCampo}-ayuda` : undefined}
        {...resto}
      />
      {(ayuda || error) && (
        <span id={`${idCampo}-ayuda`} className={error ? 'mch-campo__error' : 'mch-campo__ayuda'}>
          {error ?? ayuda}
        </span>
      )}
    </div>
  );
}

interface PropsSelector extends SelectHTMLAttributes<HTMLSelectElement> {
  etiqueta: string;
  opciones: { valor: string; texto: string }[];
}

export function Selector({ etiqueta, opciones, id, ...resto }: PropsSelector) {
  const generado = useId();
  const idCampo = id ?? generado;

  return (
    <div className="mch-campo">
      <label className="mch-campo__etiqueta" htmlFor={idCampo}>
        {etiqueta}
      </label>
      <select id={idCampo} className="mch-campo__control" {...resto}>
        {opciones.map((o) => (
          <option key={o.valor} value={o.valor}>
            {o.texto}
          </option>
        ))}
      </select>
    </div>
  );
}

/* --- Aviso -------------------------------------------------------------- */

export function Aviso({
  tono = 'info',
  children,
}: {
  tono?: 'info' | 'alerta' | 'error';
  children: ReactNode;
}) {
  return (
    <div className={`mch-aviso mch-aviso--${tono}`} role={tono === 'error' ? 'alert' : undefined}>
      <span>{children}</span>
    </div>
  );
}

/* --- Distintivo --------------------------------------------------------- */

export function Distintivo({
  tono = 'neutro',
  children,
}: {
  tono?: 'activo' | 'inactivo' | 'neutro';
  children: ReactNode;
}) {
  return <span className={`mch-distintivo mch-distintivo--${tono}`}>{children}</span>;
}

/* --- Diálogo ------------------------------------------------------------ */

export function Dialogo({
  titulo,
  onCerrar,
  children,
  pie,
}: {
  titulo: string;
  onCerrar: () => void;
  children: ReactNode;
  pie?: ReactNode;
}) {
  // Escape cierra el diálogo: se espera de cualquier modal y evita dejar al
  // usuario atrapado si el ratón falla.
  useEffect(() => {
    const alPulsar = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCerrar();
    };
    document.addEventListener('keydown', alPulsar);
    return () => document.removeEventListener('keydown', alPulsar);
  }, [onCerrar]);

  return (
    <div
      className="mch-velo"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onCerrar();
      }}
    >
      <div className="mch-dialogo" role="dialog" aria-modal="true" aria-label={titulo}>
        <header className="mch-dialogo__cabecera">
          <h2 style={{ fontSize: 'var(--mch-txt-lg)' }}>{titulo}</h2>
          <Boton variante="fantasma" onClick={onCerrar} aria-label="Cerrar">
            ✕
          </Boton>
        </header>
        <div className="mch-dialogo__cuerpo">{children}</div>
        {pie && <footer className="mch-dialogo__pie">{pie}</footer>}
      </div>
    </div>
  );
}

/* --- Estados vacíos y de carga ------------------------------------------ */

export function Vacio({ titulo, detalle }: { titulo: string; detalle?: string }) {
  return (
    <div className="mch-vacio">
      <p style={{ margin: 0, fontWeight: 560, color: 'var(--mch-texto)' }}>{titulo}</p>
      {detalle && <p style={{ margin: 'var(--mch-esp-2) 0 0' }}>{detalle}</p>}
    </div>
  );
}

export function Cargando({ texto = 'Cargando…' }: { texto?: string }) {
  return (
    <div className="mch-vacio">
      <span className="mch-cargando" aria-hidden="true" />
      <span style={{ marginLeft: 'var(--mch-esp-3)' }}>{texto}</span>
    </div>
  );
}

/* --- Sección ------------------------------------------------------------ */

/**
 * Bloque con cabecera, resumen y una acción a la derecha.
 *
 * La ficha de orden apila varios (diagnóstico, mano de obra, repuestos) y todos
 * tienen la misma forma; sin esto, cada panel repetiría la misma cabecera con
 * estilos en línea ligeramente distintos.
 */
export function Seccion({
  titulo,
  resumen,
  accion,
  children,
}: {
  titulo: string;
  resumen?: ReactNode;
  accion?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="mch-panel">
      <header className="mch-seccion__cabecera">
        <div>
          <h2 className="mch-seccion__titulo">{titulo}</h2>
          {resumen && <p className="mch-seccion__resumen">{resumen}</p>}
        </div>
        {accion}
      </header>
      {children}
    </section>
  );
}
