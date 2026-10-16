import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Aviso, Boton, Campo, Cargando, Seccion } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { formatearFecha, formatearMoneda } from '@/lib/formato';
import { useSesion } from '@/app/sesion';
import { CLAVE_TALLER, editarTaller, obtenerTaller, type DatosTaller, type Taller } from './api';

/**
 * Configuración del taller.
 *
 * Es la pantalla que le da sentido al resto: la tarifa por hora, el impuesto y
 * los días de validez son los números con los que el sistema calcula cuando
 * quien registra una línea o emite un presupuesto no indica otra cosa, y hasta
 * ahora solo se podían poner por SQL.
 *
 * Quien no administra también la ve, pero sin poder editarla. Bloquearla del
 * todo sería esconder datos que su rol puede leer —y que necesita: el técnico
 * mira la tarifa para entender el subtotal que le sale en pantalla.
 */
export function PaginaTaller() {
  const { claims } = useSesion();
  const clienteQuery = useQueryClient();

  const [error, setError] = useState<string | null>(null);
  const [guardado, setGuardado] = useState(false);

  const consulta = useQuery({ queryKey: CLAVE_TALLER, queryFn: obtenerTaller });

  const mutacion = useMutation({
    mutationFn: editarTaller,
    onSuccess: (taller) => {
      // Se escribe la respuesta en la caché en vez de invalidar: `Layout` lee
      // la misma clave para la moneda, y así el símbolo cambia en el acto.
      clienteQuery.setQueryData(CLAVE_TALLER, taller);
      setError(null);
      setGuardado(true);
    },
    onError: (e) => {
      setGuardado(false);
      setError(e instanceof ErrorApi ? e.message : 'No se pudo guardar la configuración.');
    },
  });

  if (consulta.isLoading) return <Cargando texto="Cargando la configuración…" />;

  if (consulta.isError || !consulta.data) {
    return (
      <Aviso tono="error">
        {consulta.error instanceof ErrorApi
          ? consulta.error.message
          : 'No se pudo leer la configuración del taller.'}
      </Aviso>
    );
  }

  const t = consulta.data;
  const puedeEditar = claims?.rol === 'admin_taller';

  function alEnviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const texto = (campo: string) => String(f.get(campo) ?? '').trim();
    // Un campo de contacto vacío se manda en null a propósito: vaciarlo es
    // querer borrarlo, no guardar una cadena vacía que luego se imprime como un
    // hueco en el presupuesto del cliente.
    const opcional = (campo: string) => texto(campo) || null;

    const datos: DatosTaller = {
      nombre: texto('nombre'),
      identificacion_fiscal: opcional('identificacion_fiscal'),
      telefono: opcional('telefono'),
      email: opcional('email'),
      direccion: opcional('direccion'),
      moneda: texto('moneda').toUpperCase(),
      tarifa_hora_default: Number(texto('tarifa_hora_default')),
      impuesto_pct: Number(texto('impuesto_pct')),
      prefijo_orden: texto('prefijo_orden').toUpperCase(),
      dias_validez_presupuesto: Number(texto('dias_validez_presupuesto')),
    };

    setGuardado(false);
    mutacion.mutate(datos);
  }

  return (
    <>
      <header style={{ marginBottom: 'var(--mch-esp-6)' }}>
        <h1 style={{ fontSize: 'var(--mch-txt-xl)' }}>Configuración</h1>
        <p
          style={{
            margin: 'var(--mch-esp-1) 0 0',
            color: 'var(--mch-texto-secundario)',
            fontSize: 'var(--mch-txt-sm)',
          }}
        >
          Los datos del taller y los números con los que el sistema calcula.
        </p>
      </header>

      {!puedeEditar && (
        <div style={{ marginBottom: 'var(--mch-esp-4)' }}>
          <Aviso tono="info">
            Esto lo cambia quien administra el taller. Aquí lo puedes consultar, que es lo que
            explica la tarifa y el impuesto que ves aplicados en las órdenes.
          </Aviso>
        </div>
      )}

      {error && (
        <div style={{ marginBottom: 'var(--mch-esp-4)' }}>
          <Aviso tono="error">{error}</Aviso>
        </div>
      )}

      {guardado && (
        <div style={{ marginBottom: 'var(--mch-esp-4)' }}>
          <Aviso tono="info">
            Configuración guardada. Vale para lo que se registre de ahora en adelante: las líneas
            de mano de obra y los presupuestos ya emitidos conservan los números con los que se
            crearon.
          </Aviso>
        </div>
      )}

      {puedeEditar ? (
        <form onSubmit={alEnviar} style={{ display: 'grid', gap: 'var(--mch-esp-5)' }}>
          <Formulario taller={t} />
          <div style={{ display: 'flex', gap: 'var(--mch-esp-3)', alignItems: 'center' }}>
            <Boton type="submit" cargando={mutacion.isPending}>
              Guardar
            </Boton>
            <span style={{ fontSize: 'var(--mch-txt-xs)', color: 'var(--mch-texto-secundario)' }}>
              Última modificación: {formatearFecha(t.actualizado_en, true)}
            </span>
          </div>
        </form>
      ) : (
        <SoloLectura taller={t} />
      )}

      <p
        style={{
          marginTop: 'var(--mch-esp-5)',
          fontSize: 'var(--mch-txt-xs)',
          color: 'var(--mch-texto-secundario)',
        }}
      >
        Identificador del taller: <code>{t.slug}</code> · zona horaria {t.zona_horaria}. Ninguno de
        los dos se cambia desde aquí.
      </p>
    </>
  );
}

/** Los campos editables, agrupados por para qué sirve cada grupo. */
function Formulario({ taller: t }: { taller: Taller }) {
  return (
    <>
      <Seccion titulo="Identidad" resumen="Con lo que se le nombra al taller dentro del sistema.">
        <div className="mch-formulario">
          <Campo
            etiqueta="Nombre"
            name="nombre"
            required
            minLength={2}
            maxLength={120}
            defaultValue={t.nombre}
          />
          <Campo
            etiqueta="Identificación fiscal"
            name="identificacion_fiscal"
            maxLength={40}
            ayuda="RIF, NIT o lo que corresponda"
            defaultValue={t.identificacion_fiscal ?? ''}
          />
        </div>
      </Seccion>

      <Seccion
        titulo="Contacto"
        resumen="Esto es lo que ve el cliente en el presupuesto que recibe por enlace."
      >
        <div className="mch-formulario">
          <Campo
            etiqueta="Teléfono"
            name="telefono"
            maxLength={40}
            ayuda="A este número llama quien tenga dudas"
            defaultValue={t.telefono ?? ''}
          />
          <Campo
            etiqueta="Correo"
            name="email"
            type="email"
            defaultValue={t.email ?? ''}
          />
          <div className="mch-formulario__ancho">
            <Campo
              etiqueta="Dirección"
              name="direccion"
              maxLength={500}
              defaultValue={t.direccion ?? ''}
            />
          </div>
        </div>
      </Seccion>

      <Seccion
        titulo="Dinero"
        resumen="Lo que el sistema aplica cuando quien registra algo no indica otra cosa."
      >
        <div className="mch-formulario">
          <Campo
            etiqueta="Moneda"
            name="moneda"
            required
            pattern="[A-Za-z]{3}"
            maxLength={3}
            ayuda="Código de tres letras: USD, EUR, VES…"
            defaultValue={t.moneda}
            style={{ textTransform: 'uppercase' }}
          />
          <Campo
            etiqueta="Tarifa por hora"
            name="tarifa_hora_default"
            type="number"
            step="0.01"
            min="0"
            required
            ayuda="Cada línea de mano de obra la congela al crearse"
            defaultValue={t.tarifa_hora_default}
          />
          <Campo
            etiqueta="Impuesto (%)"
            name="impuesto_pct"
            type="number"
            step="0.01"
            min="0"
            max="100"
            required
            ayuda="0 si el taller está exento"
            defaultValue={t.impuesto_pct}
          />
        </div>
      </Seccion>

      <Seccion titulo="Operación" resumen="Cómo se numeran las órdenes y cuánto dura una oferta.">
        <div className="mch-formulario">
          <Campo
            etiqueta="Prefijo de folio"
            name="prefijo_orden"
            required
            pattern="[A-Za-z0-9]{2,6}"
            maxLength={6}
            ayuda="De 2 a 6 letras o números. Las órdenes ya emitidas conservan su folio."
            defaultValue={t.prefijo_orden}
            style={{ textTransform: 'uppercase' }}
          />
          <Campo
            etiqueta="Validez del presupuesto (días)"
            name="dias_validez_presupuesto"
            type="number"
            min="1"
            max="365"
            required
            ayuda="Pasados estos días el presupuesto vence y el cliente ya no puede aprobarlo"
            defaultValue={t.dias_validez_presupuesto}
          />
        </div>
      </Seccion>
    </>
  );
}

/** Lo mismo para quien no administra: los datos, sin controles. */
function SoloLectura({ taller: t }: { taller: Taller }) {
  const datos: [string, string][] = [
    ['Nombre', t.nombre],
    ['Identificación fiscal', t.identificacion_fiscal ?? '—'],
    ['Teléfono', t.telefono ?? '—'],
    ['Correo', t.email ?? '—'],
    ['Dirección', t.direccion ?? '—'],
    ['Moneda', t.moneda],
    ['Tarifa por hora', formatearMoneda(t.tarifa_hora_default, t.moneda)],
    ['Impuesto', `${t.impuesto_pct}%`],
    ['Prefijo de folio', t.prefijo_orden],
    ['Validez del presupuesto', `${t.dias_validez_presupuesto} días`],
  ];

  return (
    <div className="mch-panel">
      <div className="mch-datos">
        {datos.map(([etiqueta, valor]) => (
          <div key={etiqueta}>
            <div className="mch-dato__etiqueta">{etiqueta}</div>
            <div className="mch-dato__valor">{valor}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
