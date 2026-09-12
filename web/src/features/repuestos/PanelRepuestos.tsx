import { useEffect, useState, type FormEvent } from 'react';
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
import { formatearMoneda, formatearNumero } from '@/lib/formato';
import { useSesion } from '@/app/sesion';
import {
  ESTADOS_ITEM,
  PENDIENTES,
  agregarItem,
  borrarItem,
  editarItem,
  listarCatalogo,
  listarItems,
  type EstadoItem,
  type ItemNuevo,
} from './api';

export function PanelRepuestos({
  ordenId,
  cerrada,
  onCambio,
}: {
  ordenId: string;
  cerrada: boolean;
  onCambio: () => void;
}) {
  const { claims } = useSesion();
  const clienteQuery = useQueryClient();
  const [abriendo, setAbriendo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const consulta = useQuery({
    queryKey: ['orden', ordenId, 'repuestos'],
    queryFn: () => listarItems(ordenId),
  });

  const refrescar = async () => {
    await clienteQuery.invalidateQueries({ queryKey: ['orden', ordenId, 'repuestos'] });
    onCambio();
  };

  const fallo = (e: unknown, respaldo: string) =>
    setError(e instanceof ErrorApi ? e.message : respaldo);

  const mutEstado = useMutation({
    mutationFn: ({ id, estado }: { id: string; estado: EstadoItem }) => editarItem(id, { estado }),
    onSuccess: () => {
      setError(null);
      refrescar();
    },
    onError: (e) => fallo(e, 'No se pudo cambiar el estado de la pieza.'),
  });

  const mutBorrar = useMutation({
    mutationFn: borrarItem,
    onSuccess: () => {
      setError(null);
      refrescar();
    },
    onError: (e) => fallo(e, 'No se pudo quitar la pieza.'),
  });

  // El técnico puede pedir piezas —es quien descubre que hacen falta— pero no
  // cambiarles el estado ni el precio. Mismos roles que las políticas RLS.
  const puedePedir = !cerrada && claims?.rol !== undefined;
  const puedeGestionar =
    !cerrada &&
    (claims?.rol === 'encargado_repuestos' ||
      claims?.rol === 'admin_taller' ||
      claims?.rol === 'asesor_servicio');

  const datos = consulta.data;
  const lineas = datos?.lineas ?? [];

  return (
    <>
      <Seccion
        titulo="Repuestos"
        resumen={
          datos && datos.pendientes > 0
            ? `${datos.pendientes} ${datos.pendientes === 1 ? 'pieza' : 'piezas'} sin llegar`
            : lineas.length > 0
              ? 'Todas las piezas están en el taller'
              : undefined
        }
        accion={puedePedir && <Boton onClick={() => setAbriendo(true)}>Pedir pieza</Boton>}
      >
        {error && (
          <div style={{ padding: 'var(--mch-esp-4) var(--mch-esp-5) 0' }}>
            <Aviso tono="alerta">{error}</Aviso>
          </div>
        )}

        {consulta.isLoading ? (
          <Cargando texto="" />
        ) : lineas.length === 0 ? (
          <Vacio
            titulo="Sin piezas"
            detalle={cerrada ? undefined : 'Del catálogo del taller o compradas para este trabajo.'}
          />
        ) : (
          <>
            {lineas.map((l) => (
              <div key={l.id} className="mch-linea">
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 560 }}>{l.descripcion}</div>
                  <div className="mch-linea__detalle">
                    {l.sku ? `${l.sku} · ` : 'Fuera de catálogo · '}
                    {formatearNumero(l.cantidad)} × {formatearMoneda(l.precio_unitario)}
                    {l.solicitante_nombre && ` · pidió ${l.solicitante_nombre}`}
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--mch-esp-2)' }}>
                  {puedeGestionar ? (
                    // Cambiar el estado de una pieza es la acción más repetida
                    // del encargado, así que va en línea y no tras un diálogo.
                    <select
                      className="mch-campo__control"
                      style={{ width: 'auto', padding: '0.2rem 0.4rem', fontSize: 'var(--mch-txt-xs)' }}
                      value={l.estado}
                      aria-label={`Estado de ${l.descripcion}`}
                      onChange={(e) =>
                        mutEstado.mutate({ id: l.id, estado: e.target.value as EstadoItem })
                      }
                    >
                      {ESTADOS_ITEM.map((o) => (
                        <option key={o.valor} value={o.valor}>
                          {o.texto}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <Distintivo tono={PENDIENTES.has(l.estado) ? 'neutro' : 'activo'}>
                      {l.estado_etiqueta}
                    </Distintivo>
                  )}
                  <span className="mch-linea__importe">{formatearMoneda(l.subtotal)}</span>
                  {puedeGestionar && (
                    <Boton
                      variante="fantasma"
                      aria-label="Quitar pieza"
                      onClick={() => mutBorrar.mutate(l.id)}
                    >
                      ✕
                    </Boton>
                  )}
                </div>
              </div>
            ))}
            <div className="mch-total">
              <span>Total repuestos</span>
              <span>{formatearMoneda(datos?.total ?? 0)}</span>
            </div>
          </>
        )}
      </Seccion>

      {abriendo && (
        <DialogoPieza
          onCerrar={() => setAbriendo(false)}
          onGuardar={async (d) => {
            await agregarItem(ordenId, d);
            await refrescar();
          }}
        />
      )}
    </>
  );
}

/* -------------------------------------------------------------------------- */

function DialogoPieza({
  onCerrar,
  onGuardar,
}: {
  onCerrar: () => void;
  onGuardar: (d: ItemNuevo) => Promise<void>;
}) {
  const [delCatalogo, setDelCatalogo] = useState(true);
  const [repuestoId, setRepuestoId] = useState('');
  const [descripcion, setDescripcion] = useState('');
  const [cantidad, setCantidad] = useState('1');
  const [precio, setPrecio] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  const catalogo = useQuery({
    queryKey: ['repuestos', 'selector'],
    queryFn: () => listarCatalogo({ limite: 200, desplazamiento: 0 }),
  });

  const piezas = catalogo.data?.items ?? [];
  const elegida = piezas.find((p) => p.id === repuestoId);

  // Al elegir del catálogo se muestra su precio, pero editable: a veces se
  // ajusta el de una pieza concreta al cotizar.
  useEffect(() => {
    if (elegida) setPrecio(elegida.precio_venta);
  }, [elegida]);

  async function alEnviar(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setGuardando(true);
    try {
      await onGuardar(
        delCatalogo
          ? {
              repuesto_id: repuestoId,
              cantidad: Number(cantidad),
              precio_unitario: precio === '' ? null : Number(precio),
            }
          : {
              descripcion,
              cantidad: Number(cantidad),
              precio_unitario: Number(precio),
            },
      );
      onCerrar();
    } catch (err) {
      setError(
        err instanceof ErrorApi && err.esDeUsuario ? err.message : 'No se pudo añadir la pieza.',
      );
    } finally {
      setGuardando(false);
    }
  }

  const subtotal = Number(cantidad) * Number(precio || 0);
  const listo = delCatalogo ? Boolean(repuestoId) : Boolean(descripcion.trim() && precio);

  return (
    <Dialogo
      titulo="Pedir una pieza"
      onCerrar={onCerrar}
      pie={
        <>
          <Boton variante="secundario" type="button" onClick={onCerrar}>
            Cancelar
          </Boton>
          <Boton type="submit" form="formulario-pieza" cargando={guardando} disabled={!listo}>
            Añadir
          </Boton>
        </>
      }
    >
      <form
        id="formulario-pieza"
        onSubmit={alEnviar}
        style={{ display: 'grid', gap: 'var(--mch-esp-4)' }}
      >
        {error && <Aviso tono="error">{error}</Aviso>}

        <div style={{ display: 'flex', gap: 'var(--mch-esp-2)' }}>
          <Boton
            type="button"
            variante={delCatalogo ? 'primario' : 'secundario'}
            onClick={() => setDelCatalogo(true)}
          >
            Del catálogo
          </Boton>
          <Boton
            type="button"
            variante={delCatalogo ? 'secundario' : 'primario'}
            onClick={() => setDelCatalogo(false)}
          >
            Compra suelta
          </Boton>
        </div>

        {delCatalogo ? (
          <Selector
            etiqueta="Pieza"
            value={repuestoId}
            onChange={(e) => setRepuestoId(e.target.value)}
            opciones={[
              {
                valor: '',
                texto: catalogo.isLoading
                  ? 'Cargando catálogo…'
                  : piezas.length === 0
                    ? 'El catálogo está vacío'
                    : 'Selecciona una pieza',
              },
              ...piezas.map((p) => ({ valor: p.id, texto: `${p.sku} — ${p.nombre}` })),
            ]}
          />
        ) : (
          <Campo
            etiqueta="Qué pieza es"
            required
            autoFocus
            ayuda="La que se compra para este trabajo y no está en el catálogo"
            value={descripcion}
            onChange={(e) => setDescripcion(e.target.value)}
          />
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--mch-esp-4)' }}>
          <Campo
            etiqueta="Cantidad"
            type="number"
            min={0.01}
            step={1}
            required
            value={cantidad}
            onChange={(e) => setCantidad(e.target.value)}
          />
          <Campo
            etiqueta="Precio unitario"
            type="number"
            min={0}
            step={0.5}
            required={!delCatalogo}
            ayuda={delCatalogo && elegida ? 'Precio del catálogo, editable' : undefined}
            value={precio}
            onChange={(e) => setPrecio(e.target.value)}
          />
        </div>

        {Number.isFinite(subtotal) && subtotal > 0 && (
          <Aviso tono="info">Subtotal: {formatearMoneda(subtotal)}</Aviso>
        )}
      </form>
    </Dialogo>
  );
}
