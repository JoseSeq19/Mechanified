/**
 * La encuesta tal como la ve el cliente, desde el enlace que le mandaron.
 *
 * Igual que el presupuesto público: sin sesión, sin barra lateral, en una
 * columna y con objetivos de toque grandes, porque esto se abre desde el móvil
 * mientras se hace otra cosa.
 *
 * Se responde entera o no se responde: cuatro notas a medias no se pueden
 * promediar con las del resto sin falsear la media del taller.
 */
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Aviso, Boton, Campo, Cargando, Marca } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { formatearFecha } from '@/lib/formato';
import { responderEncuestaPublica, verEncuestaPublica } from './api';

export function PaginaEncuestaPublica() {
  const { token = '' } = useParams();
  const clienteQuery = useQueryClient();

  const [atencion, setAtencion] = useState<number | null>(null);
  const [tiempo, setTiempo] = useState<number | null>(null);
  const [calidad, setCalidad] = useState<number | null>(null);
  const [recomendaria, setRecomendaria] = useState<number | null>(null);
  const [comentario, setComentario] = useState('');
  const [error, setError] = useState<string | null>(null);

  const consulta = useQuery({
    queryKey: ['encuesta-publica', token],
    queryFn: () => verEncuestaPublica(token),
    retry: false,
  });

  const responder = useMutation({
    mutationFn: () =>
      responderEncuestaPublica(token, {
        puntaje_atencion: atencion!,
        puntaje_tiempo: tiempo!,
        puntaje_calidad: calidad!,
        recomendaria: recomendaria!,
        comentario: comentario.trim() || null,
      }),
    onSuccess: () => {
      setError(null);
      clienteQuery.invalidateQueries({ queryKey: ['encuesta-publica', token] });
    },
    onError: (e) =>
      setError(
        e instanceof ErrorApi ? e.message : 'No se pudo enviar tu respuesta. Inténtalo de nuevo.',
      ),
  });

  if (consulta.isLoading) {
    return (
      <main className="mch-publico">
        <Cargando texto="Abriendo la encuesta…" />
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

  const e = consulta.data;
  const completa =
    atencion !== null && tiempo !== null && calidad !== null && recomendaria !== null;

  return (
    <main className="mch-publico">
      <div className="mch-publico__tarjeta">
        <header className="mch-publico__cabecera">
          <div>
            <div className="mch-publico__taller">{e.taller_nombre}</div>
            {e.taller_telefono && (
              <a className="mch-publico__telefono" href={`tel:${e.taller_telefono}`}>
                {e.taller_telefono}
              </a>
            )}
          </div>
          <div className="mch-publico__folio">
            {e.folio_orden}
            {e.fecha_entrega && <span>entregado el {formatearFecha(e.fecha_entrega)}</span>}
          </div>
        </header>

        <section className="mch-publico__vehiculo">
          <strong>{e.placa}</strong> · {e.vehiculo}
        </section>

        {e.respondida ? (
          <section className="mch-publico__acciones">
            <Aviso tono="info">
              Gracias por responder el {formatearFecha(e.respondida_en)}. Tu opinión ya está con
              el taller.
            </Aviso>
            <div className="mch-escala__resumen">
              <span>Atención: {e.puntaje_atencion} / 5</span>
              <span>Tiempo: {e.puntaje_tiempo} / 5</span>
              <span>Calidad: {e.puntaje_calidad} / 5</span>
              <span>Recomendarías: {e.recomendaria} / 10</span>
            </div>
            {e.comentario && <p className="mch-publico__nota">Escribiste: «{e.comentario}»</p>}
          </section>
        ) : (
          <section className="mch-publico__acciones">
            {error && <Aviso tono="error">{error}</Aviso>}

            <p style={{ margin: 0, fontSize: 'var(--mch-txt-sm)' }}>
              Son cuatro preguntas y se responde en menos de un minuto. Lo lee el taller, no una
              agencia.
            </p>

            <Escala
              etiqueta="¿Cómo te atendieron?"
              extremos={['Mal', 'Excelente']}
              valor={atencion}
              onCambio={setAtencion}
            />
            <Escala
              etiqueta="¿Qué tal el tiempo que tardaron?"
              extremos={['Lento', 'Puntual']}
              valor={tiempo}
              onCambio={setTiempo}
            />
            <Escala
              etiqueta="¿Cómo quedó el trabajo?"
              extremos={['Mal', 'Impecable']}
              valor={calidad}
              onCambio={setCalidad}
            />
            <Escala
              etiqueta="¿Nos recomendarías a alguien?"
              extremos={['Para nada', 'Sin dudarlo']}
              desde={0}
              hasta={10}
              valor={recomendaria}
              onCambio={setRecomendaria}
            />

            <Campo
              etiqueta="¿Algo que contarnos? (opcional)"
              value={comentario}
              onChange={(ev) => setComentario(ev.target.value)}
            />

            <div className="mch-publico__botones">
              <Boton
                disabled={!completa}
                cargando={responder.isPending}
                title={completa ? undefined : 'Faltan preguntas por responder'}
                onClick={() => responder.mutate()}
              >
                Enviar mi respuesta
              </Boton>
            </div>
          </section>
        )}
      </div>

      <footer className="mch-publico__pie">
        <Marca compacta />
        <span>Encuesta enviada con Mechanified</span>
      </footer>
    </main>
  );
}

/* -------------------------------------------------------------------------- */

/**
 * Escala de notas con los extremos escritos.
 *
 * Números a secas dejan la duda de si 1 es lo mejor o lo peor, y esa duda
 * convierte la respuesta en ruido. Botones y no un desplegable porque esto se
 * contesta con el pulgar.
 */
function Escala({
  etiqueta,
  extremos,
  valor,
  onCambio,
  desde = 1,
  hasta = 5,
}: {
  etiqueta: string;
  extremos: [string, string];
  valor: number | null;
  onCambio: (n: number) => void;
  desde?: number;
  hasta?: number;
}) {
  const opciones = Array.from({ length: hasta - desde + 1 }, (_, i) => desde + i);

  return (
    <fieldset className="mch-escala">
      <legend className="mch-escala__titulo">{etiqueta}</legend>
      <div className="mch-escala__opciones">
        {opciones.map((n) => (
          <button
            key={n}
            type="button"
            aria-pressed={valor === n}
            aria-label={`${n} de ${hasta}`}
            className={`mch-escala__boton${valor === n ? ' mch-escala__boton--activo' : ''}`}
            onClick={() => onCambio(n)}
          >
            {n}
          </button>
        ))}
      </div>
      <div className="mch-escala__extremos">
        <span>{extremos[0]}</span>
        <span>{extremos[1]}</span>
      </div>
    </fieldset>
  );
}
