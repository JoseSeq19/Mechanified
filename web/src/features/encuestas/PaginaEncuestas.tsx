import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { Aviso, Boton, Cargando, Distintivo, Vacio } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { formatearFecha } from '@/lib/formato';
import { listarEncuestas, resumenEncuestas, type EncuestaFila } from './api';

const POR_PAGINA = 20;

export function PaginaEncuestas() {
  const [soloRespondidas, setSoloRespondidas] = useState(false);
  const [desplazamiento, setDesplazamiento] = useState(0);

  const resumen = useQuery({ queryKey: ['encuestas', 'resumen'], queryFn: resumenEncuestas });

  const filtros = { soloRespondidas, limite: POR_PAGINA, desplazamiento };
  const consulta = useQuery({
    queryKey: ['encuestas', filtros],
    queryFn: () => listarEncuestas(filtros),
  });

  const r = resumen.data;
  const total = consulta.data?.total ?? 0;
  const items = consulta.data?.items ?? [];
  const paginas = Math.max(1, Math.ceil(total / POR_PAGINA));
  const pagina = Math.floor(desplazamiento / POR_PAGINA) + 1;

  return (
    <>
      <header style={{ marginBottom: 'var(--mch-esp-6)' }}>
        <h1 style={{ fontSize: 'var(--mch-txt-xl)' }}>Satisfacción</h1>
        <p
          style={{
            margin: 'var(--mch-esp-1) 0 0',
            color: 'var(--mch-texto-secundario)',
            fontSize: 'var(--mch-txt-sm)',
          }}
        >
          Cada vehículo entregado recibe una encuesta. Esto es lo que han contestado.
        </p>
      </header>

      {consulta.isError && (
        <div style={{ marginBottom: 'var(--mch-esp-4)' }}>
          <Aviso tono="error">
            {consulta.error instanceof ErrorApi
              ? consulta.error.message
              : 'No se pudieron cargar las encuestas.'}
          </Aviso>
        </div>
      )}

      {r && (
        <div className="mch-indicadores">
          <Indicador
            titulo="Respuestas"
            valor={r.respondidas === 0 ? '—' : `${r.respondidas} de ${r.enviadas}`}
            pie={`${r.tasa_respuesta}% de respuesta`}
          />
          <Indicador
            titulo="Recomendación"
            valor={r.nps === null ? '—' : String(r.nps)}
            pie={
              r.nps === null
                ? 'Sin respuestas todavía'
                : `${r.promotores} promotores · ${r.pasivos} pasivos · ${r.detractores} detractores`
            }
            destacado
          />
          <Indicador titulo="Atención" valor={_nota(r.promedio_atencion)} pie="sobre 5" />
          <Indicador titulo="Tiempo" valor={_nota(r.promedio_tiempo)} pie="sobre 5" />
          <Indicador titulo="Calidad" valor={_nota(r.promedio_calidad)} pie="sobre 5" />
        </div>
      )}

      <label
        style={{
          display: 'flex',
          gap: 'var(--mch-esp-2)',
          alignItems: 'center',
          fontSize: 'var(--mch-txt-sm)',
          color: 'var(--mch-texto-secundario)',
          margin: 'var(--mch-esp-6) 0 var(--mch-esp-4)',
        }}
      >
        <input
          type="checkbox"
          checked={soloRespondidas}
          onChange={(e) => {
            setSoloRespondidas(e.target.checked);
            setDesplazamiento(0);
          }}
        />
        Solo las que contestaron
      </label>

      <div className="mch-panel">
        {consulta.isLoading ? (
          <Cargando texto="" />
        ) : items.length === 0 ? (
          <Vacio
            titulo={soloRespondidas ? 'Nadie ha contestado todavía' : 'Sin encuestas'}
            detalle={
              soloRespondidas
                ? 'Quita el filtro para ver las que están esperando respuesta.'
                : 'Se crean solas al entregar un vehículo.'
            }
          />
        ) : (
          items.map((e) => <Fila key={e.id} encuesta={e} />)
        )}
      </div>

      {paginas > 1 && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--mch-esp-3)',
            marginTop: 'var(--mch-esp-4)',
          }}
        >
          <Boton
            variante="secundario"
            disabled={desplazamiento === 0}
            onClick={() => setDesplazamiento(Math.max(0, desplazamiento - POR_PAGINA))}
          >
            Anterior
          </Boton>
          <span className="mch-linea__detalle">
            Página {pagina} de {paginas}
          </span>
          <Boton
            variante="secundario"
            disabled={pagina >= paginas}
            onClick={() => setDesplazamiento(desplazamiento + POR_PAGINA)}
          >
            Siguiente
          </Boton>
        </div>
      )}
    </>
  );
}

/* -------------------------------------------------------------------------- */

function _nota(valor: number | null): string {
  return valor === null ? '—' : valor.toLocaleString('es', { minimumFractionDigits: 1 });
}

function Indicador({
  titulo,
  valor,
  pie,
  destacado = false,
}: {
  titulo: string;
  valor: string;
  pie: string;
  destacado?: boolean;
}) {
  return (
    <div className={`mch-indicador${destacado ? ' mch-indicador--destacado' : ''}`}>
      <div className="mch-indicador__titulo">{titulo}</div>
      <div className="mch-indicador__valor">{valor}</div>
      <div className="mch-indicador__pie">{pie}</div>
    </div>
  );
}

function Fila({ encuesta }: { encuesta: EncuestaFila }) {
  const recomienda = encuesta.recomendaria ?? 0;

  return (
    <div className="mch-linea">
      <div style={{ minWidth: 0 }}>
        <div>
          <Link to={`/ordenes/${encuesta.orden_id}`} style={{ fontFamily: 'var(--mch-fuente-mono)' }}>
            {encuesta.folio}
          </Link>{' '}
          <span className="mch-linea__detalle">
            {encuesta.placa} · {encuesta.vehiculo} · {encuesta.cliente_nombre}
          </span>
        </div>
        {encuesta.respondida ? (
          <div className="mch-linea__detalle">
            Atención {encuesta.puntaje_atencion}/5 · Tiempo {encuesta.puntaje_tiempo}/5 · Calidad{' '}
            {encuesta.puntaje_calidad}/5 · Recomendaría {encuesta.recomendaria}/10 ·{' '}
            {formatearFecha(encuesta.respondida_en)}
          </div>
        ) : (
          <div className="mch-linea__detalle">
            {encuesta.enviada_en
              ? `Enviada el ${formatearFecha(encuesta.enviada_en)}, sin respuesta`
              : 'Todavía sin enviar'}
          </div>
        )}
        {encuesta.comentario && (
          <div className="mch-bitacora__comentario" style={{ marginTop: 'var(--mch-esp-2)' }}>
            {encuesta.comentario}
          </div>
        )}
      </div>

      <Distintivo
        tono={
          !encuesta.respondida ? 'neutro' : recomienda >= 9 ? 'activo' : recomienda >= 7 ? 'neutro' : 'inactivo'
        }
      >
        {!encuesta.respondida
          ? 'Pendiente'
          : recomienda >= 9
            ? 'Promotor'
            : recomienda >= 7
              ? 'Pasivo'
              : 'Detractor'}
      </Distintivo>
    </div>
  );
}
