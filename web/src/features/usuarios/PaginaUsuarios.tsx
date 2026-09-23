import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Aviso, Boton, Campo, Cargando, Dialogo, Distintivo, Selector, Vacio } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { formatearFecha } from '@/lib/formato';
import { ETIQUETA_ROL, useSesion, type Rol } from '@/app/sesion';
import {
  cambiarCorreo,
  crearUsuario,
  editarUsuario,
  listarUsuarios,
  restablecerClave,
  type DatosAlta,
  type Usuario,
} from './api';

const ROLES: Rol[] = ['admin_taller', 'asesor_servicio', 'tecnico', 'encargado_repuestos'];

const QUE_HACE: Record<Rol, string> = {
  admin_taller: 'Todo, incluido dar de alta gente y ver el panel.',
  asesor_servicio: 'Recibe vehículos, cotiza, cobra y entrega.',
  tecnico: 'Diagnostica, repara y hace el control de calidad.',
  encargado_repuestos: 'Lleva el catálogo y el stock de piezas.',
};

export function PaginaUsuarios() {
  const { claims } = useSesion();
  const clienteQuery = useQueryClient();

  const [incluirInactivos, setIncluirInactivos] = useState(false);
  const [dandoAlta, setDandoAlta] = useState(false);
  const [editando, setEditando] = useState<Usuario | null>(null);
  const [error, setError] = useState<string | null>(null);

  const consulta = useQuery({
    queryKey: ['usuarios', 'personal', incluirInactivos],
    queryFn: () => listarUsuarios(undefined, incluirInactivos),
  });

  const refrescar = () => clienteQuery.invalidateQueries({ queryKey: ['usuarios'] });

  const mutEstado = useMutation({
    mutationFn: ({ id, activo }: { id: string; activo: boolean }) => editarUsuario(id, { activo }),
    onSuccess: () => {
      setError(null);
      refrescar();
    },
    onError: (e) => setError(e instanceof ErrorApi ? e.message : 'No se pudo cambiar el estado.'),
  });

  if (claims?.rol !== 'admin_taller') {
    return (
      <Aviso tono="alerta">
        Esta pantalla es de administración: desde aquí se da de alta a la gente del taller y se
        decide qué puede hacer cada quien.
      </Aviso>
    );
  }

  const gente = consulta.data ?? [];

  return (
    <>
      <header
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          justifyContent: 'space-between',
          gap: 'var(--mch-esp-4)',
          flexWrap: 'wrap',
          marginBottom: 'var(--mch-esp-6)',
        }}
      >
        <div>
          <h1 style={{ fontSize: 'var(--mch-txt-xl)' }}>Personal</h1>
          <p
            style={{
              margin: 'var(--mch-esp-1) 0 0',
              color: 'var(--mch-texto-secundario)',
              fontSize: 'var(--mch-txt-sm)',
            }}
          >
            Quién entra al sistema y qué puede hacer.
          </p>
        </div>
        <Boton onClick={() => setDandoAlta(true)}>Dar de alta</Boton>
      </header>

      {error && (
        <div style={{ marginBottom: 'var(--mch-esp-4)' }}>
          <Aviso tono="error">{error}</Aviso>
        </div>
      )}

      <label
        style={{
          display: 'flex',
          gap: 'var(--mch-esp-2)',
          alignItems: 'center',
          fontSize: 'var(--mch-txt-sm)',
          color: 'var(--mch-texto-secundario)',
          marginBottom: 'var(--mch-esp-4)',
        }}
      >
        <input
          type="checkbox"
          checked={incluirInactivos}
          onChange={(e) => setIncluirInactivos(e.target.checked)}
        />
        Ver también a quien está de baja
      </label>

      <div className="mch-panel">
        {consulta.isLoading ? (
          <Cargando texto="" />
        ) : gente.length === 0 ? (
          <Vacio titulo="No hay nadie todavía" detalle="Da de alta a la primera persona." />
        ) : (
          gente.map((u) => (
            <div key={u.id} className="mch-linea">
              <div style={{ minWidth: 0 }}>
                <div>
                  {u.nombre_completo}{' '}
                  <Distintivo tono={u.activo ? 'activo' : 'inactivo'}>
                    {u.activo ? u.rol_etiqueta : 'De baja'}
                  </Distintivo>
                  {u.id === claims?.sub && <span className="mch-linea__detalle"> · tú</span>}
                </div>
                <div className="mch-linea__detalle">
                  {u.email ?? 'sin correo'}
                  {u.telefono && ` · ${u.telefono}`}
                  {u.creado_en && ` · desde ${formatearFecha(u.creado_en)}`}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 'var(--mch-esp-2)', flex: 'none' }}>
                {u.activo ? (
                  <Boton
                    variante="secundario"
                    disabled={u.id === claims?.sub || mutEstado.isPending}
                    title={u.id === claims?.sub ? 'No puedes darte de baja a ti mismo' : undefined}
                    onClick={() => mutEstado.mutate({ id: u.id, activo: false })}
                  >
                    Dar de baja
                  </Boton>
                ) : (
                  <Boton
                    variante="secundario"
                    disabled={mutEstado.isPending}
                    onClick={() => mutEstado.mutate({ id: u.id, activo: true })}
                  >
                    Reactivar
                  </Boton>
                )}
                <Boton variante="fantasma" onClick={() => setEditando(u)}>
                  Abrir
                </Boton>
              </div>
            </div>
          ))
        )}
      </div>

      {dandoAlta && (
        <DialogoAlta
          onCerrar={() => {
            setDandoAlta(false);
            refrescar();
          }}
        />
      )}

      {editando && (
        <DialogoPersona
          usuario={editando}
          esYo={editando.id === claims?.sub}
          onCerrar={() => setEditando(null)}
          onCambio={refrescar}
        />
      )}
    </>
  );
}

/* -------------------------------------------------------------------------- */

function Credenciales({ email, clave }: { email: string; clave: string }) {
  const [copiado, setCopiado] = useState(false);

  return (
    <div style={{ display: 'grid', gap: 'var(--mch-esp-2)' }}>
      <Aviso tono="alerta">
        Apunta esta contraseña ahora: no se vuelve a mostrar. Entrégasela a la persona para que
        entre y la cambie desde su sesión.
      </Aviso>
      <div className="mch-panel" style={{ padding: 'var(--mch-esp-4)', display: 'grid', gap: 4 }}>
        <span className="mch-dato__etiqueta">Entra con</span>
        <code style={{ fontSize: 'var(--mch-txt-md)' }}>{email}</code>
        <span className="mch-dato__etiqueta" style={{ marginTop: 'var(--mch-esp-2)' }}>
          Contraseña temporal
        </span>
        <code style={{ fontSize: 'var(--mch-txt-lg)', letterSpacing: '0.04em' }}>{clave}</code>
      </div>
      <Boton
        variante="secundario"
        onClick={async () => {
          await navigator.clipboard.writeText(`${email}\n${clave}`);
          setCopiado(true);
          setTimeout(() => setCopiado(false), 2000);
        }}
      >
        {copiado ? 'Copiado' : 'Copiar correo y contraseña'}
      </Boton>
    </div>
  );
}

function DialogoAlta({ onCerrar }: { onCerrar: () => void }) {
  const [rol, setRol] = useState<Rol>('tecnico');
  const [creado, setCreado] = useState<{ email: string; clave: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  async function alEnviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const datos: DatosAlta = {
      nombre_completo: String(f.get('nombre_completo') ?? '').trim(),
      email: String(f.get('email') ?? '').trim(),
      rol,
      telefono: String(f.get('telefono') ?? '').trim() || null,
    };

    setError(null);
    setGuardando(true);
    try {
      const usuario = await crearUsuario(datos);
      setCreado({ email: usuario.email ?? datos.email, clave: usuario.clave_temporal });
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : 'No se pudo dar de alta a esta persona.');
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Dialogo
      titulo={creado ? 'Listo, ya puede entrar' : 'Dar de alta'}
      onCerrar={onCerrar}
      pie={
        creado ? (
          <Boton onClick={onCerrar}>Hecho</Boton>
        ) : (
          <>
            <Boton variante="secundario" type="button" onClick={onCerrar}>
              Cancelar
            </Boton>
            <Boton type="submit" form="formulario-alta" cargando={guardando}>
              Crear cuenta
            </Boton>
          </>
        )
      }
    >
      {creado ? (
        <Credenciales email={creado.email} clave={creado.clave} />
      ) : (
        <form id="formulario-alta" onSubmit={alEnviar} style={{ display: 'grid', gap: 'var(--mch-esp-4)' }}>
          {error && <Aviso tono="error">{error}</Aviso>}

          <Campo etiqueta="Nombre y apellido" name="nombre_completo" required autoFocus />
          <Campo
            etiqueta="Correo"
            name="email"
            type="email"
            required
            ayuda="Con este correo entrará al sistema"
          />
          <Campo etiqueta="Teléfono" name="telefono" />
          <Selector
            etiqueta="Rol"
            value={rol}
            onChange={(e) => setRol(e.target.value as Rol)}
            opciones={ROLES.map((r) => ({ valor: r, texto: ETIQUETA_ROL[r] }))}
          />
          <Aviso tono="info">{QUE_HACE[rol]}</Aviso>
        </form>
      )}
    </Dialogo>
  );
}

function DialogoPersona({
  usuario,
  esYo,
  onCerrar,
  onCambio,
}: {
  usuario: Usuario;
  esYo: boolean;
  onCerrar: () => void;
  onCambio: () => void;
}) {
  const [rol, setRol] = useState<Rol>(usuario.rol);
  const [clave, setClave] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  const fallo = (e: unknown, respaldo: string) =>
    setError(e instanceof ErrorApi ? e.message : respaldo);

  async function guardar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const correo = String(f.get('email') ?? '').trim();

    setError(null);
    setGuardando(true);
    try {
      await editarUsuario(usuario.id, {
        nombre_completo: String(f.get('nombre_completo') ?? '').trim(),
        telefono: String(f.get('telefono') ?? '').trim() || null,
        ...(rol !== usuario.rol ? { rol } : {}),
      });
      if (correo && correo !== usuario.email) {
        await cambiarCorreo(usuario.id, correo);
      }
      onCambio();
      onCerrar();
    } catch (err) {
      fallo(err, 'No se pudo guardar el cambio.');
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Dialogo
      titulo={usuario.nombre_completo}
      onCerrar={onCerrar}
      pie={
        <>
          <Boton variante="secundario" type="button" onClick={onCerrar}>
            Cerrar
          </Boton>
          <Boton type="submit" form="formulario-persona" cargando={guardando}>
            Guardar
          </Boton>
        </>
      }
    >
      <form id="formulario-persona" onSubmit={guardar} style={{ display: 'grid', gap: 'var(--mch-esp-4)' }}>
        {error && <Aviso tono="error">{error}</Aviso>}

        <Campo
          etiqueta="Nombre y apellido"
          name="nombre_completo"
          required
          defaultValue={usuario.nombre_completo}
        />
        <Campo
          etiqueta="Correo de acceso"
          name="email"
          type="email"
          defaultValue={usuario.email ?? ''}
          ayuda="Cambiarlo cambia también con qué correo entra"
        />
        <Campo etiqueta="Teléfono" name="telefono" defaultValue={usuario.telefono ?? ''} />
        <Selector
          etiqueta="Rol"
          value={rol}
          disabled={esYo}
          onChange={(e) => setRol(e.target.value as Rol)}
          opciones={ROLES.map((r) => ({ valor: r, texto: ETIQUETA_ROL[r] }))}
        />
        <span className="mch-campo__ayuda">
          {esYo
            ? 'No puedes cambiarte el rol a ti mismo: pídeselo a otro administrador.'
            : `${QUE_HACE[rol]} El cambio entra cuando la persona renueve su sesión, como mucho en una hora.`}
        </span>
      </form>

      <div
        style={{
          borderTop: '1px solid var(--mch-borde)',
          paddingTop: 'var(--mch-esp-4)',
          display: 'grid',
          gap: 'var(--mch-esp-3)',
        }}
      >
        {clave ? (
          <Credenciales email={usuario.email ?? ''} clave={clave} />
        ) : (
          <>
            <span className="mch-campo__ayuda">
              Si olvidó su contraseña, aquí se le genera una nueva. La anterior deja de servir en
              el momento.
            </span>
            <Boton
              variante="secundario"
              type="button"
              onClick={async () => {
                setError(null);
                try {
                  const { clave_temporal } = await restablecerClave(usuario.id);
                  setClave(clave_temporal);
                } catch (err) {
                  fallo(err, 'No se pudo restablecer la contraseña.');
                }
              }}
            >
              Restablecer contraseña
            </Boton>
          </>
        )}
      </div>
    </Dialogo>
  );
}
