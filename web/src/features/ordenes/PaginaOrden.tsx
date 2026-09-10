import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Aviso, Boton, Campo, Cargando, Dialogo, Distintivo, Selector } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { listarUsuarios } from '@/features/usuarios/api';
import {
  ETIQUETA,
  EXIGE_COMENTARIO,
  TONO,
  formatearFecha,
  formatearMoneda,
  haceCuanto,
} from './estados';
import {
  cambiarEstado,
  editarOrden,
  obtenerEventos,
  obtenerOrden,
  type EstadoOrden,
  type Orden,
} from './api';

function Dato({ etiqueta, children }: { etiqueta: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mch-dato__etiqueta">{etiqueta}</div>
      <div className="mch-dato__valor">{children}</div>
    </div>
  );
}

export function PaginaOrden() {
  const { ordenId = '' } = useParams();
  const clienteQuery = useQueryClient();

  const [transicion, setTransicion] = useState<EstadoOrden | null>(null);
  const [comentario, setComentario] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState(false);

  const orden = useQuery({ queryKey: ['orden', ordenId], queryFn: () => obtenerOrden(ordenId) });
  const eventos = useQuery({
    queryKey: ['orden', ordenId, 'eventos'],
    queryFn: () => obtenerEventos(ordenId),
  });
  const tecnicos = useQuery({ queryKey: ['usuarios', 'tecnico'], queryFn: () => listarUsuarios('tecnico') });

  const refrescar = async () => {
    await clienteQuery.invalidateQueries({ queryKey: ['orden', ordenId] });
    await clienteQuery.invalidateQueries({ queryKey: ['ordenes'] });
  };

  const mutEstado = useMutation({
    mutationFn: ({ estado, nota }: { estado: EstadoOrden; nota: string }) =>
      cambiarEstado(ordenId, estado, nota),
    onSuccess: async () => {
      setTransicion(null);
      setComentario('');
      setError(null);
      await refrescar();
    },
    onError: (e) =>
      setError(e instanceof ErrorApi ? e.message : 'No se pudo cambiar el estado de la orden.'),
  });

  const mutEditar = useMutation({
    mutationFn: (datos: Parameters<typeof editarOrden>[1]) => editarOrden(ordenId, datos),
    onSuccess: async () => {
      setEditando(false);
      await refrescar();
    },
    onError: (e) => setError(e instanceof ErrorApi ? e.message : 'No se pudo guardar el cambio.'),
  });

  if (orden.isLoading) return <Cargando texto="Abriendo la orden…" />;

  if (orden.isError || !orden.data) {
    return (
      <>
        <Aviso tono="error">
          {orden.error instanceof ErrorApi ? orden.error.message : 'No se encontró la orden.'}
        </Aviso>
        <p style={{ marginTop: 'var(--mch-esp-4)' }}>
          <Link to="/ordenes">← Volver al tablero</Link>
        </p>
      </>
    );
  }

  const o: Orden = orden.data;
  const exigeMotivo = transicion ? EXIGE_COMENTARIO.has(transicion) : false;

  return (
    <>
      <Link
        to="/ordenes"
        style={{
          fontSize: 'var(--mch-txt-sm)',
          color: 'var(--mch-texto-secundario)',
          textDecoration: 'none',
        }}
      >
        ← Tablero
      </Link>

      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 'var(--mch-esp-4)',
          flexWrap: 'wrap',
          margin: 'var(--mch-esp-3) 0 var(--mch-esp-6)',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--mch-esp-3)' }}>
            <h1 style={{ fontSize: 'var(--mch-txt-xl)', fontFamily: 'var(--mch-fuente-mono)' }}>
              {o.folio}
            </h1>
            <Distintivo tono={TONO[o.estado] === 'cerrado' ? 'inactivo' : 'activo'}>
              {ETIQUETA[o.estado]}
            </Distintivo>
            {o.atrasada && <span className="mch-atrasada">Atrasada</span>}
          </div>
          <p
            style={{
              margin: 'var(--mch-esp-1) 0 0',
              color: 'var(--mch-texto-secundario)',
              fontSize: 'var(--mch-txt-sm)',
            }}
          >
            {o.vehiculo_placa} · {o.vehiculo_descripcion} · {o.cliente_nombre}
          </p>
        </div>
      </header>

      {error && (
        <div style={{ marginBottom: 'var(--mch-esp-4)' }}>
          <Aviso tono="error">{error}</Aviso>
        </div>
      )}

      <div className="mch-ficha">
        <div style={{ display: 'grid', gap: 'var(--mch-esp-5)' }}>
          {/* Acciones: solo las que este usuario puede hacer ahora. La lista la
              decide el backend con la máquina de estados. */}
          <div className="mch-panel">
            <div
              style={{
                padding: 'var(--mch-esp-4) var(--mch-esp-5) 0',
                fontSize: 'var(--mch-txt-xs)',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                color: 'var(--mch-texto-secundario)',
              }}
            >
              Siguiente paso
            </div>
            <div className="mch-acciones-estado">
              {o.transiciones_posibles.length === 0 ? (
                <span style={{ color: 'var(--mch-texto-secundario)', fontSize: 'var(--mch-txt-sm)' }}>
                  {TONO[o.estado] === 'cerrado'
                    ? 'La orden está cerrada.'
                    : 'Tu rol no puede mover la orden desde este estado.'}
                </span>
              ) : (
                o.transiciones_posibles.map((estado) => (
                  <Boton
                    key={estado}
                    variante={estado === 'cancelado' ? 'peligro' : 'primario'}
                    onClick={() => {
                      setError(null);
                      setTransicion(estado);
                    }}
                  >
                    {estado === 'cancelado' ? 'Cancelar orden' : `Pasar a ${ETIQUETA[estado]}`}
                  </Boton>
                ))
              )}
            </div>
          </div>

          <div className="mch-panel">
            <div className="mch-datos">
              <Dato etiqueta="Motivo de ingreso">{o.motivo_ingreso}</Dato>
              <Dato etiqueta="Kilometraje">
                {o.kilometraje_ingreso?.toLocaleString('es') ?? '—'}
              </Dato>
              <Dato etiqueta="Combustible">
                {o.nivel_combustible !== null ? `${o.nivel_combustible}%` : '—'}
              </Dato>
              <Dato etiqueta="Ingreso">{formatearFecha(o.fecha_ingreso, true)}</Dato>
              <Dato etiqueta="Prometida">{formatearFecha(o.fecha_promesa, true)}</Dato>
              <Dato etiqueta="Entrega">{formatearFecha(o.fecha_entrega, true)}</Dato>
              <Dato etiqueta="Asesor">{o.asesor_nombre ?? 'Sin asignar'}</Dato>
              <Dato etiqueta="Técnico">{o.tecnico_nombre ?? 'Sin asignar'}</Dato>
              <Dato etiqueta="Mano de obra">{formatearMoneda(o.total_mano_obra)}</Dato>
              <Dato etiqueta="Repuestos">{formatearMoneda(o.total_repuestos)}</Dato>
              <Dato etiqueta="Total">
                <strong>{formatearMoneda(o.total)}</strong>
              </Dato>
            </div>

            {(o.notas_internas || o.motivo_cancelacion) && (
              <div
                style={{
                  borderTop: '1px solid var(--mch-borde)',
                  padding: 'var(--mch-esp-4) var(--mch-esp-5)',
                }}
              >
                {o.motivo_cancelacion && (
                  <Aviso tono="alerta">Cancelada: {o.motivo_cancelacion}</Aviso>
                )}
                {o.notas_internas && (
                  <p style={{ margin: 'var(--mch-esp-3) 0 0', fontSize: 'var(--mch-txt-sm)' }}>
                    <span className="mch-dato__etiqueta">Notas internas</span>
                    <br />
                    {o.notas_internas}
                  </p>
                )}
              </div>
            )}

            <div
              style={{
                borderTop: '1px solid var(--mch-borde)',
                padding: 'var(--mch-esp-3) var(--mch-esp-5)',
              }}
            >
              <Boton variante="fantasma" onClick={() => setEditando(true)}>
                Editar datos
              </Boton>
            </div>
          </div>
        </div>

        <div className="mch-panel">
          <div
            style={{
              padding: 'var(--mch-esp-4) var(--mch-esp-5) 0',
              fontSize: 'var(--mch-txt-xs)',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              color: 'var(--mch-texto-secundario)',
            }}
          >
            Historial
          </div>
          {eventos.isLoading ? (
            <Cargando texto="" />
          ) : (
            <ol className="mch-bitacora">
              {(eventos.data ?? []).map((e) => (
                <li key={e.id} className="mch-bitacora__item">
                  <span className="mch-bitacora__punto" />
                  <div>
                    <div className="mch-bitacora__titulo">
                      {e.estado_anterior
                        ? `${ETIQUETA[e.estado_anterior]} → ${ETIQUETA[e.estado_nuevo]}`
                        : 'Orden abierta'}
                    </div>
                    <div className="mch-bitacora__meta">
                      {e.usuario_nombre ?? 'Sistema'} · {haceCuanto(e.creado_en)}
                    </div>
                    {e.comentario && (
                      <div className="mch-bitacora__comentario">{e.comentario}</div>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>

      {transicion && (
        <Dialogo
          titulo={
            transicion === 'cancelado' ? 'Cancelar la orden' : `Pasar a ${ETIQUETA[transicion]}`
          }
          onCerrar={() => setTransicion(null)}
          pie={
            <>
              <Boton variante="secundario" onClick={() => setTransicion(null)}>
                Volver
              </Boton>
              <Boton
                variante={transicion === 'cancelado' ? 'peligro' : 'primario'}
                cargando={mutEstado.isPending}
                disabled={exigeMotivo && comentario.trim().length === 0}
                onClick={() => mutEstado.mutate({ estado: transicion, nota: comentario.trim() })}
              >
                Confirmar
              </Boton>
            </>
          }
        >
          <p style={{ margin: 0, fontSize: 'var(--mch-txt-sm)' }}>
            {o.folio} · {o.vehiculo_placa}
          </p>
          <Campo
            etiqueta={exigeMotivo ? 'Motivo (obligatorio)' : 'Comentario'}
            ayuda="Queda en el historial de la orden"
            autoFocus
            value={comentario}
            onChange={(e) => setComentario(e.target.value)}
          />
        </Dialogo>
      )}

      {editando && (
        <Dialogo
          titulo="Editar la orden"
          onCerrar={() => setEditando(false)}
          pie={
            <>
              <Boton variante="secundario" onClick={() => setEditando(false)}>
                Cancelar
              </Boton>
              <Boton form="formulario-editar-orden" type="submit" cargando={mutEditar.isPending}>
                Guardar
              </Boton>
            </>
          }
        >
          <form
            id="formulario-editar-orden"
            style={{ display: 'grid', gap: 'var(--mch-esp-4)' }}
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              const promesa = String(f.get('fecha_promesa') ?? '');
              mutEditar.mutate({
                tecnico_id: String(f.get('tecnico_id') ?? '') || null,
                fecha_promesa: promesa ? new Date(promesa).toISOString() : null,
                notas_internas: String(f.get('notas_internas') ?? '') || null,
              });
            }}
          >
            <Selector
              etiqueta="Técnico asignado"
              name="tecnico_id"
              defaultValue={
                (tecnicos.data ?? []).find((t) => t.nombre_completo === o.tecnico_nombre)?.id ?? ''
              }
              opciones={[
                { valor: '', texto: 'Sin asignar' },
                ...(tecnicos.data ?? []).map((t) => ({ valor: t.id, texto: t.nombre_completo })),
              ]}
            />
            <Campo
              etiqueta="Fecha prometida"
              name="fecha_promesa"
              type="datetime-local"
              defaultValue={o.fecha_promesa?.slice(0, 16) ?? ''}
            />
            <Campo
              etiqueta="Notas internas"
              name="notas_internas"
              defaultValue={o.notas_internas ?? ''}
            />
          </form>
        </Dialogo>
      )}
    </>
  );
}
