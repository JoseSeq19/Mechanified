/**
 * La orden de servicio en papel.
 *
 * Un taller necesita entregar algo: el resguardo que firma el cliente al dejar
 * el vehículo y el desglose que se lleva al recogerlo. Hasta ahora todo vivía
 * en pantalla, así que la única forma de dar un comprobante era imprimir una
 * captura con la barra lateral incluida.
 *
 * Va fuera del armazón de la aplicación —sin barra, sin navegación— porque es
 * un documento, no una pantalla. Los datos del encabezado son los que el taller
 * configuró en Configuración: si no los ha puesto, el documento sale sin
 * dirección ni teléfono, y eso se ve, que es la mejor forma de que alguien los
 * ponga.
 */
import { useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { Aviso, Boton, Cargando } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { formatearFecha, formatearMoneda, formatearNumero } from '@/lib/formato';
import { listarDiagnosticos, listarManoObra } from '@/features/diagnosticos/api';
import { listarItems } from '@/features/repuestos/api';
import { CLAVE_TALLER, obtenerTaller } from '@/features/taller/api';
import { ETIQUETA } from './estados';
import { inventarioTexto, obtenerOrden } from './api';

export function PaginaOrdenImpresa() {
  const { ordenId = '' } = useParams();

  const orden = useQuery({ queryKey: ['orden', ordenId], queryFn: () => obtenerOrden(ordenId) });
  const taller = useQuery({ queryKey: CLAVE_TALLER, queryFn: obtenerTaller });
  const diagnosticos = useQuery({
    queryKey: ['orden', ordenId, 'diagnosticos'],
    queryFn: () => listarDiagnosticos(ordenId),
  });
  const manoObra = useQuery({
    queryKey: ['orden', ordenId, 'mano-obra'],
    queryFn: () => listarManoObra(ordenId),
  });
  const repuestos = useQuery({
    queryKey: ['orden', ordenId, 'repuestos'],
    queryFn: () => listarItems(ordenId),
  });

  const cargando =
    orden.isLoading ||
    taller.isLoading ||
    diagnosticos.isLoading ||
    manoObra.isLoading ||
    repuestos.isLoading;

  // El título de la ventana es el nombre que propone el navegador al guardar
  // como PDF, así que vale la pena que sea el folio y no "Grupo La Meseta".
  useEffect(() => {
    const anterior = document.title;
    if (orden.data) document.title = `${orden.data.folio} · ${orden.data.vehiculo_placa}`;
    return () => {
      document.title = anterior;
    };
  }, [orden.data]);

  if (cargando) return <Cargando texto="Preparando el documento…" />;

  if (orden.isError || !orden.data) {
    return (
      <div style={{ padding: 'var(--mch-esp-6)' }}>
        <Aviso tono="error">
          {orden.error instanceof ErrorApi ? orden.error.message : 'No se encontró la orden.'}
        </Aviso>
        <p style={{ marginTop: 'var(--mch-esp-4)' }}>
          <Link to="/ordenes">← Volver al tablero</Link>
        </p>
      </div>
    );
  }

  const o = orden.data;
  const t = taller.data;
  const lineasTrabajo = manoObra.data?.lineas ?? [];
  const lineasPiezas = repuestos.data?.lineas ?? [];
  const hallazgos = (diagnosticos.data ?? []).flatMap((d) => d.hallazgos);
  const inventario = Object.entries(inventarioTexto(o.inventario_ingreso));

  return (
    <div className="mch-documento">
      <div className="mch-documento__barra">
        <Link to={`/ordenes/${ordenId}`}>← Volver a la orden</Link>
        <Boton onClick={() => window.print()}>Imprimir</Boton>
      </div>

      <article className="mch-hoja">
        <header className="mch-hoja__cabecera">
          <div>
            <h1 className="mch-hoja__taller">{t?.nombre ?? 'Taller'}</h1>
            <p className="mch-hoja__contacto">
              {[t?.identificacion_fiscal, t?.direccion, t?.telefono, t?.email]
                .filter(Boolean)
                .join(' · ') || 'Completa los datos del taller en Configuración.'}
            </p>
          </div>
          <div className="mch-hoja__folio">
            <span className="mch-hoja__folio-numero">{o.folio}</span>
            <span>Orden de servicio</span>
            <span>{ETIQUETA[o.estado]}</span>
          </div>
        </header>

        <section className="mch-hoja__rejilla">
          <Dato etiqueta="Cliente" valor={o.cliente_nombre} />
          <Dato etiqueta="Vehículo" valor={`${o.vehiculo_placa} · ${o.vehiculo_descripcion}`} />
          <Dato
            etiqueta="Kilometraje de ingreso"
            valor={o.kilometraje_ingreso?.toLocaleString('es') ?? '—'}
          />
          <Dato
            etiqueta="Combustible"
            valor={o.nivel_combustible !== null ? `${o.nivel_combustible}%` : '—'}
          />
          <Dato etiqueta="Ingreso" valor={formatearFecha(o.fecha_ingreso, true)} />
          <Dato etiqueta="Fecha prometida" valor={formatearFecha(o.fecha_promesa, true)} />
          <Dato etiqueta="Entrega" valor={formatearFecha(o.fecha_entrega, true)} />
          <Dato etiqueta="Asesor" valor={o.asesor_nombre ?? 'Sin asignar'} />
          <Dato etiqueta="Técnico" valor={o.tecnico_nombre ?? 'Sin asignar'} />
        </section>

        <Bloque titulo="Motivo de ingreso">
          <p className="mch-hoja__texto">{o.motivo_ingreso}</p>
        </Bloque>

        {/* `inventario_ingreso` es un objeto libre —cada taller inventaría cosas
            distintas— así que se imprime como pares. Hoy solo lo escriben la
            API y el móvil; la web todavía no lo captura. */}
        {inventario.length > 0 && (
          <Bloque titulo="Inventario recibido con el vehículo">
            <table className="mch-hoja__tabla">
              <tbody>
                {inventario.map(([clave, valor]) => (
                  <tr key={clave}>
                    <td>{clave}</td>
                    <td>{valor}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Bloque>
        )}

        {hallazgos.length > 0 && (
          <Bloque titulo="Hallazgos del diagnóstico">
            <table className="mch-hoja__tabla">
              <thead>
                <tr>
                  <th>Sistema</th>
                  <th>Hallazgo</th>
                  <th>Severidad</th>
                </tr>
              </thead>
              <tbody>
                {hallazgos.map((h) => (
                  <tr key={h.id}>
                    <td>{h.sistema}</td>
                    <td>{h.descripcion}</td>
                    <td>{h.severidad_etiqueta}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Bloque>
        )}

        {lineasTrabajo.length > 0 && (
          <Bloque titulo="Mano de obra">
            <table className="mch-hoja__tabla">
              <thead>
                <tr>
                  <th>Trabajo</th>
                  <th className="mch-hoja__num">Horas</th>
                  <th className="mch-hoja__num">Tarifa</th>
                  <th className="mch-hoja__num">Importe</th>
                </tr>
              </thead>
              <tbody>
                {lineasTrabajo.map((l) => (
                  <tr key={l.id}>
                    <td>{l.descripcion}</td>
                    <td className="mch-hoja__num">{formatearNumero(l.horas)}</td>
                    <td className="mch-hoja__num">{formatearMoneda(l.tarifa_hora)}</td>
                    <td className="mch-hoja__num">{formatearMoneda(l.subtotal)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Bloque>
        )}

        {lineasPiezas.length > 0 && (
          <Bloque titulo="Repuestos y materiales">
            <table className="mch-hoja__tabla">
              <thead>
                <tr>
                  <th>Pieza</th>
                  <th className="mch-hoja__num">Cantidad</th>
                  <th className="mch-hoja__num">Precio</th>
                  <th className="mch-hoja__num">Importe</th>
                </tr>
              </thead>
              <tbody>
                {lineasPiezas.map((l) => (
                  <tr key={l.id}>
                    <td>
                      {l.descripcion}
                      {l.sku && <span className="mch-hoja__sku"> ({l.sku})</span>}
                    </td>
                    <td className="mch-hoja__num">{formatearNumero(l.cantidad)}</td>
                    <td className="mch-hoja__num">{formatearMoneda(l.precio_unitario)}</td>
                    <td className="mch-hoja__num">{formatearMoneda(l.subtotal)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Bloque>
        )}

        <section className="mch-hoja__totales">
          <div>
            <span>Mano de obra</span>
            <span>{formatearMoneda(o.total_mano_obra)}</span>
          </div>
          <div>
            <span>Repuestos</span>
            <span>{formatearMoneda(o.total_repuestos)}</span>
          </div>
          <div className="mch-hoja__total">
            <span>Total</span>
            <span>{formatearMoneda(o.total)}</span>
          </div>
          {Number(t?.impuesto_pct ?? 0) > 0 && (
            <p className="mch-hoja__aviso-impuesto">
              Los importes no incluyen el {t?.impuesto_pct}% de impuesto, que se aplica al emitir
              el presupuesto.
            </p>
          )}
        </section>

        {o.motivo_cancelacion && (
          <Bloque titulo="Orden cancelada">
            <p className="mch-hoja__texto">{o.motivo_cancelacion}</p>
          </Bloque>
        )}

        {/* Las notas internas no se imprimen: son del taller, y este papel se
            lo lleva el cliente. */}

        <section className="mch-hoja__firmas">
          <div>
            <span className="mch-hoja__linea-firma" />
            <span>Por el taller</span>
          </div>
          <div>
            <span className="mch-hoja__linea-firma" />
            <span>Recibí conforme · {o.cliente_nombre}</span>
          </div>
        </section>

        <footer className="mch-hoja__pie">
          Documento generado el {formatearFecha(new Date().toISOString(), true)} · {o.folio}
        </footer>
      </article>
    </div>
  );
}

function Dato({ etiqueta, valor }: { etiqueta: string; valor: string }) {
  return (
    <div>
      <span className="mch-hoja__etiqueta">{etiqueta}</span>
      <span className="mch-hoja__valor">{valor}</span>
    </div>
  );
}

function Bloque({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="mch-hoja__bloque">
      <h2 className="mch-hoja__titulo">{titulo}</h2>
      {children}
    </section>
  );
}
