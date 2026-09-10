import { useState, type FormEvent } from 'react';

import { Aviso, Boton, Campo, Marca } from '@/components/ui';
import { useSesion } from '@/app/sesion';

export function PaginaLogin() {
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
    <main
      style={{
        minHeight: '100dvh',
        display: 'grid',
        placeItems: 'center',
        padding: 'var(--mch-esp-4)',
      }}
    >
      <div style={{ width: 'min(400px, 100%)' }}>
        <div style={{ marginBottom: 'var(--mch-esp-6)' }}>
          <Marca />
          <p
            style={{
              margin: 'var(--mch-esp-3) 0 0',
              color: 'var(--mch-texto-secundario)',
              fontSize: 'var(--mch-txt-sm)',
            }}
          >
            Gestión de taller. Entra con la cuenta que te dio tu administrador.
          </p>
        </div>

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
        </form>

        <p
          style={{
            marginTop: 'var(--mch-esp-4)',
            fontSize: 'var(--mch-txt-xs)',
            color: 'var(--mch-texto-secundario)',
            textAlign: 'center',
          }}
        >
          No hay registro público: las cuentas las crea el administrador del taller.
        </p>
      </div>
    </main>
  );
}
