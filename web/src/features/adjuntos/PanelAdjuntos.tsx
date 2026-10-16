import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Aviso, Boton, Campo, Cargando, Distintivo, Seccion, Vacio } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { formatearFecha } from '@/lib/formato';
import { useSesion } from '@/app/sesion';
import {
  ETIQUETA_CONTEXTO,
  MIMES_PERMITIDOS,
  borrarAdjunto,
  listarAdjuntos,
  revisarArchivo,
  subirAdjunto,
  urlsFirmadas,
  type Adjunto,
  type ContextoAdjunto,
} from './api';

/** Los momentos de la orden, en el orden en que ocurren. */
const CONTEXTOS: ContextoAdjunto[] = [
  'ingreso',
  'diagnostico',
  'reparacion',
  'calidad',
  'entrega',
];

function tamanoLegible(bytes: number | null): string {
  if (!bytes) return '';
  const mb = bytes / 1_048_576;
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/**
 * Fotos y archivos de la orden.
 *
 * Es la constancia del estado del vehículo: lo que el taller puede poner sobre
 * la mesa cuando alguien dice que el golpe del parachoques no estaba al
 * entregarlo. Por eso cada archivo lleva el momento al que pertenece y se sigue
 * pudiendo subir con la orden ya entregada.
 *
 * El archivo viaja del navegador al bucket sin pasar por la API; ver el
 * docstring de `api.ts`.
 */
export function PanelAdjuntos({ ordenId }: { ordenId: string }) {
  const { claims } = useSesion();
  const clienteQuery = useQueryClient();
  const entrada = useRef<HTMLInputElement>(null);

  const [contexto, setContexto] = useState<ContextoAdjunto>('ingreso');
  // Se escribe antes de elegir el archivo y vale para lo que se suba en esa
  // tanda. Es lo que convierte doce fotos iguales en doce fotos que dicen algo.
  const [nota, setNota] = useState('');
  const [error, setError] = useState<string | null>(null);

  const consulta = useQuery({
    queryKey: ['orden', ordenId, 'adjuntos'],
    queryFn: () => listarAdjuntos(ordenId),
  });

  const adjuntos = consulta.data ?? [];
  const rutas = adjuntos.map((a) => a.ruta_storage);

  // Las URLs firmadas caducan, así que se piden aparte de los metadatos y se
  // vuelven a pedir cuando cambia la lista de archivos.
  const urls = useQuery({
    queryKey: ['orden', ordenId, 'adjuntos', 'urls', rutas.join('|')],
    queryFn: () => urlsFirmadas(rutas),
    enabled: rutas.length > 0,
    staleTime: 5 * 60_000,
  });

  const refrescar = () =>
    clienteQuery.invalidateQueries({ queryKey: ['orden', ordenId, 'adjuntos'] });

  const mutSubir = useMutation({
    mutationFn: async ({ archivos, tallerId }: { archivos: File[]; tallerId: string }) => {
      // En serie y no en paralelo: son fotos de varios MB desde el móvil del
      // técnico, y varias subidas simultáneas en la red de un taller se
      // estorban entre ellas más de lo que se adelantan.
      for (const archivo of archivos) {
        await subirAdjunto({ tallerId, ordenId, archivo, contexto, descripcion: nota });
      }
    },
    onSuccess: () => {
      setError(null);
      setNota('');
      refrescar();
    },
    onError: (e) =>
      setError(e instanceof ErrorApi || e instanceof Error ? e.message : 'No se pudo subir.'),
  });

  const mutBorrar = useMutation({
    mutationFn: borrarAdjunto,
    onSuccess: () => {
      setError(null);
      refrescar();
    },
    onError: (e) =>
      setError(
        e instanceof ErrorApi ? e.message : 'No se pudo quitar el archivo de la orden.',
      ),
  });

  function alElegir(archivos: FileList | null) {
    if (!archivos || archivos.length === 0) return;

    const tallerId = claims?.taller_id;
    const lista = Array.from(archivos);
    const problemas = lista.map(revisarArchivo).filter((m): m is string => m !== null);

    if (!tallerId) {
      // La primera carpeta de la ruta es el taller: sin ese dato no hay dónde
      // subir nada, y el aviso de la cabecera ya explica por qué falta.
      setError('Tu sesión no trae taller asignado, así que no se puede subir nada.');
    } else if (problemas.length > 0) {
      setError(problemas.join(' '));
    } else {
      mutSubir.mutate({ archivos: lista, tallerId });
    }

    // Se limpia para que elegir el mismo archivo otra vez vuelva a disparar el
    // evento; sin esto, un segundo intento tras un error no haría nada.
    if (entrada.current) entrada.current.value = '';
  }

  const porContexto = CONTEXTOS.map((c) => ({
    contexto: c,
    archivos: adjuntos.filter((a) => a.contexto === c),
  })).filter((grupo) => grupo.archivos.length > 0);

  return (
    <Seccion
      titulo="Fotos y archivos"
      resumen={
        adjuntos.length > 0
          ? `${adjuntos.length} ${adjuntos.length === 1 ? 'archivo' : 'archivos'} · la constancia del estado del vehículo`
          : 'Fotos del vehículo, del hallazgo o de la entrega.'
      }
      accion={
        <div style={{ display: 'flex', gap: 'var(--mch-esp-2)', alignItems: 'center' }}>
          <select
            className="mch-campo__control"
            style={{ width: 'auto' }}
            value={contexto}
            onChange={(e) => setContexto(e.target.value as ContextoAdjunto)}
            aria-label="Momento al que pertenece el archivo"
          >
            {CONTEXTOS.map((c) => (
              <option key={c} value={c}>
                {ETIQUETA_CONTEXTO[c]}
              </option>
            ))}
          </select>
          <Boton
            onClick={() => entrada.current?.click()}
            cargando={mutSubir.isPending}
            disabled={!claims?.taller_id}
          >
            {mutSubir.isPending ? 'Subiendo…' : 'Añadir'}
          </Boton>
        </div>
      }
    >
      <input
        ref={entrada}
        type="file"
        hidden
        multiple
        accept={MIMES_PERMITIDOS.join(',')}
        onChange={(e) => alElegir(e.target.files)}
      />

      <div style={{ padding: 'var(--mch-esp-4) var(--mch-esp-5) 0' }}>
        <Campo
          etiqueta="Nota para lo que subas ahora"
          ayuda="Opcional. Queda junto al archivo: «golpe lateral derecho», «factura de la bomba»."
          maxLength={500}
          value={nota}
          onChange={(e) => setNota(e.target.value)}
        />
      </div>

      {error && (
        <div style={{ padding: 'var(--mch-esp-4) var(--mch-esp-5) 0' }}>
          <Aviso tono="alerta">{error}</Aviso>
        </div>
      )}

      {consulta.isLoading ? (
        <Cargando texto="" />
      ) : adjuntos.length === 0 ? (
        <Vacio
          titulo="Sin archivos"
          detalle="Las fotos de recepción son lo que respalda al taller si después hay una discusión por un golpe."
        />
      ) : (
        porContexto.map(({ contexto: c, archivos }) => (
          <div key={c} className="mch-galeria__grupo">
            <div className="mch-dato__etiqueta">{ETIQUETA_CONTEXTO[c]}</div>
            <div className="mch-galeria">
              {archivos.map((a) => (
                <Ficha
                  key={a.id}
                  adjunto={a}
                  url={urls.data?.[a.ruta_storage]}
                  cargandoUrl={urls.isLoading}
                  borrando={mutBorrar.isPending}
                  onBorrar={() => mutBorrar.mutate(a)}
                />
              ))}
            </div>
          </div>
        ))
      )}

      {urls.isError && (
        <div style={{ padding: '0 var(--mch-esp-5) var(--mch-esp-4)' }}>
          <Aviso tono="alerta">
            Los archivos están registrados, pero no se pudieron abrir sus enlaces temporales.
          </Aviso>
        </div>
      )}
    </Seccion>
  );
}

function Ficha({
  adjunto: a,
  url,
  cargandoUrl,
  borrando,
  onBorrar,
}: {
  adjunto: Adjunto;
  url: string | undefined;
  cargandoUrl: boolean;
  borrando: boolean;
  onBorrar: () => void;
}) {
  const esImagen = (a.mime ?? '').startsWith('image/');

  return (
    <figure className="mch-galeria__ficha">
      {url ? (
        <a href={url} target="_blank" rel="noreferrer" title={`Abrir ${a.nombre_archivo}`}>
          {esImagen ? (
            <img src={url} alt={a.descripcion ?? a.nombre_archivo} loading="lazy" />
          ) : (
            <span className="mch-galeria__documento">PDF</span>
          )}
        </a>
      ) : (
        <span className="mch-galeria__documento">{cargandoUrl ? '…' : '—'}</span>
      )}

      <figcaption>
        <span className="mch-galeria__nombre" title={a.nombre_archivo}>
          {a.nombre_archivo}
        </span>
        <span className="mch-galeria__meta">
          {a.autor_nombre ?? 'Autor dado de baja'} · {formatearFecha(a.creado_en)}
          {a.tamano_bytes ? ` · ${tamanoLegible(a.tamano_bytes)}` : ''}
        </span>
        {a.descripcion && <span className="mch-galeria__meta">{a.descripcion}</span>}
        {a.puede_borrar ? (
          <Boton variante="fantasma" onClick={onBorrar} disabled={borrando}>
            Quitar
          </Boton>
        ) : (
          <Distintivo tono="neutro">De otra persona</Distintivo>
        )}
      </figcaption>
    </figure>
  );
}
