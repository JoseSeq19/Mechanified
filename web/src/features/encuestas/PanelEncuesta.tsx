import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Aviso, Boton, Cargando, Distintivo, Seccion, Vacio } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { formatearFecha } from '@/lib/formato';
import { useSesion } from '@/app/sesion';
import type { EstadoOrden } from '@/features/ordenes/api';
import { enviarEncuesta, obtenerEncuesta, type Encuesta } from './api';

/**
 * La encuesta de satisfacción de la orden.
 *
 * Solo aparece con el vehículo ya entregado, que es cuando la encuesta existe:
 * la crea la propia entrega, no un botón. El botón que hay aquí es para
 * reenviarla, o para crearla en órdenes entregadas antes de que esto existiera.
 */
export function PanelEncuesta({ ordenId, estado }: { ordenId: string; estado: EstadoOrden }) {
  const { claims } = useSesion();
  const clienteQuery = useQueryClient();
  const [aviso, setAviso] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copiado, setCopiado] = useState(false);

  const entregada = estado === 'entregado';

  const consulta = useQuery({
    queryKey: ['orden', ordenId, 'encuesta'],
    queryFn: () => obtenerEncuesta(ordenId),
    enabled: entregada,
  });

  const mutEnviar = useMutation({
    mutationFn: () => enviarEncuesta(ordenId),
    onSuccess: async (e) => {
      setError(null);
      setAviso(
        e.encolada_a
          ? `Se le envía a ${e.encolada_a}.`
          : 'El cliente no tiene correo registrado: cópiale el enlace y mándaselo por donde hables con él.',
      );
      await clienteQuery.invalidateQueries({ queryKey: ['orden', ordenId, 'encuesta'] });
      await clienteQuery.invalidateQueries({ queryKey: ['orden', ordenId, 'notificaciones'] });
    },
    onError: (e) => {
      setAviso(null);
      setError(e instanceof ErrorApi ? e.message : 'No se pudo enviar la encuesta.');
    },
  });

  if (!entregada) return null;

  const puedeEnviar =
    claims?.rol === 'admin_taller' || claims?.rol === 'asesor_servicio';
  const encuesta = consulta.data ?? null;

  return (
    <Seccion
      titulo="Encuesta de satisfacción"
      resumen={
        encuesta?.respondida
          ? `Respondida el ${formatearFecha(encuesta.respondida_en)}`
          : encuesta?.enviada_en
            ? `Enviada el ${formatearFecha(encuesta.enviada_en)}, sin responder`
            : undefined
      }
      accion={
        puedeEnviar &&
        !encuesta?.respondida && (
          <Boton cargando={mutEnviar.isPending} onClick={() => mutEnviar.mutate()}>
            {encuesta ? 'Reenviar' : 'Enviar encuesta'}
          </Boton>
        )
      }
    >
      {(error || aviso) && (
        <div style={{ padding: 'var(--mch-esp-4) var(--mch-esp-5) 0' }}>
          <Aviso tono={error ? 'alerta' : 'info'}>{error ?? aviso}</Aviso>
        </div>
      )}

      {consulta.isLoading ? (
        <Cargando texto="" />
      ) : !encuesta ? (
        <Vacio
          titulo="Sin encuesta"
          detalle="Esta orden se entregó antes de que existieran las encuestas. Puedes crearla ahora."
        />
      ) : encuesta.respondida ? (
        <Respuestas encuesta={encuesta} />
      ) : (
        <div style={{ padding: 'var(--mch-esp-4) var(--mch-esp-5)', display: 'grid', gap: 'var(--mch-esp-3)' }}>
          <span className="mch-linea__detalle">
            {encuesta.enviada_en
              ? 'El cliente todavía no ha contestado.'
              : 'Todavía no ha salido el correo. Si el cliente no tiene dirección, comparte el enlace.'}
          </span>
          <div style={{ display: 'flex', gap: 'var(--mch-esp-2)' }}>
            <input className="mch-campo__control" readOnly value={encuesta.enlace_publico} />
            <Boton
              variante="secundario"
              onClick={async () => {
                await navigator.clipboard.writeText(encuesta.enlace_publico);
                setCopiado(true);
                setTimeout(() => setCopiado(false), 2000);
              }}
            >
              {copiado ? 'Copiado' : 'Copiar'}
            </Boton>
          </div>
        </div>
      )}
    </Seccion>
  );
}

/* -------------------------------------------------------------------------- */

function Nota({ etiqueta, valor, sobre }: { etiqueta: string; valor: number | null; sobre: number }) {
  return (
    <div>
      <div className="mch-dato__etiqueta">{etiqueta}</div>
      <div className="mch-dato__valor">
        {valor === null ? '—' : `${valor} / ${sobre}`}
      </div>
    </div>
  );
}

function Respuestas({ encuesta }: { encuesta: Encuesta }) {
  const recomienda = encuesta.recomendaria ?? 0;

  return (
    <>
      <div className="mch-datos">
        <Nota etiqueta="Atención" valor={encuesta.puntaje_atencion} sobre={5} />
        <Nota etiqueta="Tiempo" valor={encuesta.puntaje_tiempo} sobre={5} />
        <Nota etiqueta="Calidad del trabajo" valor={encuesta.puntaje_calidad} sobre={5} />
        <div>
          <div className="mch-dato__etiqueta">Nos recomendaría</div>
          <div className="mch-dato__valor">
            {encuesta.recomendaria === null ? (
              '—'
            ) : (
              <>
                {encuesta.recomendaria} / 10{' '}
                <Distintivo tono={recomienda >= 9 ? 'activo' : recomienda >= 7 ? 'neutro' : 'inactivo'}>
                  {recomienda >= 9 ? 'Promotor' : recomienda >= 7 ? 'Pasivo' : 'Detractor'}
                </Distintivo>
              </>
            )}
          </div>
        </div>
      </div>

      {encuesta.comentario && (
        <div
          style={{
            borderTop: '1px solid var(--mch-borde)',
            padding: 'var(--mch-esp-4) var(--mch-esp-5)',
          }}
        >
          <div className="mch-bitacora__comentario">{encuesta.comentario}</div>
        </div>
      )}
    </>
  );
}
