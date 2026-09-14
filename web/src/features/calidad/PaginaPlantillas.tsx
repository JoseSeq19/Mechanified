import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  Aviso,
  Boton,
  Campo,
  Cargando,
  Dialogo,
  Distintivo,
  Seccion,
  Vacio,
} from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { useSesion } from '@/app/sesion';
import {
  agregarPunto,
  borrarPlantilla,
  borrarPunto,
  crearPlantilla,
  editarPlantilla,
  editarPunto,
  listarPlantillas,
  type Plantilla,
  type PuntoNuevo,
} from './api';

const PUNTO_VACIO: PuntoNuevo = { descripcion: '', categoria: '', obligatorio: true };

/**
 * Las plantillas son el criterio de calidad del taller: qué se revisa en todo
 * vehículo antes de devolverlo. Las define administración; el resto las ve para
 * saber contra qué se va a inspeccionar su trabajo.
 */
export function PaginaPlantillas() {
  const { claims } = useSesion();
  const clienteQuery = useQueryClient();
  const [creando, setCreando] = useState(false);
  const [agregandoA, setAgregandoA] = useState<Plantilla | null>(null);
  const [error, setError] = useState<string | null>(null);

  const esAdmin = claims?.rol === 'admin_taller';

  const consulta = useQuery({
    queryKey: ['calidad', 'plantillas', 'todas'],
    queryFn: () => listarPlantillas(true),
  });

  const refrescar = () => clienteQuery.invalidateQueries({ queryKey: ['calidad', 'plantillas'] });

  const alFallar = (e: unknown, respaldo: string) =>
    setError(e instanceof ErrorApi ? e.message : respaldo);

  const mutActiva = useMutation({
    mutationFn: (p: Plantilla) => editarPlantilla(p.id, { activo: !p.activo }),
    onSuccess: () => {
      setError(null);
      refrescar();
    },
    onError: (e) => alFallar(e, 'No se pudo cambiar la plantilla.'),
  });

  const mutBorrar = useMutation({
    mutationFn: borrarPlantilla,
    onSuccess: () => {
      setError(null);
      refrescar();
    },
    onError: (e) => alFallar(e, 'No se pudo borrar la plantilla.'),
  });

  const mutObligatorio = useMutation({
    mutationFn: (v: { id: string; obligatorio: boolean }) =>
      editarPunto(v.id, { obligatorio: v.obligatorio }),
    onSuccess: refrescar,
    onError: (e) => alFallar(e, 'No se pudo cambiar el punto.'),
  });

  const mutBorrarPunto = useMutation({
    mutationFn: borrarPunto,
    onSuccess: refrescar,
    onError: (e) => alFallar(e, 'No se pudo quitar el punto.'),
  });

  const plantillas = consulta.data ?? [];

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
          <h1 style={{ fontSize: 'var(--mch-txt-xl)' }}>Control de calidad</h1>
          <p
            style={{
              margin: 'var(--mch-esp-1) 0 0',
              color: 'var(--mch-texto-secundario)',
              fontSize: 'var(--mch-txt-sm)',
            }}
          >
            Checklists que se aplican a los vehículos antes de entregarlos
          </p>
        </div>
        {esAdmin && <Boton onClick={() => setCreando(true)}>Nueva plantilla</Boton>}
      </header>

      {error && (
        <div style={{ marginBottom: 'var(--mch-esp-4)' }}>
          <Aviso tono="alerta">{error}</Aviso>
        </div>
      )}

      {!esAdmin && (
        <div style={{ marginBottom: 'var(--mch-esp-4)' }}>
          <Aviso tono="info">Solo administración puede crear o modificar plantillas.</Aviso>
        </div>
      )}

      {consulta.isLoading ? (
        <div className="mch-panel">
          <Cargando />
        </div>
      ) : plantillas.length === 0 ? (
        <div className="mch-panel">
          <Vacio
            titulo="Sin plantillas"
            detalle="Crea al menos una para poder inspeccionar vehículos antes de entregarlos."
          />
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 'var(--mch-esp-5)', maxWidth: 960 }}>
          {plantillas.map((p) => (
            <Seccion
              key={p.id}
              titulo={p.nombre}
              resumen={`${p.puntos.length} puntos · ${p.obligatorios} obligatorios${
                p.descripcion ? ` · ${p.descripcion}` : ''
              }`}
              accion={
                <span style={{ display: 'flex', gap: 'var(--mch-esp-2)', alignItems: 'center' }}>
                  {!p.activo && <Distintivo tono="inactivo">Desactivada</Distintivo>}
                  {esAdmin && (
                    <>
                      <Boton variante="fantasma" onClick={() => setAgregandoA(p)}>
                        + Punto
                      </Boton>
                      <Boton variante="fantasma" onClick={() => mutActiva.mutate(p)}>
                        {p.activo ? 'Desactivar' : 'Activar'}
                      </Boton>
                      <Boton variante="fantasma" onClick={() => mutBorrar.mutate(p.id)}>
                        Borrar
                      </Boton>
                    </>
                  )}
                </span>
              }
            >
              {p.puntos.length === 0 ? (
                <Vacio titulo="Sin puntos" detalle="Una plantilla vacía no se puede usar." />
              ) : (
                p.puntos.map((punto) => (
                  <div key={punto.id} className="mch-linea" style={{ alignItems: 'center' }}>
                    <div style={{ minWidth: 0 }}>
                      <div>{punto.descripcion}</div>
                      {punto.categoria && (
                        <div className="mch-linea__detalle">{punto.categoria}</div>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 'var(--mch-esp-2)', alignItems: 'center' }}>
                      {esAdmin ? (
                        <label
                          className="mch-linea__detalle"
                          style={{ display: 'flex', gap: 'var(--mch-esp-1)', alignItems: 'center' }}
                        >
                          <input
                            type="checkbox"
                            checked={punto.obligatorio}
                            onChange={(e) =>
                              mutObligatorio.mutate({ id: punto.id, obligatorio: e.target.checked })
                            }
                          />
                          Obligatorio
                        </label>
                      ) : (
                        punto.obligatorio && <span className="mch-linea__detalle">obligatorio</span>
                      )}
                      {esAdmin && (
                        <Boton
                          variante="fantasma"
                          aria-label="Quitar punto"
                          onClick={() => mutBorrarPunto.mutate(punto.id)}
                        >
                          ✕
                        </Boton>
                      )}
                    </div>
                  </div>
                ))
              )}
            </Seccion>
          ))}
        </div>
      )}

      {creando && (
        <DialogoPlantilla
          onCerrar={() => setCreando(false)}
          onGuardar={async (d) => {
            await crearPlantilla(d);
            await refrescar();
          }}
        />
      )}

      {agregandoA && (
        <DialogoPunto
          onCerrar={() => setAgregandoA(null)}
          onGuardar={async (punto) => {
            await agregarPunto(agregandoA.id, punto);
            await refrescar();
          }}
        />
      )}
    </>
  );
}

/* -------------------------------------------------------------------------- */

function CamposPunto({
  valor,
  onCambiar,
  onQuitar,
}: {
  valor: PuntoNuevo;
  onCambiar: (p: PuntoNuevo) => void;
  onQuitar?: () => void;
}) {
  return (
    <div style={{ display: 'grid', gap: 'var(--mch-esp-3)' }}>
      <Campo
        etiqueta="Qué se revisa"
        value={valor.descripcion}
        onChange={(e) => onCambiar({ ...valor, descripcion: e.target.value })}
      />
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr auto',
          gap: 'var(--mch-esp-3)',
          alignItems: 'end',
        }}
      >
        <Campo
          etiqueta="Categoría"
          placeholder="Seguridad, mecánica, entrega…"
          value={valor.categoria ?? ''}
          onChange={(e) => onCambiar({ ...valor, categoria: e.target.value })}
        />
        <div style={{ display: 'flex', gap: 'var(--mch-esp-3)', alignItems: 'center', paddingBottom: 6 }}>
          <label
            style={{
              display: 'flex',
              gap: 'var(--mch-esp-2)',
              alignItems: 'center',
              fontSize: 'var(--mch-txt-sm)',
              color: 'var(--mch-texto-secundario)',
            }}
          >
            <input
              type="checkbox"
              checked={valor.obligatorio}
              onChange={(e) => onCambiar({ ...valor, obligatorio: e.target.checked })}
            />
            Obligatorio
          </label>
          {onQuitar && (
            <Boton variante="fantasma" type="button" onClick={onQuitar}>
              Quitar
            </Boton>
          )}
        </div>
      </div>
    </div>
  );
}

function DialogoPlantilla({
  onCerrar,
  onGuardar,
}: {
  onCerrar: () => void;
  onGuardar: (d: { nombre: string; descripcion: string | null; puntos: PuntoNuevo[] }) => Promise<void>;
}) {
  const [nombre, setNombre] = useState('');
  const [descripcion, setDescripcion] = useState('');
  const [puntos, setPuntos] = useState<PuntoNuevo[]>([{ ...PUNTO_VACIO }]);
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  async function alEnviar(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setGuardando(true);
    try {
      await onGuardar({
        nombre,
        descripcion: descripcion || null,
        // Las filas en blanco no se envían: es normal dejar una abierta de más.
        puntos: puntos
          .filter((p) => p.descripcion.trim())
          .map((p) => ({ ...p, categoria: p.categoria || null })),
      });
      onCerrar();
    } catch (err) {
      setError(
        err instanceof ErrorApi && err.esDeUsuario ? err.message : 'No se pudo crear la plantilla.',
      );
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Dialogo
      titulo="Nueva plantilla de checklist"
      onCerrar={onCerrar}
      pie={
        <>
          <Boton variante="secundario" type="button" onClick={onCerrar}>
            Cancelar
          </Boton>
          <Boton type="submit" form="formulario-plantilla" cargando={guardando}>
            Crear
          </Boton>
        </>
      }
    >
      <form
        id="formulario-plantilla"
        onSubmit={alEnviar}
        style={{ display: 'grid', gap: 'var(--mch-esp-5)' }}
      >
        {error && <Aviso tono="error">{error}</Aviso>}

        <Campo
          etiqueta="Nombre"
          required
          autoFocus
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
        />
        <Campo
          etiqueta="Descripción"
          value={descripcion}
          onChange={(e) => setDescripcion(e.target.value)}
        />

        <Aviso tono="info">
          Un punto obligatorio tiene que quedar <strong>conforme</strong> para aprobar el control:
          "no aplica" también lo bloquea. Si algo no aplica a todos los vehículos, no lo marques como
          obligatorio.
        </Aviso>

        <div style={{ display: 'grid', gap: 'var(--mch-esp-4)' }}>
          <span className="mch-dato__etiqueta">Puntos</span>
          {puntos.map((p, i) => (
            <div
              key={i}
              style={{
                padding: 'var(--mch-esp-4)',
                border: '1px solid var(--mch-borde)',
                borderRadius: 'var(--mch-radio)',
              }}
            >
              <CamposPunto
                valor={p}
                onCambiar={(nuevo) => setPuntos((prev) => prev.map((x, j) => (j === i ? nuevo : x)))}
                onQuitar={
                  puntos.length > 1 ? () => setPuntos((prev) => prev.filter((_, j) => j !== i)) : undefined
                }
              />
            </div>
          ))}
          <Boton
            variante="secundario"
            type="button"
            onClick={() => setPuntos((prev) => [...prev, { ...PUNTO_VACIO }])}
          >
            Añadir otro punto
          </Boton>
        </div>
      </form>
    </Dialogo>
  );
}

function DialogoPunto({
  onCerrar,
  onGuardar,
}: {
  onCerrar: () => void;
  onGuardar: (p: PuntoNuevo) => Promise<void>;
}) {
  const [valor, setValor] = useState<PuntoNuevo>({ ...PUNTO_VACIO });
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  return (
    <Dialogo
      titulo="Añadir punto"
      onCerrar={onCerrar}
      pie={
        <>
          <Boton variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
          <Boton
            disabled={!valor.descripcion.trim()}
            cargando={guardando}
            onClick={async () => {
              setError(null);
              setGuardando(true);
              try {
                await onGuardar({ ...valor, categoria: valor.categoria || null });
                onCerrar();
              } catch (e) {
                setError(e instanceof ErrorApi ? e.message : 'No se pudo añadir el punto.');
              } finally {
                setGuardando(false);
              }
            }}
          >
            Añadir
          </Boton>
        </>
      }
    >
      {error && <Aviso tono="error">{error}</Aviso>}
      <CamposPunto valor={valor} onCambiar={setValor} />
    </Dialogo>
  );
}
