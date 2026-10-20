/**
 * Presentación de Mechanified.
 *
 * La página cuenta lo que hace el producto siguiendo lo que de verdad hace: el
 * recorrido de una orden de servicio, que es el eje de toda la aplicación, y
 * la forma en que se organiza un cliente con varias sedes. Nada de lo que se
 * describe aquí es una promesa: son las pantallas que ya existen.
 *
 * Las ilustraciones (la orden, el presupuesto en el móvil, la ventana de la
 * aplicación) están dibujadas con HTML y CSS, sin imágenes: llevan datos de
 * ejemplo y se leen igual en cualquier pantalla.
 */
import { useEffect, type ComponentType } from 'react';
import { Link, useLocation } from 'react-router-dom';

import { RUTA_CUENTA, useSesion } from '@/app/sesion';
import { CabeceraSitio, PieSitio } from './CabeceraSitio';
import {
  IconoBarras,
  IconoCandado,
  IconoChip,
  IconoFlecha,
  IconoImpresora,
  IconoPersonas,
  IconoRayo,
  IconoSobre,
  IconoTablero,
  IconoTuerca,
  IconoVisto,
  IconoVistoCirculo,
} from './iconos';

const RECORRIDO = [
  {
    paso: 'Recepción',
    texto:
      'Cliente, vehículo, kilometraje e inventario de lo que trae, con fotos del estado en que llega.',
  },
  {
    paso: 'Diagnóstico',
    texto: 'Hallazgos con su severidad, horas de trabajo y las piezas que hacen falta.',
  },
  {
    paso: 'Presupuesto',
    texto:
      'Le llega al cliente por correo y lo aprueba o rechaza desde su móvil, sin llamadas de ida y vuelta.',
  },
  {
    paso: 'Reparación',
    texto: 'Repuestos pedidos, recibidos e instalados, y el tiempo de cada técnico, en la misma ficha.',
  },
  {
    paso: 'Control de calidad',
    texto: 'Una lista de comprobación propia de tu taller antes de dar el trabajo por bueno.',
  },
  {
    paso: 'Entrega y encuesta',
    texto: 'El aviso de "listo para recoger" y, al entregar, una encuesta de cuatro preguntas.',
  },
];

type Tono = 'azul' | 'orquidea' | 'grafito' | 'esmeralda' | 'ambar' | 'violeta';

const PIEZAS: { titulo: string; texto: string; Icono: ComponentType; tono: Tono }[] = [
  {
    titulo: 'Tablero de órdenes',
    texto: 'Todo lo que está en el taller, por estado, con búsqueda por folio, placa o cliente.',
    Icono: IconoTablero,
    tono: 'azul',
  },
  {
    titulo: 'Repuestos y catálogo',
    texto: 'Precios, existencias y mínimos, y el camino de cada pieza desde que se pide.',
    Icono: IconoTuerca,
    tono: 'grafito',
  },
  {
    titulo: 'Avisos al cliente',
    texto: 'Los correos salen solos en cada momento clave, con el nombre de tu taller como remitente.',
    Icono: IconoSobre,
    tono: 'orquidea',
  },
  {
    titulo: 'Panel de indicadores',
    texto: 'Facturación, ticket medio, productividad por técnico y satisfacción, para quien dirige.',
    Icono: IconoBarras,
    tono: 'esmeralda',
  },
  {
    titulo: 'Papel cuando hace falta',
    texto: 'La orden se imprime con tus datos y dos huecos para firmar; el presupuesto, también.',
    Icono: IconoImpresora,
    tono: 'ambar',
  },
  {
    titulo: 'Personal y permisos',
    texto: 'Administración, asesoría, técnicos y repuestos: cada rol ve y hace lo que le toca.',
    Icono: IconoPersonas,
    tono: 'violeta',
  },
];

const GARANTIAS = [
  {
    titulo: 'Una sede no ve los datos de otra.',
    texto:
      'El aislamiento lo aplica la base de datos en cada consulta, no una pantalla que alguien podría saltarse.',
  },
  {
    titulo: 'Cada persona, con su rol.',
    texto:
      'El técnico no toca precios y repuestos no aprueba presupuestos; administración lo ve todo de su sede.',
  },
  {
    titulo: 'Las fotos, privadas.',
    texto: 'Se guardan en un almacén cerrado y se ven con enlaces que caducan en minutos.',
  },
];

const PASOS = [
  {
    titulo: 'Crea tu cuenta',
    texto: 'Con tu correo. Es la que usarás para entrar en Mechanified.',
  },
  {
    titulo: 'Descarga Mechanified',
    texto: 'El programa para Windows. Se abre en tu navegador y no hay que instalar nada.',
  },
  {
    titulo: 'Crea tu organización',
    texto:
      'Tú mismo, en un minuto, o pídenos que la creemos y te acompañamos en la puesta en marcha.',
  },
];

export function PaginaInicio() {
  const { sesion } = useSesion();
  const { hash } = useLocation();
  const destino = sesion ? RUTA_CUENTA : '/entrar?registro';

  useEffect(() => {
    document.title = 'Mechanified · gestión de talleres mecánicos';
  }, []);

  // Al llegar desde otra página con una sección en la dirección (`/#sedes`):
  // la sección no existía cuando el navegador intentó bajar hasta ella.
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView();
  }, [hash]);

  return (
    <div className="mch-sitio">
      <CabeceraSitio conSecciones />

      <main>
        <section className="mch-sitio-portada">
          <div className="mch-sitio-ancho mch-sitio-portada__contenido">
            <ul className="mch-sitio-portada__insignias">
              <li>
                <IconoVistoCirculo />
                <span>Para un taller solo o un grupo con varias sedes</span>
              </li>
              <li>
                <IconoVistoCirculo />
                <span>
                  Para Windows · <strong>tu primera sede, en un minuto</strong>
                </span>
              </li>
            </ul>
            <h1>El taller en orden, de la recepción a la entrega.</h1>
            <p className="mch-sitio-portada__bajada">
              Mechanified lleva cada vehículo por su camino: fotos al recibirlo, diagnóstico,
              presupuesto que el cliente aprueba desde su móvil, reparación, control de calidad y
              entrega.
            </p>
            <div className="mch-sitio-portada__acciones">
              <Link to={destino} className="mch-boton">
                {sesion ? 'Ir a mi cuenta' : 'Crear cuenta y descargar'}
                <IconoFlecha />
              </Link>
              {!sesion && (
                <Link to="/entrar" className="mch-sitio-portada__secundaria">
                  Ya tengo cuenta
                </Link>
              )}
            </div>
          </div>

          <EscenaPortada />
        </section>

        <section className="mch-sitio-seccion" aria-labelledby="titulo-piezas">
          <div className="mch-sitio-ancho">
            <h2 id="titulo-piezas" className="mch-sitio-titulo-doble mch-sitio-aparece">
              Lo que necesita un taller para trabajar, <span>en un solo sitio</span>
            </h2>
            <div className="mch-sitio-piezas">
              {PIEZAS.map(({ titulo, texto, Icono, tono }) => (
                <article key={titulo} className="mch-sitio-pieza mch-sitio-aparece">
                  <span className={`mch-sitio-chip mch-sitio-chip--${tono}`}>
                    <Icono />
                  </span>
                  <div>
                    <h3>{titulo}</h3>
                    <p>{texto}</p>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="recorrido" className="mch-sitio-seccion">
          <div className="mch-sitio-ancho">
            <header className="mch-sitio-encabezado mch-sitio-aparece">
              <p className="mch-sitio-antetitulo">
                <IconoVistoCirculo />
                Cómo funciona
              </p>
              <h2 className="mch-sitio-titular">Una orden, seis pasos, ningún papel perdido.</h2>
            </header>

            <div className="mch-sitio-destacado mch-sitio-aparece">
              <div className="mch-sitio-cuadricula mch-sitio-destacado__cuadricula" aria-hidden="true" />
              <div className="mch-sitio-destacado__texto">
                <div>
                  <h3>Nadie entrega un coche que no pasó por control de calidad.</h3>
                  <p>
                    Cada vehículo que entra abre una orden de servicio, y la orden solo avanza por
                    pasos que tienen sentido.
                  </p>
                </div>
                <Link to={destino} className="mch-boton">
                  {sesion ? 'Ir a mi cuenta' : 'Crear cuenta'}
                  <IconoFlecha />
                </Link>
              </div>
              <PanelOrden />
            </div>

            <ol className="mch-sitio-recorrido">
              {RECORRIDO.map((r, i) => (
                <li key={r.paso} className="mch-sitio-recorrido__paso mch-sitio-aparece">
                  <span className="mch-sitio-recorrido__numero">{String(i + 1).padStart(2, '0')}</span>
                  <h3>{r.paso}</h3>
                  <p>{r.texto}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="sedes" className="mch-sitio-seccion mch-sitio-seccion--negra mch-sitio-sedes">
          <div className="mch-sitio-ancho mch-sitio-sedes__rejilla">
            <div className="mch-sitio-sedes__texto">
              <p className="mch-sitio-antetitulo">
                <IconoVistoCirculo />
                Una organización, varias sedes
              </p>
              <h2 className="mch-sitio-titular">Con tu nombre, y cada sede en lo suyo.</h2>
              <p className="mch-sitio-bajada">
                Tu organización es la que se ve: cuando tu gente entra, la aplicación lleva el nombre
                de tu grupo o de tu taller, no el nuestro. Si tienes varias sedes, cada una trabaja con
                sus órdenes, sus precios y su personal.
              </p>
              <ul className="mch-sitio-vistos">
                {GARANTIAS.map((g) => (
                  <li key={g.titulo}>
                    <IconoVisto />
                    <div>
                      <strong>{g.titulo}</strong>
                      <span>{g.texto}</span>
                    </div>
                  </li>
                ))}
              </ul>
              <Link to={destino} className="mch-boton">
                {sesion ? 'Ir a mi cuenta' : 'Crear cuenta'}
                <IconoFlecha />
              </Link>
            </div>

            <VentanaOrganizacion />
          </div>
        </section>

        <section id="empezar" className="mch-sitio-seccion">
          <div className="mch-sitio-ancho">
            <header className="mch-sitio-encabezado mch-sitio-aparece">
              <p className="mch-sitio-antetitulo">
                <IconoVistoCirculo />
                Empezar
              </p>
              <h2 className="mch-sitio-titular">Tres pasos y estás dentro.</h2>
            </header>

            <ol className="mch-sitio-pasos">
              {PASOS.map((p, i) => (
                <li key={p.titulo} className="mch-sitio-aparece">
                  <div>
                    <span className="mch-sitio-pasos__numero">{String(i + 1).padStart(2, '0')}</span>
                    <h3>{p.titulo}</h3>
                  </div>
                  <p>{p.texto}</p>
                </li>
              ))}
            </ol>

            <div className="mch-sitio-franja mch-sitio-aparece">
              <IconoRayo />
              <p>Un solo archivo para Windows: se abre en tu navegador y no hay que instalar nada.</p>
              <Link to={destino} className="mch-boton mch-boton--oscuro">
                {sesion ? 'Ir a mi cuenta' : 'Crear mi cuenta'}
                <IconoFlecha />
              </Link>
            </div>
          </div>
        </section>

        <section className="mch-sitio-cierre" aria-labelledby="titulo-cierre">
          <div className="mch-sitio-ancho mch-sitio-aparece">
            <h2 id="titulo-cierre">¿Listo para poner tu taller en orden?</h2>
            <p>Para un taller solo o para un grupo con varias sedes.</p>
            <Link to={destino} className="mch-boton">
              {sesion ? 'Ir a mi cuenta' : 'Crear mi cuenta'}
              <IconoFlecha />
            </Link>
          </div>
        </section>
      </main>

      <PieSitio />
    </div>
  );
}

/**
 * La ilustración de la portada: la orden de un vehículo, el presupuesto tal
 * como lo ve el cliente en su móvil y el aviso de que lo aprobó.
 */
function EscenaPortada() {
  return (
    <div
      className="mch-sitio-ancho mch-sitio-escena"
      role="img"
      aria-label="Ilustración: una orden de servicio, su presupuesto en el móvil del cliente y el aviso de que lo aprobó"
    >
      <div className="mch-sitio-escena__brillo" />

      <div className="mch-sitio-movil">
        <div className="mch-sitio-movil__pantalla">
          <span className="mch-sitio-movil__rotulo">Presupuesto · TGN-00042</span>
          <strong className="mch-sitio-movil__vehiculo">Sedán 2018 · plata</strong>
          <ul className="mch-sitio-movil__lineas">
            <li>
              <span>Pastillas delanteras</span>
              <span>$ 2.900</span>
            </li>
            <li>
              <span>Rectificado de discos</span>
              <span>$ 1.950</span>
            </li>
            <li className="mch-sitio-movil__total">
              <span>Total</span>
              <span>$ 4.850</span>
            </li>
          </ul>
          <span className="mch-sitio-movil__boton">Aprobar</span>
          <span className="mch-sitio-movil__boton mch-sitio-movil__boton--tenue">Rechazar</span>
        </div>
      </div>

      <div className="mch-sitio-tarjeta-orden">
        <div className="mch-sitio-tarjeta-orden__fila">
          <IconoChip />
          <span className="mch-sitio-tarjeta-orden__marca">Mechanified</span>
        </div>
        <div>
          <span className="mch-sitio-tarjeta-orden__vehiculo">Sedán 2018 · plata</span>
          <span className="mch-sitio-tarjeta-orden__folio">TGN-00042</span>
        </div>
        <div className="mch-sitio-tarjeta-orden__fila mch-sitio-tarjeta-orden__fechas">
          <span>
            <small>Recibido</small>14/10
          </span>
          <span>
            <small>Kilometraje</small>87.400
          </span>
          <span>
            <small>Entrega</small>17/10
          </span>
        </div>
      </div>

      <div className="mch-sitio-tarjeta-aviso">
        <div className="mch-sitio-tarjeta-aviso__cabecera">
          <span className="mch-sitio-chip mch-sitio-chip--orquidea">
            <IconoVisto />
          </span>
          <div>
            <strong>Presupuesto aprobado</strong>
            <span>Desde el móvil del cliente</span>
          </div>
        </div>
        <div className="mch-sitio-tarjeta-aviso__cuerpo">
          <span>Total</span>
          <div>
            <strong>$ 4.850,00</strong>
            <em>10:42</em>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Una orden avanzando por sus estados, con lo último que pasó. */
function PanelOrden() {
  const estados = ['Recibido', 'Diagnóstico', 'Presupuesto', 'Reparación', 'Calidad', 'Entrega'];
  const actual = 3;

  return (
    <div className="mch-sitio-panel-orden" role="img" aria-label="Ilustración de una orden en reparación">
      <div>
        <strong className="mch-sitio-panel-orden__titulo">Orden TGN-00042</strong>
        <span className="mch-sitio-panel-orden__detalle">Sedán 2018 · plata · 87.400 km</span>
      </div>
      <ul className="mch-sitio-panel-orden__estados">
        {estados.map((e, i) => (
          <li
            key={e}
            className={
              i === actual
                ? 'mch-sitio-panel-orden__estado mch-sitio-panel-orden__estado--actual'
                : 'mch-sitio-panel-orden__estado'
            }
          >
            {e}
          </li>
        ))}
      </ul>
      <ol className="mch-sitio-linea-tiempo">
        <li>
          <span className="mch-sitio-linea-tiempo__punto">
            <IconoVisto tamano={16} />
          </span>
          <div>
            <strong>Presupuesto aprobado por el cliente</strong>
            <span>14 oct · 10:42 · desde su móvil</span>
          </div>
        </li>
        <li>
          <span className="mch-sitio-linea-tiempo__punto mch-sitio-linea-tiempo__punto--pendiente" />
          <div>
            <strong>Reparación en curso</strong>
            <span>2 de 2 repuestos recibidos</span>
          </div>
        </li>
      </ol>
    </div>
  );
}

/**
 * La aplicación tal como la ve la gente de una organización: con su nombre, y
 * en cada sede solo lo de esa sede. El nombre es de ejemplo.
 */
function VentanaOrganizacion() {
  const ordenes = [
    { folio: 'TGN-00042', vehiculo: 'Sedán 2018 · plata', estado: 'En reparación', tono: '' },
    { folio: 'TGN-00043', vehiculo: 'Pickup 2020 · blanca', estado: 'Diagnóstico', tono: 'rosa' },
    { folio: 'TGN-00044', vehiculo: 'Hatchback 2016 · roja', estado: 'Listo', tono: 'menta' },
  ];

  return (
    <div
      className="mch-sitio-ventana"
      role="img"
      aria-label="Ilustración de la aplicación con el nombre de una organización de ejemplo"
    >
      <div className="mch-sitio-ventana__barra" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>
      <div className="mch-sitio-ventana__cuerpo">
        <div className="mch-sitio-ventana__rail">
          <div className="mch-sitio-ventana__organizacion">
            <span className="mch-sitio-ventana__glifo">TV</span>
            <div>
              <strong>Talleres del Valle</strong>
              <small>con Mechanified</small>
            </div>
          </div>
          <ul className="mch-sitio-ventana__menu">
            <li className="mch-sitio-ventana__menu-actual">Órdenes</li>
            <li>Clientes</li>
            <li>Repuestos</li>
            <li>Panel</li>
          </ul>
        </div>
        <div className="mch-sitio-ventana__contenido">
          <div className="mch-sitio-ventana__sede">
            <strong>Sede Norte</strong>
            <span>
              <IconoCandado />
              Solo los datos de esta sede
            </span>
          </div>
          {ordenes.map((o) => (
            <div key={o.folio} className="mch-sitio-ventana__orden">
              <span className="mch-sitio-ventana__folio">{o.folio}</span>
              <span className="mch-sitio-ventana__vehiculo">{o.vehiculo}</span>
              <span
                className={
                  o.tono
                    ? `mch-sitio-ventana__estado mch-sitio-ventana__estado--${o.tono}`
                    : 'mch-sitio-ventana__estado'
                }
              >
                {o.estado}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
