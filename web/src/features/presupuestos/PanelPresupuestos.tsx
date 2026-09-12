import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Aviso, Boton, Campo, Cargando, Dialogo, Distintivo, Seccion, Vacio } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { formatearFecha, formatearMoneda, formatearNumero } from '@/lib/formato';
import { useSesion } from '@/app/sesion';
import {
  anotarRespuesta,
  emitirPresupuesto,
  enviarPresupuesto,
  listarPresupuestos,
  obtenerPresupuesto,
  type DatosEmitir,
  type EstadoPresupuesto,
  type PresupuestoResumen,
} from './api';

const TONO: Record<EstadoPresupuesto, 'activo' | 'inactivo' | 'neutro'> = {
  borrador: 'neutro',
  enviado: 'neutro',
  aprobado: 'activo',
  rechazado: 'inactivo',
  vencido: 'inactivo',
};

export function PanelPresupuestos({
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
  const [emitiendo, setEmitiendo] = useState(false);
  const [viendo, setViendo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const consulta = useQuery({
    queryKey: ['orden', ordenId, 'presupuestos'],
    queryFn: () => listarPresupuestos(ordenId),
  });

  // Aprobar un presupuesto puede mover la orden, así que la ficha se refresca.
  const refrescar = async () => {
    await clienteQuery.invalidateQueries({ queryKey: ['orden', ordenId, 'presupuestos'] });
    onCambio();
  };

  const puedeEmitir =
    !cerrada && (claims?.rol === 'admin_taller' || claims?.rol === 'asesor_servicio');

  const versiones = consulta.data ?? [];
  const vigente = versiones.at(-1);

  return (
    <>
      <Seccion
        titulo="Presupuesto"
        resumen={
          versiones.length > 1
            ? `${versiones.length} versiones · la vigente es la v${vigente?.version}`
            : undefined
        }
        accion={
          puedeEmitir && (
            <Boton onClick={() => setEmitiendo(true)}>
              {versiones.length === 0 ? 'Emitir presupuesto' : 'Emitir nueva versión'}
            </Boton>
          )
        }
      >
        {error && (
          <div style={{ padding: 'var(--mch-esp-4) var(--mch-esp-5) 0' }}>
            <Aviso tono="alerta">{error}</Aviso>
          </div>
        )}

        {consulta.isLoading ? (
          <Cargando texto="" />
        ) : versiones.length === 0 ? (
          <Vacio
            titulo="Sin presupuestar"
            detalle={
              cerrada
                ? undefined
                : 'Emitir copia el trabajo y las piezas que tenga la orden ahora mismo.'
            }
          />
        ) : (
          versiones.map((v) => (
            <FilaVersion
              key={v.id}
              version={v}
              onAbrir={() => {
                setError(null);
                setViendo(v.id);
              }}
            />
          ))
        )}
      </Seccion>

      {emitiendo && (
        <DialogoEmitir
          onCerrar={() => setEmitiendo(false)}
          onEmitir={async (d) => {
            await emitirPresupuesto(ordenId, d);
            await refrescar();
          }}
        />
      )}

      {viendo && (
        <DialogoPresupuesto
          presupuestoId={viendo}
          onCerrar={() => setViendo(null)}
          onCambio={refrescar}
          onError={setError}
        />
      )}
    </>
  );
}

/* -------------------------------------------------------------------------- */

function FilaVersion({
  version,
  onAbrir,
}: {
  version: PresupuestoResumen;
  onAbrir: () => void;
}) {
  return (
    <div className="mch-linea">
      <div>
        <div style={{ fontWeight: 560 }}>
          Versión {version.version}{' '}
          <Distintivo tono={version.caducado ? 'inactivo' : TONO[version.estado]}>
            {version.caducado ? 'Vencido' : version.estado_etiqueta}
          </Distintivo>
        </div>
        <div className="mch-linea__detalle">
          {version.respondido_en
            ? `Respondido el ${formatearFecha(version.respondido_en)}`
            : version.enviado_en
              ? `Enviado el ${formatearFecha(version.enviado_en)} · válido hasta ${formatearFecha(
                  version.valido_hasta,
                )}`
              : 'Todavía es borrador'}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--mch-esp-2)' }}>
        <span className="mch-linea__importe">{formatearMoneda(version.total)}</span>
        <Boton variante="fantasma" onClick={onAbrir}>
          Abrir
        </Boton>
      </div>
    </div>
  );
}

function DialogoEmitir({
  onCerrar,
  onEmitir,
}: {
  onCerrar: () => void;
  onEmitir: (d: DatosEmitir) => Promise<void>;
}) {
  const [descuento, setDescuento] = useState('');
  const [impuesto, setImpuesto] = useState('');
  const [valido, setValido] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  async function alEnviar(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setGuardando(true);
    try {
      await onEmitir({
        descuento: descuento === '' ? 0 : Number(descuento),
        // Vacío deja que el backend tome el impuesto del taller; un 0 escrito a
        // mano significa exento, y eso sí se respeta.
        impuesto_pct: impuesto === '' ? null : Number(impuesto),
        valido_hasta: valido || null,
      });
      onCerrar();
    } catch (err) {
      setError(
        err instanceof ErrorApi && err.esDeUsuario
          ? err.message
          : 'No se pudo emitir el presupuesto.',
      );
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Dialogo
      titulo="Emitir presupuesto"
      onCerrar={onCerrar}
      pie={
        <>
          <Boton variante="secundario" type="button" onClick={onCerrar}>
            Cancelar
          </Boton>
          <Boton type="submit" form="formulario-emitir" cargando={guardando}>
            Emitir
          </Boton>
        </>
      }
    >
      <form
        id="formulario-emitir"
        onSubmit={alEnviar}
        style={{ display: 'grid', gap: 'var(--mch-esp-4)' }}
      >
        {error && <Aviso tono="error">{error}</Aviso>}

        <Aviso tono="info">
          Se copian el trabajo y las piezas que tenga la orden ahora. Una vez enviado, el
          documento no cambia: si hace falta ajustar algo se emite otra versión.
        </Aviso>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--mch-esp-4)' }}>
          <Campo
            etiqueta="Descuento"
            type="number"
            min={0}
            step={0.5}
            value={descuento}
            onChange={(e) => setDescuento(e.target.value)}
          />
          <Campo
            etiqueta="Impuesto (%)"
            type="number"
            min={0}
            max={100}
            step={0.5}
            ayuda="Vacío usa el del taller"
            value={impuesto}
            onChange={(e) => setImpuesto(e.target.value)}
          />
        </div>
        <Campo
          etiqueta="Válido hasta"
          type="date"
          ayuda="Vacío usa los días configurados en el taller"
          value={valido}
          onChange={(e) => setValido(e.target.value)}
        />
      </form>
    </Dialogo>
  );
}

function DialogoPresupuesto({
  presupuestoId,
  onCerrar,
  onCambio,
  onError,
}: {
  presupuestoId: string;
  onCerrar: () => void;
  onCambio: () => Promise<void>;
  onError: (m: string) => void;
}) {
  const clienteQuery = useQueryClient();
  const [comentario, setComentario] = useState('');
  const [copiado, setCopiado] = useState(false);

  const consulta = useQuery({
    queryKey: ['presupuesto', presupuestoId],
    queryFn: () => obtenerPresupuesto(presupuestoId),
  });

  const tras = async () => {
    await clienteQuery.invalidateQueries({ queryKey: ['presupuesto', presupuestoId] });
    await onCambio();
  };

  const fallo = (e: unknown, respaldo: string) =>
    onError(e instanceof ErrorApi ? e.message : respaldo);

  const mutEnviar = useMutation({
    mutationFn: () => enviarPresupuesto(presupuestoId),
    onSuccess: tras,
    onError: (e) => fallo(e, 'No se pudo enviar el presupuesto.'),
  });

  const mutResponder = useMutation({
    mutationFn: (aprobado: boolean) => anotarRespuesta(presupuestoId, aprobado, comentario),
    onSuccess: async () => {
      await tras();
      onCerrar();
    },
    onError: (e) => fallo(e, 'No se pudo anotar la respuesta.'),
  });

  const p = consulta.data;

  return (
    <Dialogo
      titulo={p ? `Presupuesto v${p.version}` : 'Presupuesto'}
      onCerrar={onCerrar}
      pie={
        p && (
          <>
            <Boton variante="secundario" onClick={onCerrar}>
              Cerrar
            </Boton>
            {p.estado === 'borrador' && (
              <Boton cargando={mutEnviar.isPending} onClick={() => mutEnviar.mutate()}>
                Enviar al cliente
              </Boton>
            )}
            {p.estado === 'enviado' && !p.caducado && (
              <>
                <Boton
                  variante="peligro"
                  cargando={mutResponder.isPending}
                  onClick={() => mutResponder.mutate(false)}
                >
                  Rechazó
                </Boton>
                <Boton
                  cargando={mutResponder.isPending}
                  onClick={() => mutResponder.mutate(true)}
                >
                  Aprobó
                </Boton>
              </>
            )}
          </>
        )
      }
    >
      {consulta.isLoading || !p ? (
        <Cargando texto="" />
      ) : (
        <>
          <div style={{ display: 'flex', gap: 'var(--mch-esp-3)', alignItems: 'center' }}>
            <Distintivo tono={p.caducado ? 'inactivo' : TONO[p.estado]}>
              {p.caducado ? 'Vencido' : p.estado_etiqueta}
            </Distintivo>
            {p.valido_hasta && (
              <span className="mch-linea__detalle">
                Válido hasta {formatearFecha(p.valido_hasta)}
              </span>
            )}
          </div>

          <div className="mch-panel" style={{ overflow: 'hidden' }}>
            {p.items.map((i) => (
              <div key={i.id} className="mch-linea">
                <div>
                  <div>{i.descripcion}</div>
                  <div className="mch-linea__detalle">
                    {i.tipo_etiqueta} · {formatearNumero(i.cantidad)} ×{' '}
                    {formatearMoneda(i.precio_unitario)}
                  </div>
                </div>
                <span className="mch-linea__importe">{formatearMoneda(i.subtotal)}</span>
              </div>
            ))}
            <div className="mch-total">
              <span>Total</span>
              <span>{formatearMoneda(p.total)}</span>
            </div>
          </div>

          <div className="mch-datos" style={{ padding: 0 }}>
            <div>
              <div className="mch-dato__etiqueta">Mano de obra</div>
              <div className="mch-dato__valor">{formatearMoneda(p.subtotal_mano_obra)}</div>
            </div>
            <div>
              <div className="mch-dato__etiqueta">Repuestos</div>
              <div className="mch-dato__valor">{formatearMoneda(p.subtotal_repuestos)}</div>
            </div>
            <div>
              <div className="mch-dato__etiqueta">Descuento</div>
              <div className="mch-dato__valor">{formatearMoneda(p.descuento)}</div>
            </div>
            <div>
              <div className="mch-dato__etiqueta">Impuesto {p.impuesto_pct}%</div>
              <div className="mch-dato__valor">{formatearMoneda(p.impuesto_monto)}</div>
            </div>
          </div>

          {p.enlace_publico && (
            <div style={{ display: 'grid', gap: 'var(--mch-esp-2)' }}>
              <span className="mch-dato__etiqueta">Enlace para el cliente</span>
              <div style={{ display: 'flex', gap: 'var(--mch-esp-2)' }}>
                <input className="mch-campo__control" readOnly value={p.enlace_publico} />
                <Boton
                  variante="secundario"
                  type="button"
                  onClick={async () => {
                    await navigator.clipboard.writeText(p.enlace_publico!);
                    setCopiado(true);
                    setTimeout(() => setCopiado(false), 2000);
                  }}
                >
                  {copiado ? 'Copiado' : 'Copiar'}
                </Boton>
              </div>
              <span className="mch-campo__ayuda">
                Todavía no se envía solo por correo: cópialo y mándaselo tú.
              </span>
            </div>
          )}

          {p.comentario_cliente && (
            <Aviso tono="info">El cliente dijo: {p.comentario_cliente}</Aviso>
          )}

          {p.estado === 'enviado' && !p.caducado && (
            <Campo
              etiqueta="Comentario del cliente"
              ayuda="Si te contestó por teléfono, anótalo aquí antes de marcar la respuesta"
              value={comentario}
              onChange={(e) => setComentario(e.target.value)}
            />
          )}
        </>
      )}
    </Dialogo>
  );
}
