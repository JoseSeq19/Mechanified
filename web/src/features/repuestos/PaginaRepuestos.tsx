import { useEffect, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Aviso, Boton, Campo, Cargando, Dialogo, Distintivo, Vacio } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { formatearMoneda, formatearNumero } from '@/lib/formato';
import { useSesion } from '@/app/sesion';
import {
  borrarRepuesto,
  crearRepuesto,
  editarRepuesto,
  listarCatalogo,
  type DatosRepuesto,
  type Repuesto,
} from './api';

const POR_PAGINA = 20;

export function PaginaRepuestos() {
  const { claims } = useSesion();
  const clienteQuery = useQueryClient();

  const [texto, setTexto] = useState('');
  const [busqueda, setBusqueda] = useState('');
  const [soloBajoMinimo, setSoloBajoMinimo] = useState(false);
  const [desplazamiento, setDesplazamiento] = useState(0);
  const [editando, setEditando] = useState<Repuesto | 'nuevo' | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      setBusqueda(texto.trim().length >= 3 ? texto.trim() : '');
      setDesplazamiento(0);
    }, 300);
    return () => clearTimeout(t);
  }, [texto]);

  const filtros = { busqueda, soloBajoMinimo, limite: POR_PAGINA, desplazamiento };
  const consulta = useQuery({
    queryKey: ['repuestos', filtros],
    queryFn: () => listarCatalogo(filtros),
  });

  const refrescar = () => clienteQuery.invalidateQueries({ queryKey: ['repuestos'] });

  const mutBorrar = useMutation({
    mutationFn: borrarRepuesto,
    onSuccess: () => {
      setError(null);
      refrescar();
    },
    onError: (e) => setError(e instanceof ErrorApi ? e.message : 'No se pudo borrar la pieza.'),
  });

  const puedeEscribir =
    claims?.rol === 'admin_taller' || claims?.rol === 'encargado_repuestos';

  const total = consulta.data?.total ?? 0;
  const items = consulta.data?.items ?? [];
  const paginas = Math.max(1, Math.ceil(total / POR_PAGINA));

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
          <h1 style={{ fontSize: 'var(--mch-txt-xl)' }}>Repuestos</h1>
          <p
            style={{
              margin: 'var(--mch-esp-1) 0 0',
              color: 'var(--mch-texto-secundario)',
              fontSize: 'var(--mch-txt-sm)',
            }}
          >
            {total} {total === 1 ? 'pieza en el catálogo' : 'piezas en el catálogo'}
          </p>
        </div>
        {puedeEscribir && <Boton onClick={() => setEditando('nuevo')}>Nueva pieza</Boton>}
      </header>

      <div
        style={{
          display: 'flex',
          gap: 'var(--mch-esp-4)',
          alignItems: 'center',
          flexWrap: 'wrap',
          marginBottom: 'var(--mch-esp-4)',
        }}
      >
        <input
          className="mch-campo__control"
          style={{ maxWidth: 320 }}
          type="search"
          placeholder="Buscar por SKU, nombre o categoría…"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          aria-label="Buscar repuestos"
        />
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
            checked={soloBajoMinimo}
            onChange={(e) => {
              setSoloBajoMinimo(e.target.checked);
              setDesplazamiento(0);
            }}
          />
          Solo lo que hay que reponer
        </label>
      </div>

      {error && (
        <div style={{ marginBottom: 'var(--mch-esp-4)' }}>
          <Aviso tono="alerta">{error}</Aviso>
        </div>
      )}

      <div className="mch-panel">
        {consulta.isLoading ? (
          <Cargando />
        ) : consulta.isError ? (
          <div style={{ padding: 'var(--mch-esp-6)' }}>
            <Aviso tono="error">
              {consulta.error instanceof ErrorApi
                ? consulta.error.message
                : 'No se pudo cargar el catálogo.'}
            </Aviso>
          </div>
        ) : items.length === 0 ? (
          <Vacio
            titulo={busqueda || soloBajoMinimo ? 'Sin resultados' : 'El catálogo está vacío'}
            detalle={
              busqueda || soloBajoMinimo
                ? undefined
                : 'Da de alta las piezas que usas siempre para no reescribirlas en cada orden.'
            }
          />
        ) : (
          <div className="mch-tabla-envoltura">
            <table className="mch-tabla">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Pieza</th>
                  <th>Costo</th>
                  <th>Precio</th>
                  <th>Existencias</th>
                  <th>Proveedor</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((p) => (
                  <tr key={p.id}>
                    <td style={{ fontFamily: 'var(--mch-fuente-mono)', fontSize: 'var(--mch-txt-xs)' }}>
                      {p.sku}
                    </td>
                    <td>
                      <div style={{ fontWeight: 560 }}>{p.nombre}</div>
                      {p.categoria && (
                        <div
                          style={{
                            color: 'var(--mch-texto-secundario)',
                            fontSize: 'var(--mch-txt-xs)',
                          }}
                        >
                          {p.categoria}
                        </div>
                      )}
                    </td>
                    <td className="mch-linea__importe">{formatearMoneda(p.costo)}</td>
                    <td className="mch-linea__importe">{formatearMoneda(p.precio_venta)}</td>
                    <td>
                      {formatearNumero(p.stock, 0)} {p.unidad}
                      {p.bajo_minimo && (
                        <>
                          {' '}
                          <Distintivo tono="inactivo">reponer</Distintivo>
                        </>
                      )}
                    </td>
                    <td>{p.proveedor ?? '—'}</td>
                    <td>
                      <div className="mch-tabla__acciones">
                        {puedeEscribir && (
                          <>
                            <Boton variante="fantasma" onClick={() => setEditando(p)}>
                              Editar
                            </Boton>
                            <Boton variante="fantasma" onClick={() => mutBorrar.mutate(p.id)}>
                              Borrar
                            </Boton>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {paginas > 1 && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: 'var(--mch-esp-4)',
            fontSize: 'var(--mch-txt-sm)',
            color: 'var(--mch-texto-secundario)',
          }}
        >
          <span>
            Página {Math.floor(desplazamiento / POR_PAGINA) + 1} de {paginas}
          </span>
          <div style={{ display: 'flex', gap: 'var(--mch-esp-2)' }}>
            <Boton
              variante="secundario"
              disabled={desplazamiento === 0}
              onClick={() => setDesplazamiento((d) => Math.max(0, d - POR_PAGINA))}
            >
              Anterior
            </Boton>
            <Boton
              variante="secundario"
              disabled={desplazamiento + POR_PAGINA >= total}
              onClick={() => setDesplazamiento((d) => d + POR_PAGINA)}
            >
              Siguiente
            </Boton>
          </div>
        </div>
      )}

      {editando && (
        <FormularioRepuesto
          repuesto={editando === 'nuevo' ? undefined : editando}
          onCerrar={() => setEditando(null)}
          onGuardar={async (datos) => {
            if (editando === 'nuevo') await crearRepuesto(datos);
            else await editarRepuesto(editando.id, datos);
            await refrescar();
          }}
        />
      )}
    </>
  );
}

/* -------------------------------------------------------------------------- */

function FormularioRepuesto({
  repuesto,
  onCerrar,
  onGuardar,
}: {
  repuesto?: Repuesto;
  onCerrar: () => void;
  onGuardar: (d: DatosRepuesto) => Promise<void>;
}) {
  const [datos, setDatos] = useState<DatosRepuesto>({
    sku: repuesto?.sku ?? '',
    nombre: repuesto?.nombre ?? '',
    categoria: repuesto?.categoria ?? '',
    unidad: repuesto?.unidad ?? 'unidad',
    costo: Number(repuesto?.costo ?? 0),
    precio_venta: Number(repuesto?.precio_venta ?? 0),
    stock: Number(repuesto?.stock ?? 0),
    stock_minimo: Number(repuesto?.stock_minimo ?? 0),
    proveedor: repuesto?.proveedor ?? '',
  });
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  const cambiar = <K extends keyof DatosRepuesto>(campo: K, valor: DatosRepuesto[K]) =>
    setDatos((d) => ({ ...d, [campo]: valor }));

  async function alEnviar(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setGuardando(true);
    try {
      await onGuardar(datos);
      onCerrar();
    } catch (err) {
      setError(
        err instanceof ErrorApi && err.esDeUsuario ? err.message : 'No se pudo guardar la pieza.',
      );
    } finally {
      setGuardando(false);
    }
  }

  const dos = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--mch-esp-4)' };
  const margen =
    Number(datos.precio_venta ?? 0) - Number(datos.costo ?? 0);

  return (
    <Dialogo
      titulo={repuesto ? `Editar ${repuesto.sku}` : 'Nueva pieza'}
      onCerrar={onCerrar}
      pie={
        <>
          <Boton variante="secundario" type="button" onClick={onCerrar}>
            Cancelar
          </Boton>
          <Boton type="submit" form="formulario-repuesto" cargando={guardando}>
            Guardar
          </Boton>
        </>
      }
    >
      <form
        id="formulario-repuesto"
        onSubmit={alEnviar}
        style={{ display: 'grid', gap: 'var(--mch-esp-4)' }}
      >
        {error && <Aviso tono="error">{error}</Aviso>}

        <div style={dos}>
          <Campo
            etiqueta="SKU"
            required
            autoFocus
            ayuda="Se guarda en mayúsculas"
            value={datos.sku}
            onChange={(e) => cambiar('sku', e.target.value)}
          />
          <Campo
            etiqueta="Categoría"
            value={datos.categoria ?? ''}
            onChange={(e) => cambiar('categoria', e.target.value)}
          />
        </div>

        <Campo
          etiqueta="Nombre"
          required
          value={datos.nombre}
          onChange={(e) => cambiar('nombre', e.target.value)}
        />

        <div style={dos}>
          <Campo
            etiqueta="Costo"
            type="number"
            min={0}
            step={0.5}
            value={datos.costo ?? 0}
            onChange={(e) => cambiar('costo', Number(e.target.value))}
          />
          <Campo
            etiqueta="Precio de venta"
            type="number"
            min={0}
            step={0.5}
            ayuda={margen > 0 ? `Margen: ${formatearMoneda(margen)}` : undefined}
            value={datos.precio_venta ?? 0}
            onChange={(e) => cambiar('precio_venta', Number(e.target.value))}
          />
        </div>

        <div style={dos}>
          <Campo
            etiqueta="Existencias"
            type="number"
            min={0}
            value={datos.stock ?? 0}
            onChange={(e) => cambiar('stock', Number(e.target.value))}
          />
          <Campo
            etiqueta="Mínimo antes de reponer"
            type="number"
            min={0}
            value={datos.stock_minimo ?? 0}
            onChange={(e) => cambiar('stock_minimo', Number(e.target.value))}
          />
        </div>

        <div style={dos}>
          <Campo
            etiqueta="Unidad"
            value={datos.unidad ?? 'unidad'}
            onChange={(e) => cambiar('unidad', e.target.value)}
          />
          <Campo
            etiqueta="Proveedor"
            value={datos.proveedor ?? ''}
            onChange={(e) => cambiar('proveedor', e.target.value)}
          />
        </div>

        <Aviso tono="info">
          Las existencias son informativas: instalar una pieza todavía no las descuenta.
        </Aviso>
      </form>
    </Dialogo>
  );
}
