/**
 * Incorporación de una cuenta que todavía no pertenece a ninguna organización.
 *
 * Dos caminos, y quien llega elige:
 *
 *   - **Crearla ahora.** Funda la organización con su primera sede y queda
 *     como su administrador. Es inmediato.
 *   - **Que la cree el equipo.** Deja una solicitud; el equipo de Mechanified
 *     la atiende y contesta al correo de la cuenta. Es para quien tiene varias
 *     sedes, datos que migrar, o simplemente prefiere que lo acompañen.
 *
 * Se usa en dos sitios: en el portal web (`/cuenta`) y en la aplicación de
 * escritorio, cuando alguien entra con una cuenta sin organización. Es el
 * mismo formulario en los dos porque es la misma operación.
 */
import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';

import { Aviso, Boton, Campo, Selector } from '@/components/ui';
import { formatearFecha } from '@/lib/formato';
import { ErrorApi } from '@/lib/api';
import {
  crearOrganizacion,
  solicitarOrganizacion,
  type EstadoCuenta,
} from './api';

/**
 * Las monedas de la región, primero. Cualquier otra se puede poner después en
 * Configuración; aquí basta con no empezar con una equivocada.
 */
const MONEDAS = [
  { valor: 'USD', texto: 'USD · dólar' },
  { valor: 'EUR', texto: 'EUR · euro' },
  { valor: 'MXN', texto: 'MXN · peso mexicano' },
  { valor: 'COP', texto: 'COP · peso colombiano' },
  { valor: 'VES', texto: 'VES · bolívar' },
  { valor: 'PEN', texto: 'PEN · sol' },
  { valor: 'CLP', texto: 'CLP · peso chileno' },
  { valor: 'ARS', texto: 'ARS · peso argentino' },
  { valor: 'GTQ', texto: 'GTQ · quetzal' },
  { valor: 'CRC', texto: 'CRC · colón' },
  { valor: 'DOP', texto: 'DOP · peso dominicano' },
  { valor: 'BOB', texto: 'BOB · boliviano' },
  { valor: 'UYU', texto: 'UYU · peso uruguayo' },
  { valor: 'PYG', texto: 'PYG · guaraní' },
  { valor: 'HNL', texto: 'HNL · lempira' },
  { valor: 'NIO', texto: 'NIO · córdoba' },
  { valor: 'PAB', texto: 'PAB · balboa' },
  { valor: 'BRL', texto: 'BRL · real' },
];

type Camino = 'crear' | 'pedir';

function mensajeDe(error: unknown, porOmision: string): string {
  return error instanceof ErrorApi || error instanceof Error ? error.message : porOmision;
}

export function Incorporacion({
  estado,
  nombreSugerido,
  onCreada,
  onSolicitada,
}: {
  estado: EstadoCuenta;
  /** El nombre con el que se registró, para no pedirlo dos veces. */
  nombreSugerido?: string;
  /** Recibe el estado nuevo, ya con organización. Quien llama renueva la sesión. */
  onCreada: (estado: EstadoCuenta) => void | Promise<void>;
  onSolicitada: (estado: EstadoCuenta) => void;
}) {
  const pendiente = estado.solicitud?.estado === 'pendiente' ? estado.solicitud : null;
  const [camino, setCamino] = useState<Camino | null>(pendiente ? null : 'crear');

  return (
    <div className="mch-incorporacion">
      {pendiente && (
        <div className="mch-incorporacion__pendiente">
          <Aviso tono="info">
            Pediste que el equipo de Mechanified creara <strong>{pendiente.nombre_organizacion}</strong>{' '}
            el {formatearFecha(pendiente.creado_en)}. Te escribiremos a{' '}
            <strong>{estado.email ?? 'tu correo'}</strong> en cuanto esté lista; no tienes que hacer
            nada más.
          </Aviso>
          {camino === null && (
            <button type="button" className="mch-acceso__enlace" onClick={() => setCamino('crear')}>
              ¿Prefieres no esperar? Créala ahora tú
            </button>
          )}
        </div>
      )}

      {!pendiente && (
        <div className="mch-incorporacion__caminos" role="group" aria-label="Cómo crear tu organización">
          <button
            type="button"
            aria-pressed={camino === 'crear'}
            className={`mch-camino${camino === 'crear' ? ' mch-camino--activo' : ''}`}
            onClick={() => setCamino('crear')}
          >
            <span className="mch-camino__titulo">Crearla ahora</span>
            <span className="mch-camino__detalle">Un minuto, y entras como administrador.</span>
          </button>
          <button
            type="button"
            aria-pressed={camino === 'pedir'}
            className={`mch-camino${camino === 'pedir' ? ' mch-camino--activo' : ''}`}
            onClick={() => setCamino('pedir')}
          >
            <span className="mch-camino__titulo">Que la cree el equipo</span>
            <span className="mch-camino__detalle">
              Para varias sedes o si prefieres que te acompañemos.
            </span>
          </button>
        </div>
      )}

      {camino === 'crear' && (
        <FormularioCrear nombreSugerido={nombreSugerido} onCreada={onCreada} />
      )}
      {camino === 'pedir' && !pendiente && (
        <FormularioPedir
          nombreSugerido={nombreSugerido}
          onSolicitada={(nuevo) => {
            // Con la solicitud ya pendiente se vuelve a la vista de espera, que
            // es la que ofrece crearla igualmente sin esperar al equipo.
            setCamino(null);
            onSolicitada(nuevo);
          }}
        />
      )}
    </div>
  );
}

function FormularioCrear({
  nombreSugerido,
  onCreada,
}: {
  nombreSugerido?: string;
  onCreada: (estado: EstadoCuenta) => void | Promise<void>;
}) {
  const crear = useMutation({
    mutationFn: crearOrganizacion,
    onSuccess: async (estado) => {
      // La organización ya existe: lo que venga después —renovar la sesión—
      // no la deshace, y un fallo ahí no debe pintarse como "no se pudo
      // crear". Quien llama muestra su propio estado.
      try {
        await onCreada(estado);
      } catch {
        /* lo resuelve quien llama */
      }
    },
  });

  function alEnviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const texto = (campo: string) => String(f.get(campo) ?? '').trim();
    crear.mutate({
      nombre: texto('nombre'),
      sede: texto('sede') || null,
      nombre_completo: texto('nombre_completo'),
      telefono: texto('telefono') || null,
      moneda: texto('moneda'),
      tarifa_hora_default: Number(texto('tarifa') || 0),
      impuesto_pct: Number(texto('impuesto') || 0),
    });
  }

  return (
    <form className="mch-panel mch-incorporacion__formulario" onSubmit={alEnviar}>
      <div className="mch-formulario">
        <div className="mch-formulario__ancho">
          <Campo
            etiqueta="Nombre de tu organización"
            name="nombre"
            required
            minLength={2}
            maxLength={120}
            autoFocus
            placeholder="Taller García, Grupo Automotriz del Norte…"
            ayuda="Es el nombre con el que Mechanified se presentará a tu gente."
          />
        </div>
        <Campo
          etiqueta="Primera sede (opcional)"
          name="sede"
          maxLength={120}
          placeholder="Igual que la organización"
          ayuda="Si tienes varias, esta es la primera. Las demás se suman después."
        />
        <Campo
          etiqueta="Tu nombre"
          name="nombre_completo"
          required
          minLength={2}
          maxLength={120}
          defaultValue={nombreSugerido}
          autoComplete="name"
        />
        <Campo etiqueta="Teléfono (opcional)" name="telefono" maxLength={40} autoComplete="tel" />
        <Selector etiqueta="Moneda" name="moneda" defaultValue="USD" opciones={MONEDAS} />
        <Campo
          etiqueta="Tarifa por hora"
          name="tarifa"
          type="number"
          min={0}
          step="0.01"
          defaultValue={0}
          ayuda="De la mano de obra. Se cambia en Configuración."
        />
        <Campo
          etiqueta="Impuesto (%)"
          name="impuesto"
          type="number"
          min={0}
          max={100}
          step="0.01"
          defaultValue={0}
        />
      </div>

      <div className="mch-incorporacion__acciones">
        {crear.isError && (
          <Aviso tono="error">{mensajeDe(crear.error, 'No se pudo crear la organización.')}</Aviso>
        )}
        <Boton type="submit" cargando={crear.isPending}>
          {crear.isPending ? 'Creando…' : 'Crear mi organización'}
        </Boton>
      </div>
    </form>
  );
}

function FormularioPedir({
  nombreSugerido,
  onSolicitada,
}: {
  nombreSugerido?: string;
  onSolicitada: (estado: EstadoCuenta) => void;
}) {
  const pedir = useMutation({
    mutationFn: solicitarOrganizacion,
    onSuccess: (estado) => onSolicitada(estado),
  });

  function alEnviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const texto = (campo: string) => String(f.get(campo) ?? '').trim();
    const sedes = Number(texto('sedes'));
    pedir.mutate({
      nombre_organizacion: texto('nombre_organizacion'),
      nombre_contacto: texto('nombre_contacto'),
      telefono: texto('telefono') || null,
      sedes: sedes > 0 ? sedes : null,
      mensaje: texto('mensaje') || null,
    });
  }

  return (
    <form className="mch-panel mch-incorporacion__formulario" onSubmit={alEnviar}>
      <div className="mch-formulario">
        <div className="mch-formulario__ancho">
          <Campo
            etiqueta="Nombre de tu organización"
            name="nombre_organizacion"
            required
            minLength={2}
            maxLength={120}
            autoFocus
          />
        </div>
        <Campo
          etiqueta="Tu nombre"
          name="nombre_contacto"
          required
          minLength={2}
          maxLength={120}
          defaultValue={nombreSugerido}
          autoComplete="name"
        />
        <Campo etiqueta="Teléfono (opcional)" name="telefono" maxLength={40} autoComplete="tel" />
        <Campo etiqueta="¿Cuántas sedes?" name="sedes" type="number" min={1} max={999} />
        <div className="mch-campo mch-formulario__ancho">
          <label className="mch-campo__etiqueta" htmlFor="mch-solicitud-mensaje">
            Algo que debamos saber (opcional)
          </label>
          <textarea
            id="mch-solicitud-mensaje"
            name="mensaje"
            className="mch-campo__control"
            rows={3}
            maxLength={2000}
            placeholder="Si vienes de otro sistema, cuántas personas lo usarán, cuándo quieres empezar…"
          />
        </div>
      </div>

      <div className="mch-incorporacion__acciones">
        {pedir.isError && (
          <Aviso tono="error">{mensajeDe(pedir.error, 'No se pudo enviar la solicitud.')}</Aviso>
        )}
        <Boton type="submit" cargando={pedir.isPending}>
          {pedir.isPending ? 'Enviando…' : 'Enviar la solicitud'}
        </Boton>
      </div>
    </form>
  );
}
