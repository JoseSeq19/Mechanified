import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Aviso, Boton, Campo, Cargando, Dialogo, Seccion, Selector, Vacio } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { formatearNumero, haceCuanto } from '@/lib/formato';
import { useSesion } from '@/app/sesion';
import {
  SEVERIDADES,
  agregarHallazgo,
  borrarDiagnostico,
  borrarHallazgo,
  crearDiagnostico,
  listarDiagnosticos,
  type HallazgoNuevo,
  type Severidad,
} from './api';

const HALLAZGO_VACIO: HallazgoNuevo = {
  sistema: '',
  descripcion: '',
  severidad: 'moderada',
  requiere_repuesto: false,
};

export function PanelDiagnostico({ ordenId, cerrada }: { ordenId: string; cerrada: boolean }) {
  const { claims } = useSesion();
  const clienteQuery = useQueryClient();
  const [abriendo, setAbriendo] = useState(false);
  const [agregandoA, setAgregandoA] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const consulta = useQuery({
    queryKey: ['orden', ordenId, 'diagnosticos'],
    queryFn: () => listarDiagnosticos(ordenId),
  });

  const refrescar = () =>
    clienteQuery.invalidateQueries({ queryKey: ['orden', ordenId, 'diagnosticos'] });

  const alFallar = (e: unknown, respaldo: string) =>
    setError(e instanceof ErrorApi ? e.message : respaldo);

  const mutBorrar = useMutation({
    mutationFn: borrarDiagnostico,
    onSuccess: () => {
      setError(null);
      refrescar();
    },
    onError: (e) => alFallar(e, 'No se pudo borrar el diagnóstico.'),
  });

  const mutBorrarHallazgo = useMutation({
    mutationFn: borrarHallazgo,
    onSuccess: refrescar,
    onError: (e) => alFallar(e, 'No se pudo borrar el hallazgo.'),
  });

  // El diagnóstico es del técnico; administración puede también, por si hay que
  // corregir algo. Es la misma regla que aplican las políticas RLS.
  const puedeEscribir =
    !cerrada && (claims?.rol === 'tecnico' || claims?.rol === 'admin_taller');

  const diagnosticos = consulta.data ?? [];

  return (
    <>
      <Seccion
        titulo="Diagnóstico"
        resumen={
          diagnosticos.length > 1
            ? `${diagnosticos.length} diagnósticos · el más reciente abajo`
            : undefined
        }
        accion={
          puedeEscribir && <Boton onClick={() => setAbriendo(true)}>Registrar diagnóstico</Boton>
        }
      >
        {error && (
          <div style={{ padding: 'var(--mch-esp-4) var(--mch-esp-5) 0' }}>
            <Aviso tono="alerta">{error}</Aviso>
          </div>
        )}

        {consulta.isLoading ? (
          <Cargando texto="" />
        ) : diagnosticos.length === 0 ? (
          <Vacio
            titulo="Sin diagnóstico"
            detalle={
              cerrada
                ? 'La orden se cerró sin registrar diagnóstico.'
                : 'El técnico registra aquí lo que encontró al revisar el vehículo.'
            }
          />
        ) : (
          diagnosticos.map((d) => (
            <article key={d.id} className="mch-linea" style={{ display: 'block' }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  gap: 'var(--mch-esp-4)',
                  alignItems: 'baseline',
                }}
              >
                <div>
                  <div style={{ fontWeight: 560 }}>{d.resumen}</div>
                  <div className="mch-linea__detalle">
                    {d.tecnico_nombre ?? 'Sin técnico'} · {formatearNumero(d.horas_estimadas)} h
                    estimadas · {haceCuanto(d.creado_en)}
                  </div>
                </div>
                {puedeEscribir && (
                  <div style={{ display: 'flex', gap: 'var(--mch-esp-1)', flex: 'none' }}>
                    <Boton variante="fantasma" onClick={() => setAgregandoA(d.id)}>
                      + Hallazgo
                    </Boton>
                    <Boton variante="fantasma" onClick={() => mutBorrar.mutate(d.id)}>
                      Borrar
                    </Boton>
                  </div>
                )}
              </div>

              {d.hallazgos.length > 0 && (
                <div style={{ marginTop: 'var(--mch-esp-2)' }}>
                  {d.hallazgos.map((h) => (
                    <div key={h.id} className="mch-hallazgo">
                      <span
                        className={`mch-sev mch-sev--${h.severidad}`}
                        title={h.severidad_etiqueta}
                      />
                      <span className="mch-hallazgo__sistema">{h.sistema}</span>
                      <span style={{ flex: 1, fontSize: 'var(--mch-txt-sm)' }}>
                        {h.descripcion}
                        {h.requiere_repuesto && (
                          <span className="mch-linea__detalle"> · necesita repuesto</span>
                        )}
                      </span>
                      {puedeEscribir && (
                        <Boton
                          variante="fantasma"
                          aria-label="Quitar hallazgo"
                          onClick={() => mutBorrarHallazgo.mutate(h.id)}
                        >
                          ✕
                        </Boton>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </article>
          ))
        )}
      </Seccion>

      {abriendo && (
        <DialogoDiagnostico
          onCerrar={() => setAbriendo(false)}
          onGuardar={async (datos) => {
            await crearDiagnostico(ordenId, datos);
            await refrescar();
          }}
        />
      )}

      {agregandoA && (
        <DialogoHallazgo
          onCerrar={() => setAgregandoA(null)}
          onGuardar={async (h) => {
            await agregarHallazgo(agregandoA, h);
            await refrescar();
          }}
        />
      )}
    </>
  );
}

/* -------------------------------------------------------------------------- */

function FilaHallazgo({
  valor,
  onCambiar,
  onQuitar,
}: {
  valor: HallazgoNuevo;
  onCambiar: (h: HallazgoNuevo) => void;
  onQuitar?: () => void;
}) {
  return (
    <div style={{ display: 'grid', gap: 'var(--mch-esp-3)' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--mch-esp-3)' }}>
        <Campo
          etiqueta="Sistema"
          placeholder="Frenos, suspensión…"
          value={valor.sistema}
          onChange={(e) => onCambiar({ ...valor, sistema: e.target.value })}
        />
        <Selector
          etiqueta="Severidad"
          value={valor.severidad}
          onChange={(e) => onCambiar({ ...valor, severidad: e.target.value as Severidad })}
          opciones={SEVERIDADES}
        />
      </div>
      <Campo
        etiqueta="Qué se encontró"
        value={valor.descripcion}
        onChange={(e) => onCambiar({ ...valor, descripcion: e.target.value })}
      />
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 'var(--mch-esp-3)',
        }}
      >
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
            checked={valor.requiere_repuesto}
            onChange={(e) => onCambiar({ ...valor, requiere_repuesto: e.target.checked })}
          />
          Necesita repuesto
        </label>
        {onQuitar && (
          <Boton variante="fantasma" type="button" onClick={onQuitar}>
            Quitar
          </Boton>
        )}
      </div>
    </div>
  );
}

function DialogoDiagnostico({
  onCerrar,
  onGuardar,
}: {
  onCerrar: () => void;
  onGuardar: (d: {
    resumen: string;
    horas_estimadas: number;
    hallazgos: HallazgoNuevo[];
  }) => Promise<void>;
}) {
  const [resumen, setResumen] = useState('');
  const [horas, setHoras] = useState('');
  const [hallazgos, setHallazgos] = useState<HallazgoNuevo[]>([{ ...HALLAZGO_VACIO }]);
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  async function alEnviar(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setGuardando(true);
    try {
      // Las filas que quedaron en blanco no se envían: es habitual dejar una
      // abierta "por si acaso" y no llenarla.
      const completos = hallazgos.filter((h) => h.sistema.trim() && h.descripcion.trim());
      await onGuardar({
        resumen,
        horas_estimadas: Number(horas) || 0,
        hallazgos: completos,
      });
      onCerrar();
    } catch (err) {
      setError(
        err instanceof ErrorApi && err.esDeUsuario
          ? err.message
          : 'No se pudo registrar el diagnóstico.',
      );
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Dialogo
      titulo="Registrar diagnóstico"
      onCerrar={onCerrar}
      pie={
        <>
          <Boton variante="secundario" type="button" onClick={onCerrar}>
            Cancelar
          </Boton>
          <Boton type="submit" form="formulario-diagnostico" cargando={guardando}>
            Guardar
          </Boton>
        </>
      }
    >
      <form
        id="formulario-diagnostico"
        onSubmit={alEnviar}
        style={{ display: 'grid', gap: 'var(--mch-esp-5)' }}
      >
        {error && <Aviso tono="error">{error}</Aviso>}

        <Campo
          etiqueta="Resumen"
          required
          autoFocus
          ayuda="Lo que le dirías al asesor en una frase"
          value={resumen}
          onChange={(e) => setResumen(e.target.value)}
        />
        <Campo
          etiqueta="Horas estimadas"
          type="number"
          min={0}
          step={0.5}
          value={horas}
          onChange={(e) => setHoras(e.target.value)}
        />

        <div style={{ display: 'grid', gap: 'var(--mch-esp-4)' }}>
          <span className="mch-dato__etiqueta">Hallazgos</span>
          {hallazgos.map((h, i) => (
            <div
              key={i}
              style={{
                padding: 'var(--mch-esp-4)',
                border: '1px solid var(--mch-borde)',
                borderRadius: 'var(--mch-radio)',
              }}
            >
              <FilaHallazgo
                valor={h}
                onCambiar={(nuevo) =>
                  setHallazgos((prev) => prev.map((x, j) => (j === i ? nuevo : x)))
                }
                onQuitar={
                  hallazgos.length > 1
                    ? () => setHallazgos((prev) => prev.filter((_, j) => j !== i))
                    : undefined
                }
              />
            </div>
          ))}
          <Boton
            variante="secundario"
            type="button"
            onClick={() => setHallazgos((prev) => [...prev, { ...HALLAZGO_VACIO }])}
          >
            Añadir otro hallazgo
          </Boton>
        </div>
      </form>
    </Dialogo>
  );
}

function DialogoHallazgo({
  onCerrar,
  onGuardar,
}: {
  onCerrar: () => void;
  onGuardar: (h: HallazgoNuevo) => Promise<void>;
}) {
  const [valor, setValor] = useState<HallazgoNuevo>({ ...HALLAZGO_VACIO });
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  return (
    <Dialogo
      titulo="Añadir hallazgo"
      onCerrar={onCerrar}
      pie={
        <>
          <Boton variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
          <Boton
            cargando={guardando}
            disabled={!valor.sistema.trim() || !valor.descripcion.trim()}
            onClick={async () => {
              setError(null);
              setGuardando(true);
              try {
                await onGuardar(valor);
                onCerrar();
              } catch (err) {
                setError(
                  err instanceof ErrorApi && err.esDeUsuario
                    ? err.message
                    : 'No se pudo añadir el hallazgo.',
                );
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
      <FilaHallazgo valor={valor} onCambiar={setValor} />
    </Dialogo>
  );
}
