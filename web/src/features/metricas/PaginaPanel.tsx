/**
 * El panel del taller.
 *
 * Sobre los gráficos: son barras horizontales y nada más. Lo que se compara
 * aquí son magnitudes entre categorías —cuántas órdenes en cada estado, cuántas
 * horas en cada etapa— y para eso la barra es la forma que menos hace pensar.
 * No hay tartas (comparar ángulos es peor que comparar longitudes) ni ejes
 * dobles (dos escalas en un gráfico se leen mal siempre).
 *
 * Cada barra lleva su número escrito al lado, así que el color nunca es el
 * único portador de información: quien no distinga el ámbar del petróleo sigue
 * leyendo el panel entero. El ámbar se reserva para lo que pide atención —la
 * etapa más lenta, los presupuestos rechazados—, nunca para "la serie 2".
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { Aviso, Cargando, Vacio } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { formatearFecha, formatearMoneda } from '@/lib/formato';
import { obtenerPanel, type EtapaTiempo, type PanelMetricas } from './api';

const PERIODOS = [
  { dias: 7, texto: '7 días' },
  { dias: 30, texto: '30 días' },
  { dias: 90, texto: '90 días' },
  { dias: 365, texto: '1 año' },
];

/** Bajo este número de transiciones, un promedio no dice nada. */
const MINIMO_FIABLE = 3;

export function PaginaPanel() {
  const [dias, setDias] = useState(30);

  const consulta = useQuery({
    queryKey: ['metricas', 'panel', dias],
    queryFn: () => obtenerPanel(dias),
  });

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
          <h1 style={{ fontSize: 'var(--mch-txt-xl)' }}>Panel</h1>
          <p
            style={{
              margin: 'var(--mch-esp-1) 0 0',
              color: 'var(--mch-texto-secundario)',
              fontSize: 'var(--mch-txt-sm)',
            }}
          >
            El trabajo vivo es de ahora mismo. El resto,{' '}
            {consulta.data ? `desde el ${formatearFecha(consulta.data.desde)}` : 'del periodo'}.
          </p>
        </div>

        <div className="mch-periodos" role="group" aria-label="Periodo">
          {PERIODOS.map((p) => (
            <button
              key={p.dias}
              type="button"
              aria-pressed={dias === p.dias}
              className={`mch-periodo${dias === p.dias ? ' mch-periodo--activo' : ''}`}
              onClick={() => setDias(p.dias)}
            >
              {p.texto}
            </button>
          ))}
        </div>
      </header>

      {consulta.isError && (
        <Aviso tono="error">
          {consulta.error instanceof ErrorApi
            ? consulta.error.message
            : 'No se pudo cargar el panel.'}
        </Aviso>
      )}

      {consulta.isLoading || !consulta.data ? (
        <Cargando texto="Calculando…" />
      ) : (
        <Contenido panel={consulta.data} />
      )}
    </>
  );
}

/* -------------------------------------------------------------------------- */

function Contenido({ panel }: { panel: PanelMetricas }) {
  const { trabajo_vivo: vivo, produccion: pro, satisfaccion: sat } = panel;

  return (
    <>
      <div className="mch-indicadores">
        <Indicador
          titulo="En el taller"
          valor={String(vivo.abiertas)}
          pie={
            vivo.atrasadas > 0
              ? `${vivo.atrasadas} ${vivo.atrasadas === 1 ? 'pasada de fecha' : 'pasadas de fecha'}`
              : 'ninguna pasada de fecha'
          }
          alerta={vivo.atrasadas > 0}
        />
        <Indicador titulo="Entregadas" valor={String(pro.entregadas)} pie={`de ${pro.recibidas} recibidas`} />
        <Indicador titulo="Facturado" valor={formatearMoneda(pro.facturado)} pie="órdenes entregadas" />
        <Indicador
          titulo="Ticket medio"
          valor={pro.ticket_promedio ? formatearMoneda(pro.ticket_promedio) : '—'}
          pie={pro.ticket_promedio ? 'por orden entregada' : 'sin entregas todavía'}
        />
        <Indicador
          titulo="Ciclo"
          valor={pro.horas_ciclo_mediana !== null ? `${_horas(pro.horas_ciclo_mediana)}` : '—'}
          pie="mediana, del ingreso a la entrega"
        />
        <Indicador
          titulo="Recomendación"
          valor={sat.nps === null ? '—' : String(sat.nps)}
          pie={sat.respondidas > 0 ? `${sat.respondidas} respuestas` : 'sin respuestas'}
          destacado
        />
      </div>

      <div className="mch-bloques">
        <Tarjeta titulo="Dónde está el trabajo" pie="Órdenes abiertas ahora mismo">
          {vivo.abiertas === 0 ? (
            <Vacio titulo="El taller está al día" detalle="No hay órdenes abiertas." />
          ) : (
            <Barras
              filas={vivo.por_estado
                .filter((e) => e.cantidad > 0)
                .map((e) => ({
                  clave: e.estado,
                  etiqueta: e.etiqueta,
                  valor: e.cantidad,
                  texto: String(e.cantidad),
                }))}
            />
          )}
        </Tarjeta>

        <Tarjeta
          titulo="Dónde se va el tiempo"
          pie="Horas de media en cada etapa, según la bitácora"
        >
          {panel.etapas.length === 0 ? (
            <Vacio
              titulo="Todavía no hay recorrido"
              detalle="Hace falta que alguna orden avance de estado para poder medir."
            />
          ) : (
            <Etapas etapas={panel.etapas} />
          )}
        </Tarjeta>

        <Tarjeta titulo="Presupuestos" pie={`${panel.presupuestos.emitidos} emitidos en el periodo`}>
          {panel.presupuestos.aprobados + panel.presupuestos.rechazados === 0 ? (
            <Vacio
              titulo="Sin respuestas"
              detalle="Ningún cliente ha aprobado ni rechazado todavía."
            />
          ) : (
            <>
              <Proporcion
                aprobados={panel.presupuestos.aprobados}
                rechazados={panel.presupuestos.rechazados}
              />
              <dl className="mch-detalle">
                <div>
                  <dt>Aprobación</dt>
                  <dd>{panel.presupuestos.tasa_aprobacion}%</dd>
                </div>
                <div>
                  <dt>El cliente tarda</dt>
                  <dd>
                    {panel.presupuestos.horas_respuesta_promedio !== null
                      ? _horas(panel.presupuestos.horas_respuesta_promedio)
                      : '—'}
                  </dd>
                </div>
              </dl>
            </>
          )}
        </Tarjeta>

        <Tarjeta titulo="Calidad y satisfacción" pie="Retrabajo y opinión del cliente">
          <dl className="mch-detalle">
            <div>
              <dt>Controles</dt>
              <dd>{panel.calidad.controles}</dd>
            </div>
            <div>
              <dt>Rechazo en calidad</dt>
              <dd className={panel.calidad.tasa_rechazo ? 'mch-detalle__alerta' : undefined}>
                {panel.calidad.tasa_rechazo !== null ? `${panel.calidad.tasa_rechazo}%` : '—'}
              </dd>
            </div>
            <div>
              <dt>Atención</dt>
              <dd>{sat.promedio_atencion !== null ? `${sat.promedio_atencion} / 5` : '—'}</dd>
            </div>
            <div>
              <dt>Tiempo</dt>
              <dd>{sat.promedio_tiempo !== null ? `${sat.promedio_tiempo} / 5` : '—'}</dd>
            </div>
            <div>
              <dt>Calidad percibida</dt>
              <dd>{sat.promedio_calidad !== null ? `${sat.promedio_calidad} / 5` : '—'}</dd>
            </div>
            <div>
              <dt>Respuesta</dt>
              <dd>{sat.tasa_respuesta}%</dd>
            </div>
          </dl>
          <p className="mch-bloque__nota">
            El detalle de cada encuesta está en <Link to="/encuestas">Satisfacción</Link>.
          </p>
        </Tarjeta>

        <Tarjeta titulo="Quién entregó" pie="Órdenes terminadas en el periodo, por técnico">
          {panel.tecnicos.length === 0 ? (
            <Vacio
              titulo="Sin técnico asignado"
              detalle="Asigna el técnico en la ficha de la orden para poder medirlo."
            />
          ) : (
            <Barras
              filas={panel.tecnicos.map((t) => ({
                clave: t.tecnico_id,
                etiqueta: t.nombre,
                valor: t.entregadas,
                texto: `${t.entregadas} · ${formatearMoneda(t.facturado)}`,
              }))}
            />
          )}
        </Tarjeta>

        <Tarjeta titulo="Inventario" pie="Piezas que conviene reponer">
          <dl className="mch-detalle">
            <div>
              <dt>Bajo mínimo</dt>
              <dd className={vivo.repuestos_bajo_minimo > 0 ? 'mch-detalle__alerta' : undefined}>
                {vivo.repuestos_bajo_minimo}
              </dd>
            </div>
            <div>
              <dt>Mano de obra</dt>
              <dd>{formatearMoneda(pro.mano_obra)}</dd>
            </div>
            <div>
              <dt>Repuestos</dt>
              <dd>{formatearMoneda(pro.repuestos)}</dd>
            </div>
            <div>
              <dt>Canceladas</dt>
              <dd>{pro.canceladas}</dd>
            </div>
          </dl>
          <p className="mch-bloque__nota">
            El catálogo completo está en <Link to="/repuestos">Repuestos</Link>.
          </p>
        </Tarjeta>
      </div>
    </>
  );
}

/* --- Piezas ---------------------------------------------------------------- */

function _horas(horas: number): string {
  if (horas < 1) return `${Math.round(horas * 60)} min`;
  if (horas < 48) return `${horas.toLocaleString('es', { maximumFractionDigits: 1 })} h`;
  return `${(horas / 24).toLocaleString('es', { maximumFractionDigits: 1 })} días`;
}

function Indicador({
  titulo,
  valor,
  pie,
  destacado = false,
  alerta = false,
}: {
  titulo: string;
  valor: string;
  pie: string;
  destacado?: boolean;
  alerta?: boolean;
}) {
  return (
    <div className={`mch-indicador${destacado ? ' mch-indicador--destacado' : ''}`}>
      <div className="mch-indicador__titulo">{titulo}</div>
      <div className="mch-indicador__valor">{valor}</div>
      <div className={`mch-indicador__pie${alerta ? ' mch-indicador__pie--alerta' : ''}`}>{pie}</div>
    </div>
  );
}

function Tarjeta({
  titulo,
  pie,
  children,
}: {
  titulo: string;
  pie: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mch-bloque">
      <header>
        <h2 className="mch-seccion__titulo">{titulo}</h2>
        <p className="mch-seccion__resumen">{pie}</p>
      </header>
      {children}
    </section>
  );
}

interface Fila {
  clave: string;
  etiqueta: string;
  valor: number;
  texto: string;
  /** Marca la fila que pide atención; se acompaña siempre de una nota escrita. */
  atencion?: boolean;
  nota?: string;
  titulo?: string;
}

/** Barras horizontales con el número al lado. La escala es el mayor de la lista. */
function Barras({ filas }: { filas: Fila[] }) {
  const tope = Math.max(...filas.map((f) => f.valor), 1);

  return (
    <div className="mch-barras">
      {filas.map((f) => (
        <div key={f.clave} className="mch-barra" title={f.titulo}>
          <span className="mch-barra__etiqueta">
            {f.etiqueta}
            {f.nota && <em className="mch-barra__nota">{f.nota}</em>}
          </span>
          <span className="mch-barra__pista">
            <span
              className={`mch-barra__relleno${f.atencion ? ' mch-barra__relleno--atencion' : ''}`}
              style={{ width: `${Math.max((f.valor / tope) * 100, 2)}%` }}
            />
          </span>
          <span className="mch-barra__valor">{f.texto}</span>
        </div>
      ))}
    </div>
  );
}

function Etapas({ etapas }: { etapas: EtapaTiempo[] }) {
  const fiables = etapas.filter((e) => e.transiciones >= MINIMO_FIABLE);
  // El cuello de botella solo se señala si el promedio se sostiene en suficientes
  // pasos: con dos órdenes, la etapa "más lenta" es casualidad.
  const lenta = fiables.reduce<EtapaTiempo | null>(
    (peor, e) => (peor === null || e.horas_promedio > peor.horas_promedio ? e : peor),
    null,
  );

  return (
    <Barras
      filas={etapas.map((e) => ({
        clave: e.estado,
        etiqueta: e.etiqueta,
        valor: e.horas_promedio,
        texto: _horas(e.horas_promedio),
        atencion: lenta?.estado === e.estado && etapas.length > 1,
        nota:
          lenta?.estado === e.estado && etapas.length > 1
            ? 'lo que más tarda'
            : e.transiciones < MINIMO_FIABLE
              ? `solo ${e.transiciones}`
              : undefined,
        titulo: `${e.transiciones} ${e.transiciones === 1 ? 'orden medida' : 'órdenes medidas'}`,
      }))}
    />
  );
}

/** Aprobados contra rechazados, con las dos cifras escritas. */
function Proporcion({ aprobados, rechazados }: { aprobados: number; rechazados: number }) {
  const total = aprobados + rechazados;

  return (
    <div className="mch-proporcion">
      <div className="mch-proporcion__pista">
        <span
          className="mch-proporcion__parte"
          style={{ width: `${(aprobados / total) * 100}%` }}
        />
        <span
          className="mch-proporcion__parte mch-proporcion__parte--atencion"
          style={{ width: `${(rechazados / total) * 100}%` }}
        />
      </div>
      <div className="mch-proporcion__leyenda">
        <span>
          <i className="mch-marca-color" /> {aprobados} aprobados
        </span>
        <span>
          <i className="mch-marca-color mch-marca-color--atencion" /> {rechazados} rechazados
        </span>
      </div>
    </div>
  );
}
