import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Aviso, Boton, Cargando, Dialogo, Distintivo, Seccion, Vacio } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { formatearFecha } from '@/lib/formato';
import { useSesion } from '@/app/sesion';
import {
  listarNotificaciones,
  reintentarAviso,
  vistaPreviaCorreo,
  type EstadoAviso,
  type Notificacion,
} from './api';

const TONO: Record<EstadoAviso, 'activo' | 'inactivo' | 'neutro'> = {
  enviada: 'activo',
  fallida: 'inactivo',
  pendiente: 'neutro',
};

/**
 * Los correos que le han salido al cliente por esta orden.
 *
 * Existe porque el envío es automático: sin esta lista, "¿le llegó el
 * presupuesto?" solo se podría responder preguntándoselo al cliente. Aquí se ve
 * a qué dirección salió, si salió, y qué dijo el servidor cuando no salió.
 *
 * Solo lo ve administración y asesoría, que es lo mismo que deja leer la
 * política RLS de `notificaciones`.
 */
export function PanelNotificaciones({ ordenId }: { ordenId: string }) {
  const { claims } = useSesion();
  const clienteQuery = useQueryClient();
  const [viendo, setViendo] = useState<Notificacion | null>(null);
  const [error, setError] = useState<string | null>(null);

  const puedeVer = claims?.rol === 'admin_taller' || claims?.rol === 'asesor_servicio';

  const consulta = useQuery({
    queryKey: ['orden', ordenId, 'notificaciones'],
    queryFn: () => listarNotificaciones(ordenId),
    enabled: puedeVer,
    // Mientras haya algo en cola se refresca solo: el worker tarda segundos en
    // vaciarla y sería raro tener que recargar la página para ver el desenlace.
    refetchInterval: (q) =>
      (q.state.data ?? []).some((n) => n.estado === 'pendiente') ? 5000 : false,
  });

  const mutReintentar = useMutation({
    mutationFn: (id: string) => reintentarAviso(id),
    onSuccess: async () => {
      setError(null);
      await clienteQuery.invalidateQueries({ queryKey: ['orden', ordenId, 'notificaciones'] });
    },
    onError: (e) =>
      setError(e instanceof ErrorApi ? e.message : 'No se pudo reencolar el aviso.'),
  });

  if (!puedeVer) return null;

  const avisos = consulta.data ?? [];
  const enCola = avisos.filter((a) => a.estado === 'pendiente').length;

  return (
    <>
      <Seccion
        titulo="Avisos al cliente"
        resumen={enCola > 0 ? `${enCola} en cola de envío` : undefined}
      >
        {error && (
          <div style={{ padding: 'var(--mch-esp-4) var(--mch-esp-5) 0' }}>
            <Aviso tono="alerta">{error}</Aviso>
          </div>
        )}

        {consulta.isLoading ? (
          <Cargando texto="" />
        ) : avisos.length === 0 ? (
          <Vacio
            titulo="Sin avisos todavía"
            detalle="Salen solos: al enviar el presupuesto, cuando el vehículo queda listo y al entregarlo."
          />
        ) : (
          avisos.map((a) => (
            <div key={a.id} className="mch-linea">
              <div style={{ minWidth: 0 }}>
                <div>
                  {a.plantilla_etiqueta}{' '}
                  <Distintivo tono={TONO[a.estado]}>{a.estado_etiqueta}</Distintivo>
                </div>
                <div className="mch-linea__detalle">
                  {a.destinatario} ·{' '}
                  {a.enviada_en
                    ? `enviado el ${formatearFecha(a.enviada_en, true)}`
                    : a.estado === 'fallida'
                      ? `${a.intentos} ${a.intentos === 1 ? 'intento' : 'intentos'}`
                      : 'en cola'}
                </div>
                {a.ultimo_error && (
                  <div className="mch-linea__detalle" style={{ color: 'var(--mch-alerta)' }}>
                    {a.ultimo_error}
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', gap: 'var(--mch-esp-2)', flex: 'none' }}>
                {a.estado === 'fallida' && (
                  <Boton
                    variante="secundario"
                    cargando={mutReintentar.isPending}
                    onClick={() => mutReintentar.mutate(a.id)}
                  >
                    Reintentar
                  </Boton>
                )}
                <Boton variante="fantasma" onClick={() => setViendo(a)}>
                  Ver correo
                </Boton>
              </div>
            </div>
          ))
        )}
      </Seccion>

      {viendo && <DialogoCorreo aviso={viendo} onCerrar={() => setViendo(null)} />}
    </>
  );
}

/* -------------------------------------------------------------------------- */

function DialogoCorreo({ aviso, onCerrar }: { aviso: Notificacion; onCerrar: () => void }) {
  const consulta = useQuery({
    queryKey: ['notificacion', aviso.id, 'vista-previa'],
    queryFn: () => vistaPreviaCorreo(aviso.id),
    retry: false,
  });

  const correo = consulta.data;

  return (
    <Dialogo
      titulo="Correo al cliente"
      onCerrar={onCerrar}
      pie={
        <Boton variante="secundario" onClick={onCerrar}>
          Cerrar
        </Boton>
      }
    >
      {consulta.isLoading ? (
        <Cargando texto="" />
      ) : consulta.isError || !correo ? (
        <Aviso tono="alerta">
          {consulta.error instanceof ErrorApi
            ? consulta.error.message
            : 'No se pudo redactar este correo.'}
        </Aviso>
      ) : (
        <>
          <div className="mch-datos" style={{ padding: 0 }}>
            <div>
              <div className="mch-dato__etiqueta">Para</div>
              <div className="mch-dato__valor">{correo.destinatario}</div>
            </div>
            <div>
              <div className="mch-dato__etiqueta">Asunto</div>
              <div className="mch-dato__valor">{correo.asunto}</div>
            </div>
          </div>

          {/* En un iframe aislado: es HTML pensado para un cliente de correo y
              sus estilos no deben mezclarse con los de la aplicación. */}
          <iframe
            title={correo.asunto}
            srcDoc={correo.html}
            sandbox=""
            style={{
              width: '100%',
              height: 460,
              border: '1px solid var(--mch-borde)',
              borderRadius: 'var(--mch-radio)',
              background: '#ffffff',
            }}
          />

          <span className="mch-campo__ayuda">
            Se redacta con los datos de ahora mismo, igual que al enviarlo.
          </span>
        </>
      )}
    </Dialogo>
  );
}
