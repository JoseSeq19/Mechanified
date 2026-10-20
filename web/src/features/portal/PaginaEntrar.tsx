/**
 * Entrar o crear una cuenta de Mechanified, en el sitio.
 *
 * Es el paso previo a la descarga: el instalador solo se entrega a quien tiene
 * cuenta (ver `descarga.ts`). La cuenta nace sin organización; crearla, o pedir
 * que la creemos, viene después, en `/cuenta` o al abrir la aplicación.
 *
 * La pestaña va en la dirección: `?registro` abre la de crear cuenta, que es a
 * donde llevan los botones de "Crear cuenta" del resto del sitio, y así esos
 * enlaces también cambian de pestaña cuando ya se está en esta página.
 */
import { useEffect, useState, type FormEvent } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';

import { Aviso, Boton, Campo } from '@/components/ui';
import { RUTA_CUENTA, useSesion } from '@/app/sesion';
import { Recuperacion } from '@/features/auth/PaginaLogin';
import { CabeceraSitio, PieSitio } from './CabeceraSitio';
import { IconoFlecha, IconoVisto, IconoVistoCirculo } from './iconos';

type Pestana = 'entrar' | 'registro' | 'recuperar';

/** El mínimo que se pide aquí. Supabase exige 6; 8 es lo razonable. */
const CLAVE_MINIMA = 8;

const TITULOS: Record<Pestana, string> = {
  entrar: 'Entra en tu cuenta',
  registro: 'Crea tu cuenta y descarga Mechanified',
  recuperar: 'Recupera tu contraseña',
};

const LO_QUE_DA_LA_CUENTA = [
  {
    titulo: 'Descarga Mechanified',
    texto: 'El programa para Windows. Se abre en tu navegador y no hay que instalar nada.',
  },
  {
    titulo: 'Crea tu organización',
    texto: 'Tú mismo, en un minuto, o pídenos que la creemos.',
  },
  {
    titulo: 'Entra en la aplicación',
    texto:
      'Con esta misma cuenta. Al resto de tu gente le crea la suya la administración de su sede.',
  },
];

export function PaginaEntrar() {
  const { sesion, cargando } = useSesion();
  const [parametros, setParametros] = useSearchParams();
  const pestana: Pestana = parametros.has('registro')
    ? 'registro'
    : parametros.has('recuperar')
      ? 'recuperar'
      : 'entrar';

  const cambiarA = (nueva: Pestana) =>
    setParametros(nueva === 'entrar' ? {} : { [nueva]: '' }, { replace: true });

  useEffect(() => {
    document.title = pestana === 'registro' ? 'Crear cuenta · Mechanified' : 'Entrar · Mechanified';
  }, [pestana]);

  if (!cargando && sesion) return <Navigate to={RUTA_CUENTA} replace />;

  return (
    <div className="mch-sitio">
      <CabeceraSitio sinAcciones />
      <main className="mch-sitio-acceso">
        <div className="mch-sitio-ancho mch-sitio-acceso__rejilla">
          <section className="mch-sitio-acceso__lema" aria-labelledby="titulo-acceso">
            <div className="mch-sitio-cuadricula mch-sitio-destacado__cuadricula" aria-hidden="true" />
            <div>
              <p className="mch-sitio-antetitulo">
                <IconoVistoCirculo />
                Tu cuenta de Mechanified
              </p>
              <h1 id="titulo-acceso">{TITULOS[pestana]}</h1>
            </div>
            <ul className="mch-sitio-vistos">
              {LO_QUE_DA_LA_CUENTA.map((l) => (
                <li key={l.titulo}>
                  <IconoVisto />
                  <div>
                    <strong>{l.titulo}</strong>
                    <span>{l.texto}</span>
                  </div>
                </li>
              ))}
            </ul>
          </section>

          <div className="mch-sitio-acceso__caja">
            {pestana !== 'recuperar' && (
              <div className="mch-sitio-pestanas" role="tablist" aria-label="Acceso">
                <button
                  type="button"
                  role="tab"
                  aria-selected={pestana === 'entrar'}
                  className={`mch-sitio-pestana${pestana === 'entrar' ? ' mch-sitio-pestana--activa' : ''}`}
                  onClick={() => cambiarA('entrar')}
                >
                  Entrar
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={pestana === 'registro'}
                  className={`mch-sitio-pestana${pestana === 'registro' ? ' mch-sitio-pestana--activa' : ''}`}
                  onClick={() => cambiarA('registro')}
                >
                  Crear cuenta
                </button>
              </div>
            )}

            {pestana === 'entrar' && <Entrar onRecuperar={() => cambiarA('recuperar')} />}
            {pestana === 'registro' && <Registro onYaTengo={() => cambiarA('entrar')} />}
            {pestana === 'recuperar' && <Recuperacion onVolver={() => cambiarA('entrar')} />}
          </div>
        </div>
      </main>
      <PieSitio />
    </div>
  );
}

function Entrar({ onRecuperar }: { onRecuperar: () => void }) {
  const { entrar } = useSesion();
  const navegar = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function alEnviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setError(null);
    setEnviando(true);
    try {
      await entrar(String(f.get('correo') ?? ''), String(f.get('clave') ?? ''));
      navegar(RUTA_CUENTA, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo iniciar sesión.');
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form onSubmit={alEnviar} className="mch-panel mch-sitio-acceso__formulario">
      <Campo etiqueta="Correo" name="correo" type="email" autoComplete="username" required autoFocus />
      <Campo
        etiqueta="Contraseña"
        name="clave"
        type="password"
        autoComplete="current-password"
        required
      />
      {error && <Aviso tono="error">{error}</Aviso>}
      <Boton type="submit" cargando={enviando}>
        {enviando ? (
          'Entrando…'
        ) : (
          <>
            Entrar
            <IconoFlecha />
          </>
        )}
      </Boton>
      <button type="button" className="mch-acceso__enlace" onClick={onRecuperar}>
        No recuerdo mi contraseña
      </button>
    </form>
  );
}

function Registro({ onYaTengo }: { onYaTengo: () => void }) {
  const { registrar } = useSesion();
  const navegar = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [porConfirmar, setPorConfirmar] = useState<string | null>(null);

  async function alEnviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const correo = String(f.get('correo') ?? '').trim();
    const clave = String(f.get('clave') ?? '');

    if (clave !== String(f.get('repetida') ?? '')) {
      setError('Las dos contraseñas no coinciden.');
      return;
    }

    setError(null);
    setEnviando(true);
    try {
      const resultado = await registrar(correo, clave, String(f.get('nombre') ?? ''));
      if (resultado === 'abierta') navegar(RUTA_CUENTA, { replace: true });
      else setPorConfirmar(correo);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo crear la cuenta.');
    } finally {
      setEnviando(false);
    }
  }

  // El mismo mensaje exista o no la cuenta: Supabase no lo distingue a
  // propósito, y decirlo aquí convertiría el formulario en una forma de
  // averiguar quién está registrado.
  if (porConfirmar) {
    return (
      <div className="mch-panel mch-sitio-acceso__formulario">
        <Aviso tono="info">
          Si <strong>{porConfirmar}</strong> no tenía cuenta, te acabamos de mandar un correo para
          confirmarla. Abre el enlace y volverás aquí con la sesión abierta. Si ya la tenía, entra
          con tu contraseña.
        </Aviso>
        <Boton variante="secundario" onClick={onYaTengo}>
          Ir a entrar
        </Boton>
      </div>
    );
  }

  return (
    <form onSubmit={alEnviar} className="mch-panel mch-sitio-acceso__formulario">
      <p className="mch-sitio-acceso__intro">
        Con esta cuenta descargas Mechanified, creas tu organización y entras en la aplicación.
      </p>
      <Campo etiqueta="Tu nombre" name="nombre" autoComplete="name" required minLength={2} autoFocus />
      <Campo etiqueta="Correo" name="correo" type="email" autoComplete="email" required />
      <Campo
        etiqueta="Contraseña"
        name="clave"
        type="password"
        autoComplete="new-password"
        required
        minLength={CLAVE_MINIMA}
        ayuda={`Al menos ${CLAVE_MINIMA} caracteres.`}
      />
      <Campo
        etiqueta="Repítela"
        name="repetida"
        type="password"
        autoComplete="new-password"
        required
        minLength={CLAVE_MINIMA}
      />
      {error && <Aviso tono="error">{error}</Aviso>}
      <Boton type="submit" cargando={enviando}>
        {enviando ? (
          'Creando…'
        ) : (
          <>
            Crear cuenta
            <IconoFlecha />
          </>
        )}
      </Boton>
      <button type="button" className="mch-acceso__enlace" onClick={onYaTengo}>
        Ya tengo cuenta
      </button>
    </form>
  );
}
