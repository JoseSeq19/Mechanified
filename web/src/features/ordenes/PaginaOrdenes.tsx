import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { Aviso, Boton, Cargando, Vacio } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { useSesion } from '@/app/sesion';
import { FormularioOrden } from './FormularioOrden';
import { formatearMoneda, haceCuanto } from '@/lib/formato';
import { ETIQUETA, TONO } from './estados';
import {
  crearOrden,
  listarOrdenes,
  obtenerTablero,
  type EstadoOrden,
  type OrdenResumen,
} from './api';

/** Columnas del tablero. Las cerradas no ocupan sitio en el trabajo del día. */
const COLUMNAS: EstadoOrden[] = [
  'recibido',
  'en_diagnostico',
  'presupuesto_pendiente',
  'aprobado',
  'en_reparacion',
  'control_calidad',
  'listo_para_entrega',
];

function Tarjeta({ orden }: { orden: OrdenResumen }) {
  const tono = TONO[orden.estado];
  return (
    <Link to={`/ordenes/${orden.id}`} className={`mch-tarjeta mch-tarjeta--${tono}`}>
      <div className="mch-tarjeta__folio">
        <span>{orden.folio}</span>
        {orden.atrasada && <span className="mch-atrasada">Atrasada</span>}
      </div>
      <div className="mch-tarjeta__placa">{orden.vehiculo_placa}</div>
      <div className="mch-tarjeta__linea">{orden.vehiculo_descripcion}</div>
      <div className="mch-tarjeta__linea">{orden.cliente_nombre}</div>
      <div className="mch-tarjeta__pie">
        <span>{orden.tecnico_nombre ?? 'Sin técnico'}</span>
        <span>{haceCuanto(orden.fecha_ingreso)}</span>
      </div>
    </Link>
  );
}

export function PaginaOrdenes() {
  const { claims } = useSesion();
  const clienteQuery = useQueryClient();
  const [params, setParams] = useSearchParams();

  const [texto, setTexto] = useState('');
  const [busqueda, setBusqueda] = useState('');
  const [abriendo, setAbriendo] = useState(false);

  const vehiculoId = params.get('vehiculo') ?? undefined;
  const buscando = busqueda.length >= 3 || Boolean(vehiculoId);

  useEffect(() => {
    const t = setTimeout(() => setBusqueda(texto.trim().length >= 3 ? texto.trim() : ''), 300);
    return () => clearTimeout(t);
  }, [texto]);

  const tablero = useQuery({ queryKey: ['ordenes', 'tablero'], queryFn: obtenerTablero });

  // Una sola consulta trae todas las órdenes abiertas y se reparten por columna
  // en el cliente. Con el volumen de un taller es más barato que nueve
  // consultas, una por estado.
  const consulta = useQuery({
    queryKey: ['ordenes', 'lista', busqueda, vehiculoId],
    queryFn: () =>
      listarOrdenes({
        busqueda: busqueda || undefined,
        vehiculoId,
        incluirCerradas: buscando,
        limite: 200,
        desplazamiento: 0,
      }),
  });

  const refrescar = () => clienteQuery.invalidateQueries({ queryKey: ['ordenes'] });
  const puedeAbrir = claims?.rol === 'admin_taller' || claims?.rol === 'asesor_servicio';
  const ordenes = consulta.data?.items ?? [];

  const conteo = (estado: EstadoOrden) =>
    tablero.data?.columnas.find((c) => c.estado === estado)?.cantidad ?? 0;

  return (
    <>
      <header
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          justifyContent: 'space-between',
          gap: 'var(--mch-esp-4)',
          flexWrap: 'wrap',
          marginBottom: 'var(--mch-esp-5)',
        }}
      >
        <div>
          <h1 style={{ fontSize: 'var(--mch-txt-xl)' }}>Órdenes de servicio</h1>
          <p
            style={{
              margin: 'var(--mch-esp-1) 0 0',
              color: 'var(--mch-texto-secundario)',
              fontSize: 'var(--mch-txt-sm)',
            }}
          >
            {tablero.data?.total_abiertas ?? 0} en el taller ahora mismo
          </p>
        </div>
        {puedeAbrir && <Boton onClick={() => setAbriendo(true)}>Recibir vehículo</Boton>}
      </header>

      <div
        style={{
          display: 'flex',
          gap: 'var(--mch-esp-3)',
          alignItems: 'center',
          flexWrap: 'wrap',
          marginBottom: 'var(--mch-esp-4)',
        }}
      >
        <input
          className="mch-campo__control"
          style={{ maxWidth: 340 }}
          type="search"
          placeholder="Buscar por folio, placa o cliente…"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          aria-label="Buscar órdenes"
        />
        {vehiculoId && (
          <Boton variante="secundario" onClick={() => setParams({})}>
            Quitar filtro de vehículo
          </Boton>
        )}
        {buscando && (
          <span style={{ fontSize: 'var(--mch-txt-xs)', color: 'var(--mch-texto-secundario)' }}>
            Mostrando también las cerradas
          </span>
        )}
      </div>

      {consulta.isError && (
        <Aviso tono="error">
          {consulta.error instanceof ErrorApi
            ? consulta.error.message
            : 'No se pudieron cargar las órdenes.'}
        </Aviso>
      )}

      {consulta.isLoading ? (
        <div className="mch-panel">
          <Cargando />
        </div>
      ) : buscando ? (
        // Buscando, el tablero estorba: lo que se quiere es una lista plana con
        // el resultado, venga del estado que venga.
        <div className="mch-panel">
          {ordenes.length === 0 ? (
            <Vacio titulo="Sin resultados" detalle="Ninguna orden coincide con la búsqueda." />
          ) : (
            <div style={{ padding: 'var(--mch-esp-4)', display: 'grid', gap: 'var(--mch-esp-3)' }}>
              {ordenes.map((o) => (
                <Link
                  key={o.id}
                  to={`/ordenes/${o.id}`}
                  className={`mch-tarjeta mch-tarjeta--${TONO[o.estado]}`}
                >
                  <div className="mch-tarjeta__folio">
                    <span>{o.folio}</span>
                    <span>{ETIQUETA[o.estado]}</span>
                  </div>
                  <div className="mch-tarjeta__placa">
                    {o.vehiculo_placa} — {o.vehiculo_descripcion}
                  </div>
                  <div className="mch-tarjeta__linea">{o.cliente_nombre}</div>
                  <div className="mch-tarjeta__pie">
                    <span>{haceCuanto(o.fecha_ingreso)}</span>
                    <span>{formatearMoneda(o.total)}</span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      ) : ordenes.length === 0 ? (
        <div className="mch-panel">
          <Vacio
            titulo="No hay órdenes abiertas"
            detalle="Cuando recibas un vehículo aparecerá aquí, en la primera columna."
          />
        </div>
      ) : (
        <div className="mch-tablero">
          {COLUMNAS.map((estado) => {
            const enColumna = ordenes.filter((o) => o.estado === estado);
            return (
              <section key={estado} className="mch-columna">
                <header className="mch-columna__cabecera">
                  <span className="mch-columna__titulo">
                    <span className={`mch-columna__pip mch-pip--${TONO[estado]}`} />
                    {ETIQUETA[estado]}
                  </span>
                  <span className="mch-columna__conteo">{conteo(estado)}</span>
                </header>
                <div className="mch-columna__cuerpo">
                  {enColumna.length === 0 ? (
                    <p
                      style={{
                        margin: 0,
                        fontSize: 'var(--mch-txt-xs)',
                        color: 'var(--mch-texto-secundario)',
                        textAlign: 'center',
                        padding: 'var(--mch-esp-4) 0',
                      }}
                    >
                      Vacío
                    </p>
                  ) : (
                    enColumna.map((o) => <Tarjeta key={o.id} orden={o} />)
                  )}
                </div>
              </section>
            );
          })}
        </div>
      )}

      {abriendo && (
        <FormularioOrden
          onCerrar={() => setAbriendo(false)}
          onGuardar={async (datos) => {
            await crearOrden(datos);
            await refrescar();
          }}
        />
      )}
    </>
  );
}
