/**
 * El presupuesto tal como lo ve el cliente, desde el enlace que le mandaron.
 *
 * No hay sesión, ni barra lateral, ni nada de la aplicación: es una página
 * suelta. Quien la abre no es del taller y probablemente entra desde el móvil,
 * así que todo cabe en una columna y las dos acciones son botones grandes.
 */
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Aviso, Boton, Campo, Cargando, Marca } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { formatearFecha, formatearMoneda, formatearNumero } from '@/lib/formato';
import { responderPresupuestoPublico, verPresupuestoPublico } from './api';

export function PaginaPresupuestoPublico() {
  const { token = '' } = useParams();
  const clienteQuery = useQueryClient();
  const [comentario, setComentario] = useState('');
  const [confirmando, setConfirmando] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  const consulta = useQuery({
    queryKey: ['presupuesto-publico', token],
    queryFn: () => verPresupuestoPublico(token),
    retry: false,
  });

  const responder = useMutation({
    mutationFn: (aprobado: boolean) =>
      responderPresupuestoPublico(token, aprobado, comentario || undefined),
    onSuccess: () => {
      setError(null);
      setConfirmando(null);
      clienteQuery.invalidateQueries({ queryKey: ['presupuesto-publico', token] });
    },
    onError: (e) =>
      setError(
        e instanceof ErrorApi ? e.message : 'No se pudo enviar tu respuesta. Inténtalo de nuevo.',
      ),
  });

  if (consulta.isLoading) {
    return (
      <main className="mch-publico">
        <Cargando texto="Abriendo el presupuesto…" />
      </main>
    );
  }

  if (consulta.isError || !consulta.data) {
    return (
      <main className="mch-publico">
        <div className="mch-publico__tarjeta" style={{ padding: 'var(--mch-esp-8)' }}>
          <Aviso tono="error">
            {consulta.error instanceof ErrorApi
              ? consulta.error.message
              : 'Este enlace no es válido.'}
          </Aviso>
          <p style={{ color: 'var(--mch-texto-secundario)', fontSize: 'var(--mch-txt-sm)' }}>
            Si crees que es un error, contacta al taller que te lo envió.
          </p>
        </div>
      </main>
    );
  }

  const p = consulta.data;

  return (
    <main className="mch-publico">
      <div className="mch-publico__tarjeta">
        <header className="mch-publico__cabecera">
          <div>
            <div className="mch-publico__taller">{p.taller_nombre}</div>
            {p.taller_telefono && (
              <a className="mch-publico__telefono" href={`tel:${p.taller_telefono}`}>
                {p.taller_telefono}
              </a>
            )}
          </div>
          <div className="mch-publico__folio">
            {p.folio_orden}
            <span>versión {p.version}</span>
          </div>
        </header>

        <section className="mch-publico__vehiculo">
          <strong>{p.placa}</strong> · {p.vehiculo}
        </section>

        {p.cerrado && (
          <div style={{ padding: '0 var(--mch-esp-6)' }}>
            <Aviso tono={p.estado === 'aprobado' ? 'info' : 'alerta'}>
              {p.estado === 'aprobado'
                ? `Aprobaste este presupuesto el ${formatearFecha(p.respondido_en)}. El taller ya está trabajando en tu vehículo.`
                : p.estado === 'rechazado'
                  ? `Rechazaste este presupuesto el ${formatearFecha(p.respondido_en)}.`
                  : `Este presupuesto venció el ${formatearFecha(p.valido_hasta)}. Pide al taller uno nuevo.`}
            </Aviso>
          </div>
        )}

        <section className="mch-publico__lineas">
          {p.items.map((i) => (
            <div key={i.id} className="mch-publico__linea">
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
        </section>

        <section className="mch-publico__totales">
          <div>
            <span>Subtotal</span>
            <span>{formatearMoneda(p.subtotal)}</span>
          </div>
          {Number(p.descuento) > 0 && (
            <div>
              <span>Descuento</span>
              <span>−{formatearMoneda(p.descuento)}</span>
            </div>
          )}
          {Number(p.impuesto_pct) > 0 && (
            <div>
              <span>Impuesto ({p.impuesto_pct}%)</span>
              <span>{formatearMoneda(p.impuesto_monto)}</span>
            </div>
          )}
          <div className="mch-publico__total">
            <span>Total</span>
            <span>
              {formatearMoneda(p.total)} {p.moneda}
            </span>
          </div>
        </section>

        {!p.cerrado && (
          <section className="mch-publico__acciones">
            {error && <Aviso tono="error">{error}</Aviso>}

            {p.valido_hasta && (
              <p className="mch-publico__nota">
                Este presupuesto es válido hasta el {formatearFecha(p.valido_hasta)}.
              </p>
            )}

            {confirmando === null ? (
              <div className="mch-publico__botones">
                <Boton onClick={() => setConfirmando(true)}>Aprobar el presupuesto</Boton>
                <Boton variante="secundario" onClick={() => setConfirmando(false)}>
                  No aprobar
                </Boton>
              </div>
            ) : (
              <>
                <Aviso tono={confirmando ? 'info' : 'alerta'}>
                  {confirmando
                    ? `Vas a aprobar ${formatearMoneda(p.total)} ${p.moneda} de trabajo. El taller empezará la reparación.`
                    : 'Vas a rechazar este presupuesto. El taller se pondrá en contacto contigo.'}
                </Aviso>
                <Campo
                  etiqueta="Comentario (opcional)"
                  ayuda="Lo verá el taller junto a tu respuesta"
                  value={comentario}
                  onChange={(e) => setComentario(e.target.value)}
                />
                <div className="mch-publico__botones">
                  <Boton
                    variante={confirmando ? 'primario' : 'peligro'}
                    cargando={responder.isPending}
                    onClick={() => responder.mutate(confirmando)}
                  >
                    {confirmando ? 'Sí, aprobar' : 'Sí, rechazar'}
                  </Boton>
                  <Boton
                    variante="secundario"
                    disabled={responder.isPending}
                    onClick={() => setConfirmando(null)}
                  >
                    Volver
                  </Boton>
                </div>
              </>
            )}
          </section>
        )}

        {p.comentario_cliente && (
          <section style={{ padding: '0 var(--mch-esp-6) var(--mch-esp-6)' }}>
            <div className="mch-bitacora__comentario">Tu comentario: {p.comentario_cliente}</div>
          </section>
        )}
      </div>

      <footer className="mch-publico__pie">
        <Marca compacta />
        <span>Presupuesto emitido con Mechanified</span>
      </footer>
    </main>
  );
}
