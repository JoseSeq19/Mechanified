import { useState, type FormEvent } from 'react';

import { Aviso, Boton, Campo, Marca } from '@/components/ui';
import { useSesion } from '@/app/sesion';
import { URL_SITIO } from '@/lib/marca';

/**
 * Acceso a la aplicación de Mechanified.
 *
 * Aquí la marca es la del producto: todavía no se sabe de qué organización es
 * quien entra. En cuanto entra, la aplicación pasa a llamarse como la suya.
 *
 * No hay registro en esta pantalla. Las cuentas nacen de dos maneras: quien
 * funda una organización se registra en el sitio, y al resto de la gente la da
 * de alta la administración de su sede. Por eso el pie manda al sitio y no a un
 * formulario de aquí.
 */
export function PaginaLogin() {
  const [recuperando, setRecuperando] = useState(false);

  return (
    <main className="mch-acceso">
      <div className="mch-acceso__caja">
        <div style={{ marginBottom: 'var(--mch-esp-6)' }}>
          <Marca />
          <p className="mch-acceso__nota">
            Gestión de talleres mecánicos. Entra con tu cuenta de Mechanified.
          </p>
        </div>

        {recuperando ? (
          <Recuperacion onVolver={() => setRecuperando(false)} />
        ) : (
          <Acceso onRecuperar={() => setRecuperando(true)} />
        )}

        <p className="mch-acceso__pie">
          ¿Trabajas en un taller que ya usa Mechanified? Tu cuenta te la da su administración.
          <br />
          ¿Vas a empezar con tu organización?{' '}
          <a href={`${URL_SITIO}/entrar?registro`} target="_blank" rel="noreferrer">
            Crea tu cuenta en el sitio
          </a>
          .
        </p>
      </div>
    </main>
  );
}

function Acceso({ onRecuperar }: { onRecuperar: () => void }) {
  const { entrar } = useSesion();
  const [correo, setCorreo] = useState('');
  const [clave, setClave] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function alEnviar(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      await entrar(correo, clave);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo iniciar sesión.');
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form
      onSubmit={alEnviar}
      className="mch-panel"
      style={{ padding: 'var(--mch-esp-6)', display: 'grid', gap: 'var(--mch-esp-4)' }}
    >
      <Campo
        etiqueta="Correo"
        type="email"
        autoComplete="username"
        required
        value={correo}
        onChange={(e) => setCorreo(e.target.value)}
      />
      <Campo
        etiqueta="Contraseña"
        type="password"
        autoComplete="current-password"
        required
        value={clave}
        onChange={(e) => setClave(e.target.value)}
      />

      {error && <Aviso tono="error">{error}</Aviso>}

      <Boton type="submit" cargando={enviando}>
        {enviando ? 'Entrando…' : 'Entrar'}
      </Boton>

      <button type="button" className="mch-acceso__enlace" onClick={onRecuperar}>
        No recuerdo mi contraseña
      </button>
    </form>
  );
}

/**
 * Pedir el correo con el enlace para poner una contraseña nueva.
 *
 * Antes esto no existía y la única salida era pedírselo a un administrador del
 * taller. Para quien administra —y más si es el único— eso significaba quedarse
 * fuera hasta que alguien entrara por Supabase.
 *
 * El mensaje de después es el mismo se haya encontrado la cuenta o no, a
 * propósito: decir "ese correo no está registrado" convierte esta pantalla en
 * una forma de averiguar quién trabaja en qué taller.
 */
export function Recuperacion({ onVolver }: { onVolver: () => void }) {
  const { pedirRecuperacion } = useSesion();
  const [correo, setCorreo] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [pedido, setPedido] = useState(false);

  async function alEnviar(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      await pedirRecuperacion(correo);
      setPedido(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo pedir el correo.');
    } finally {
      setEnviando(false);
    }
  }

  if (pedido) {
    return (
      <div className="mch-panel" style={{ padding: 'var(--mch-esp-6)' }}>
        <Aviso tono="info">
          Si esa dirección tiene cuenta, va en camino un correo con un enlace para poner una
          contraseña nueva. Sirve una sola vez y caduca.
        </Aviso>
        <div style={{ marginTop: 'var(--mch-esp-4)' }}>
          <Boton variante="secundario" onClick={onVolver}>
            Volver al acceso
          </Boton>
        </div>
      </div>
    );
  }

  return (
    <form
      onSubmit={alEnviar}
      className="mch-panel"
      style={{ padding: 'var(--mch-esp-6)', display: 'grid', gap: 'var(--mch-esp-4)' }}
    >
      <p style={{ margin: 0, fontSize: 'var(--mch-txt-sm)' }}>
        Escribe el correo con el que entras y te llega un enlace para cambiarla.
      </p>

      <Campo
        etiqueta="Correo"
        type="email"
        autoComplete="username"
        required
        autoFocus
        value={correo}
        onChange={(e) => setCorreo(e.target.value)}
      />

      {error && <Aviso tono="error">{error}</Aviso>}

      <Boton type="submit" cargando={enviando}>
        {enviando ? 'Pidiendo…' : 'Mandarme el enlace'}
      </Boton>

      <button type="button" className="mch-acceso__enlace" onClick={onVolver}>
        Volver al acceso
      </button>
    </form>
  );
}
