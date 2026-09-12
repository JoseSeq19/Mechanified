import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Aviso, Boton, Campo, Cargando, Dialogo, Seccion, Vacio } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { formatearMoneda, formatearNumero } from '@/lib/formato';
import { useSesion } from '@/app/sesion';
import {
  borrarManoObra,
  crearManoObra,
  editarManoObra,
  listarManoObra,
  type ManoObra,
  type ManoObraNueva,
} from './api';

export function PanelManoObra({
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
  const [editando, setEditando] = useState<ManoObra | 'nueva' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const consulta = useQuery({
    queryKey: ['orden', ordenId, 'mano-obra'],
    queryFn: () => listarManoObra(ordenId),
  });

  // Cambiar una línea mueve el total de la orden, así que hay que refrescar
  // también la ficha: el trigger de Postgres ya actualizó la cabecera.
  const refrescar = async () => {
    await clienteQuery.invalidateQueries({ queryKey: ['orden', ordenId, 'mano-obra'] });
    onCambio();
  };

  const mutBorrar = useMutation({
    mutationFn: borrarManoObra,
    onSuccess: () => {
      setError(null);
      refrescar();
    },
    onError: (e) =>
      setError(e instanceof ErrorApi ? e.message : 'No se pudo quitar la línea de trabajo.'),
  });

  const puedeEscribir =
    !cerrada &&
    (claims?.rol === 'tecnico' ||
      claims?.rol === 'admin_taller' ||
      claims?.rol === 'asesor_servicio');

  const datos = consulta.data;
  const lineas = datos?.lineas ?? [];

  return (
    <>
      <Seccion
        titulo="Mano de obra"
        resumen={
          lineas.length > 0
            ? `${formatearNumero(datos?.total_horas ?? 0)} h en ${lineas.length} ${
                lineas.length === 1 ? 'línea' : 'líneas'
              }`
            : undefined
        }
        accion={puedeEscribir && <Boton onClick={() => setEditando('nueva')}>Cargar trabajo</Boton>}
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
            titulo="Sin trabajo cargado"
            detalle={cerrada ? undefined : 'Cada línea son horas por la tarifa del taller.'}
          />
        ) : (
          <>
            {lineas.map((l) => (
              <div key={l.id} className="mch-linea">
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 560 }}>{l.descripcion}</div>
                  <div className="mch-linea__detalle">
                    {formatearNumero(l.horas)} h × {formatearMoneda(l.tarifa_hora)}
                    {l.tecnico_nombre && ` · ${l.tecnico_nombre}`}
                  </div>
                </div>
                <div
                  style={{ display: 'flex', alignItems: 'center', gap: 'var(--mch-esp-2)' }}
                >
                  <span className="mch-linea__importe">{formatearMoneda(l.subtotal)}</span>
                  {puedeEscribir && (
                    <>
                      <Boton variante="fantasma" onClick={() => setEditando(l)}>
                        Editar
                      </Boton>
                      <Boton
                        variante="fantasma"
                        aria-label="Quitar línea"
                        onClick={() => mutBorrar.mutate(l.id)}
                      >
                        ✕
                      </Boton>
                    </>
                  )}
                </div>
              </div>
            ))}
            <div className="mch-total">
              <span>Total mano de obra</span>
              <span>{formatearMoneda(datos?.total ?? 0)}</span>
            </div>
          </>
        )}
      </Seccion>

      {editando && (
        <DialogoLinea
          linea={editando === 'nueva' ? undefined : editando}
          onCerrar={() => setEditando(null)}
          onGuardar={async (d) => {
            if (editando === 'nueva') await crearManoObra(ordenId, d);
            else await editarManoObra(editando.id, d);
            await refrescar();
          }}
        />
      )}
    </>
  );
}

function DialogoLinea({
  linea,
  onCerrar,
  onGuardar,
}: {
  linea?: ManoObra;
  onCerrar: () => void;
  onGuardar: (d: ManoObraNueva) => Promise<void>;
}) {
  const [descripcion, setDescripcion] = useState(linea?.descripcion ?? '');
  const [horas, setHoras] = useState(linea?.horas ?? '');
  const [tarifa, setTarifa] = useState(linea?.tarifa_hora ?? '');
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  async function alEnviar(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setGuardando(true);
    try {
      await onGuardar({
        descripcion,
        horas: Number(horas),
        // Sin tarifa, el backend toma la del taller y la congela en la línea.
        tarifa_hora: tarifa === '' ? null : Number(tarifa),
      });
      onCerrar();
    } catch (err) {
      setError(
        err instanceof ErrorApi && err.esDeUsuario ? err.message : 'No se pudo guardar la línea.',
      );
    } finally {
      setGuardando(false);
    }
  }

  const subtotal = Number(horas) * Number(tarifa || 0);

  return (
    <Dialogo
      titulo={linea ? 'Editar trabajo' : 'Cargar trabajo'}
      onCerrar={onCerrar}
      pie={
        <>
          <Boton variante="secundario" type="button" onClick={onCerrar}>
            Cancelar
          </Boton>
          <Boton type="submit" form="formulario-mano-obra" cargando={guardando}>
            Guardar
          </Boton>
        </>
      }
    >
      <form
        id="formulario-mano-obra"
        onSubmit={alEnviar}
        style={{ display: 'grid', gap: 'var(--mch-esp-4)' }}
      >
        {error && <Aviso tono="error">{error}</Aviso>}

        <Campo
          etiqueta="Qué se hace"
          required
          autoFocus
          value={descripcion}
          onChange={(e) => setDescripcion(e.target.value)}
        />
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--mch-esp-4)' }}>
          <Campo
            etiqueta="Horas"
            type="number"
            min={0.25}
            step={0.25}
            required
            value={horas}
            onChange={(e) => setHoras(e.target.value)}
          />
          <Campo
            etiqueta="Tarifa por hora"
            type="number"
            min={0}
            step={0.5}
            ayuda={linea ? undefined : 'Vacío usa la del taller'}
            value={tarifa}
            onChange={(e) => setTarifa(e.target.value)}
          />
        </div>

        {Number.isFinite(subtotal) && subtotal > 0 && (
          <Aviso tono="info">Subtotal: {formatearMoneda(subtotal)}</Aviso>
        )}
      </form>
    </Dialogo>
  );
}
