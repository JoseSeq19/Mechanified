import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  Aviso,
  Boton,
  Campo,
  Cargando,
  Dialogo,
  Distintivo,
  Seccion,
  Selector,
  Vacio,
} from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { formatearFecha } from '@/lib/formato';
import { useSesion } from '@/app/sesion';
import type { EstadoOrden } from '@/features/ordenes/api';
import {
  cerrarControl,
  iniciarControl,
  listarControles,
  listarPlantillas,
  marcarPunto,
  type Control,
  type ResultadoCheck,
} from './api';

const OPCIONES: { valor: ResultadoCheck; texto: string }[] = [
  { valor: 'ok', texto: 'Conforme' },
  { valor: 'no_ok', texto: 'No conforme' },
  { valor: 'no_aplica', texto: 'No aplica' },
];

export function PanelCalidad({
  ordenId,
  estado,
  cerrada,
  onCambio,
}: {
  ordenId: string;
  estado: EstadoOrden;
  cerrada: boolean;
  onCambio: () => void;
}) {
  const { claims } = useSesion();
  const clienteQuery = useQueryClient();
  const [iniciando, setIniciando] = useState(false);
  const [rechazando, setRechazando] = useState<Control | null>(null);
  const [error, setError] = useState<string | null>(null);

  const consulta = useQuery({
    queryKey: ['orden', ordenId, 'controles'],
    queryFn: () => listarControles(ordenId),
  });

  // Cerrar un control mueve la orden, así que la ficha entera se refresca.
  const refrescar = async () => {
    await clienteQuery.invalidateQueries({ queryKey: ['orden', ordenId, 'controles'] });
    onCambio();
  };

  const fallo = (e: unknown, respaldo: string) =>
    setError(e instanceof ErrorApi ? e.message : respaldo);

  const mutMarcar = useMutation({
    mutationFn: (v: { id: string; resultado: ResultadoCheck }) =>
      marcarPunto(v.id, { resultado: v.resultado }),
    // Se escribe la respuesta directamente en caché: marcar punto por punto con
    // una recarga completa cada vez haría parpadear la lista entera.
    onSuccess: (control) => {
      setError(null);
      clienteQuery.setQueryData<Control[]>(['orden', ordenId, 'controles'], (prev) =>
        prev?.map((c) => (c.id === control.id ? control : c)),
      );
    },
    onError: (e) => fallo(e, 'No se pudo marcar el punto.'),
  });

  const mutAprobar = useMutation({
    mutationFn: (controlId: string) => cerrarControl(controlId, true),
    onSuccess: async () => {
      setError(null);
      await refrescar();
    },
    onError: (e) => fallo(e, 'No se pudo aprobar el control.'),
  });

  // Mismos roles que las políticas RLS de `controles_calidad`.
  const puedeInspeccionar =
    !cerrada &&
    (claims?.rol === 'tecnico' ||
      claims?.rol === 'asesor_servicio' ||
      claims?.rol === 'admin_taller');

  const controles = consulta.data ?? [];
  const enCurso = controles.find((c) => c.resultado === 'pendiente');
  const cerrados = controles.filter((c) => c.resultado !== 'pendiente');

  return (
    <>
      <Seccion
        titulo="Control de calidad"
        resumen={
          enCurso
            ? enCurso.pendientes > 0
              ? `${enCurso.pendientes} ${enCurso.pendientes === 1 ? 'punto obligatorio pendiente' : 'puntos obligatorios pendientes'}`
              : 'Todos los obligatorios conformes'
            : undefined
        }
        accion={
          puedeInspeccionar &&
          !enCurso && <Boton onClick={() => setIniciando(true)}>Iniciar control</Boton>
        }
      >
        {error && (
          <div style={{ padding: 'var(--mch-esp-4) var(--mch-esp-5) 0' }}>
            <Aviso tono="alerta">{error}</Aviso>
          </div>
        )}

        {consulta.isLoading ? (
          <Cargando texto="" />
        ) : controles.length === 0 ? (
          <Vacio
            titulo="Sin inspeccionar"
            detalle={
              cerrada ? undefined : 'Antes de entregar se revisa el vehículo contra el checklist del taller.'
            }
          />
        ) : (
          <>
            {enCurso && (
              <div>
                {estado !== 'control_calidad' && (
                  <div style={{ padding: 'var(--mch-esp-4) var(--mch-esp-5) 0' }}>
                    <Aviso tono="info">
                      La orden no está en control de calidad: cerrar la inspección no la moverá de
                      estado.
                    </Aviso>
                  </div>
                )}

                {enCurso.respuestas.map((r) => (
                  <div key={r.id} className="mch-linea" style={{ alignItems: 'center' }}>
                    <div style={{ minWidth: 0 }}>
                      <div>
                        {r.descripcion}
                        {r.obligatorio && (
                          <span
                            title="Obligatorio"
                            style={{ color: 'var(--mch-alerta)', marginLeft: 'var(--mch-esp-1)' }}
                          >
                            *
                          </span>
                        )}
                      </div>
                      {r.comentario && <div className="mch-linea__detalle">{r.comentario}</div>}
                    </div>
                    <div style={{ display: 'flex', gap: 'var(--mch-esp-1)', flex: 'none' }}>
                      {OPCIONES.map((o) => {
                        const activo = r.resultado === o.valor;
                        return (
                          <Boton
                            key={o.valor}
                            variante={
                              activo ? (o.valor === 'no_ok' ? 'peligro' : 'primario') : 'secundario'
                            }
                            disabled={!puedeInspeccionar || mutMarcar.isPending}
                            aria-pressed={activo}
                            style={{ padding: '0.25rem 0.55rem', fontSize: 'var(--mch-txt-xs)' }}
                            onClick={() =>
                              !activo && mutMarcar.mutate({ id: r.id, resultado: o.valor })
                            }
                          >
                            {o.texto}
                          </Boton>
                        );
                      })}
                    </div>
                  </div>
                ))}

                {puedeInspeccionar && (
                  <div className="mch-total" style={{ alignItems: 'center' }}>
                    <span className="mch-linea__detalle">
                      Inspector: {enCurso.inspector_nombre ?? 'sin asignar'} · los puntos con * son
                      obligatorios
                    </span>
                    <span style={{ display: 'flex', gap: 'var(--mch-esp-2)' }}>
                      <Boton variante="peligro" onClick={() => setRechazando(enCurso)}>
                        Rechazar
                      </Boton>
                      <Boton
                        disabled={enCurso.pendientes > 0}
                        cargando={mutAprobar.isPending}
                        title={
                          enCurso.pendientes > 0
                            ? 'Faltan puntos obligatorios por marcar como conformes'
                            : undefined
                        }
                        onClick={() => mutAprobar.mutate(enCurso.id)}
                      >
                        Aprobar
                      </Boton>
                    </span>
                  </div>
                )}
              </div>
            )}

            {cerrados.map((c) => (
              <div key={c.id} className="mch-linea">
                <div>
                  <Distintivo tono={c.resultado === 'aprobado' ? 'activo' : 'inactivo'}>
                    {c.resultado_etiqueta}
                  </Distintivo>
                  <span className="mch-linea__detalle" style={{ marginLeft: 'var(--mch-esp-2)' }}>
                    {formatearFecha(c.cerrado_en, true)}
                    {c.inspector_nombre && ` · ${c.inspector_nombre}`}
                  </span>
                  {c.observaciones && (
                    <div className="mch-linea__detalle" style={{ marginTop: 2 }}>
                      {c.observaciones}
                    </div>
                  )}
                </div>
                <span className="mch-linea__detalle">
                  {c.respuestas.filter((r) => r.resultado === 'ok').length}/{c.respuestas.length}{' '}
                  conformes
                </span>
              </div>
            ))}
          </>
        )}
      </Seccion>

      {iniciando && (
        <DialogoIniciar
          onCerrar={() => setIniciando(false)}
          onIniciar={async (plantillaId) => {
            await iniciarControl(ordenId, plantillaId);
            await refrescar();
          }}
        />
      )}

      {rechazando && (
        <DialogoRechazar
          onCerrar={() => setRechazando(null)}
          onRechazar={async (obs) => {
            await cerrarControl(rechazando.id, false, obs);
            await refrescar();
          }}
        />
      )}
    </>
  );
}

/* -------------------------------------------------------------------------- */

function DialogoIniciar({
  onCerrar,
  onIniciar,
}: {
  onCerrar: () => void;
  onIniciar: (plantillaId: string) => Promise<void>;
}) {
  const [plantillaId, setPlantillaId] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  const plantillas = useQuery({
    queryKey: ['calidad', 'plantillas'],
    queryFn: () => listarPlantillas(),
  });
  const lista = plantillas.data ?? [];
  const elegida = lista.find((p) => p.id === plantillaId);

  return (
    <Dialogo
      titulo="Iniciar control de calidad"
      onCerrar={onCerrar}
      pie={
        <>
          <Boton variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
          <Boton
            disabled={!plantillaId}
            cargando={guardando}
            onClick={async () => {
              setError(null);
              setGuardando(true);
              try {
                await onIniciar(plantillaId);
                onCerrar();
              } catch (e) {
                setError(e instanceof ErrorApi ? e.message : 'No se pudo iniciar el control.');
              } finally {
                setGuardando(false);
              }
            }}
          >
            Iniciar
          </Boton>
        </>
      }
    >
      {error && <Aviso tono="error">{error}</Aviso>}

      {!plantillas.isLoading && lista.length === 0 ? (
        <Aviso tono="alerta">
          El taller todavía no tiene plantillas de checklist. Administración las define en la
          sección Control de calidad.
        </Aviso>
      ) : (
        <Selector
          etiqueta="Checklist"
          value={plantillaId}
          onChange={(e) => setPlantillaId(e.target.value)}
          opciones={[
            { valor: '', texto: plantillas.isLoading ? 'Cargando…' : 'Selecciona una plantilla' },
            ...lista.map((p) => ({
              valor: p.id,
              texto: `${p.nombre} (${p.puntos.length} puntos)`,
            })),
          ]}
        />
      )}

      {elegida && (
        <div className="mch-panel" style={{ overflow: 'hidden' }}>
          {elegida.puntos.map((p) => (
            <div key={p.id} className="mch-linea">
              <span>{p.descripcion}</span>
              {p.obligatorio && <span className="mch-linea__detalle">obligatorio</span>}
            </div>
          ))}
        </div>
      )}
    </Dialogo>
  );
}

function DialogoRechazar({
  onCerrar,
  onRechazar,
}: {
  onCerrar: () => void;
  onRechazar: (observaciones: string) => Promise<void>;
}) {
  const [observaciones, setObservaciones] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  return (
    <Dialogo
      titulo="Rechazar el control"
      onCerrar={onCerrar}
      pie={
        <>
          <Boton variante="secundario" onClick={onCerrar}>
            Volver
          </Boton>
          <Boton
            variante="peligro"
            disabled={!observaciones.trim()}
            cargando={guardando}
            onClick={async () => {
              setError(null);
              setGuardando(true);
              try {
                await onRechazar(observaciones.trim());
                onCerrar();
              } catch (e) {
                setError(e instanceof ErrorApi ? e.message : 'No se pudo rechazar el control.');
              } finally {
                setGuardando(false);
              }
            }}
          >
            Rechazar y devolver a reparación
          </Boton>
        </>
      }
    >
      {error && <Aviso tono="error">{error}</Aviso>}
      <Aviso tono="alerta">
        Si la orden está en control de calidad, vuelve a reparación con este motivo en su historial.
      </Aviso>
      <Campo
        etiqueta="Qué hay que corregir"
        autoFocus
        required
        value={observaciones}
        onChange={(e) => setObservaciones(e.target.value)}
      />
    </Dialogo>
  );
}
