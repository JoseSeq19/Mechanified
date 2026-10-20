/**
 * Presentación de Mechanified.
 *
 * La página cuenta lo que hace el producto siguiendo lo que de verdad hace: el
 * recorrido de una orden de servicio, que es el eje de toda la aplicación, y
 * la forma en que se organiza un cliente con varias sedes. Nada de lo que se
 * describe aquí es una promesa: son las pantallas que ya existen.
 */
import { Link } from 'react-router-dom';

import { RUTA_CUENTA, useSesion } from '@/app/sesion';
import { CabeceraSitio, PieSitio } from './CabeceraSitio';

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

const PIEZAS = [
  {
    titulo: 'Tablero de órdenes',
    texto: 'Todo lo que está en el taller, por estado, con búsqueda por folio, placa o cliente.',
  },
  {
    titulo: 'Repuestos y catálogo',
    texto: 'Precios, existencias y mínimos, y el camino de cada pieza desde que se pide.',
  },
  {
    titulo: 'Avisos al cliente',
    texto: 'Los correos salen solos en cada momento clave, con el nombre de tu taller como remitente.',
  },
  {
    titulo: 'Panel de indicadores',
    texto: 'Facturación, ticket medio, productividad por técnico y satisfacción, para quien dirige.',
  },
  {
    titulo: 'Papel cuando hace falta',
    texto: 'La orden se imprime con tus datos y dos huecos para firmar; el presupuesto, también.',
  },
  {
    titulo: 'Personal y permisos',
    texto: 'Administración, asesoría, técnicos y repuestos: cada rol ve y hace lo que le toca.',
  },
];

export function PaginaInicio() {
  const { sesion } = useSesion();
  const destino = sesion ? RUTA_CUENTA : '/entrar?registro';

  return (
    <div className="mch-sitio">
      <CabeceraSitio conSecciones />

      <main>
        <section className="mch-sitio-portada">
          <div className="mch-sitio-ancho mch-sitio-portada__rejilla">
            <div className="mch-sitio-portada__texto">
              <p className="mch-sitio-antetitulo">Gestión de talleres mecánicos</p>
              <h1>El taller en orden, de la recepción a la entrega.</h1>
              <p className="mch-sitio-portada__bajada">
                Mechanified lleva cada vehículo por su camino —fotos al recibirlo, diagnóstico,
                presupuesto que el cliente aprueba desde su móvil, reparación, control de calidad
                y entrega— para un taller solo o para un grupo con varias sedes.
              </p>
              <div className="mch-sitio-portada__acciones">
                <Link to={destino} className="mch-boton mch-sitio-boton-grande">
                  {sesion ? 'Ir a mi cuenta' : 'Crear cuenta y descargar'}
                </Link>
                {!sesion && (
                  <Link to="/entrar" className="mch-boton mch-boton--secundario mch-sitio-boton-grande">
                    Ya tengo cuenta
                  </Link>
                )}
              </div>
              <p className="mch-sitio-portada__nota">Para Windows · Tu primera sede, en un minuto</p>
            </div>

            <FichaDeMuestra />
          </div>
        </section>

        <section id="recorrido" className="mch-sitio-seccion">
          <div className="mch-sitio-ancho">
            <p className="mch-sitio-antetitulo">Cómo funciona</p>
            <h2>Una orden, seis pasos, ningún papel perdido</h2>
            <p className="mch-sitio-seccion__bajada">
              Cada vehículo que entra abre una orden de servicio, y la orden solo avanza por pasos
              que tienen sentido. Nadie entrega un coche que no pasó por control de calidad.
            </p>
            <ol className="mch-sitio-recorrido">
              {RECORRIDO.map((r, i) => (
                <li key={r.paso} className="mch-sitio-recorrido__paso">
                  <span className="mch-sitio-recorrido__numero">{i + 1}</span>
                  <h3>{r.paso}</h3>
                  <p>{r.texto}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="mch-sitio-seccion mch-sitio-seccion--tenue">
          <div className="mch-sitio-ancho">
            <p className="mch-sitio-antetitulo">Para el mostrador y para el que está junto al coche</p>
            <h2>Lo que necesita un taller para trabajar, en un solo sitio</h2>
            <div className="mch-sitio-piezas">
              {PIEZAS.map((p) => (
                <article key={p.titulo} className="mch-sitio-pieza">
                  <h3>{p.titulo}</h3>
                  <p>{p.texto}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="sedes" className="mch-sitio-seccion">
          <div className="mch-sitio-ancho mch-sitio-sedes">
            <div>
              <p className="mch-sitio-antetitulo">Una organización, varias sedes</p>
              <h2>Con tu nombre, y cada sede en lo suyo</h2>
              <p className="mch-sitio-seccion__bajada">
                Tu organización es la que se ve: cuando tu gente entra, la aplicación lleva el
                nombre de tu grupo o de tu taller, no el nuestro. Si tienes varias sedes, cada una
                trabaja con sus órdenes, sus precios y su personal.
              </p>
            </div>
            <ul className="mch-sitio-garantias">
              <li>
                <strong>Una sede no ve los datos de otra.</strong> El aislamiento lo aplica la base
                de datos en cada consulta, no una pantalla que alguien podría saltarse.
              </li>
              <li>
                <strong>Cada persona, con su rol.</strong> El técnico no toca precios y repuestos
                no aprueba presupuestos; administración lo ve todo de su sede.
              </li>
              <li>
                <strong>Las fotos, privadas.</strong> Se guardan en un almacén cerrado y se ven con
                enlaces que caducan en minutos.
              </li>
            </ul>
          </div>
        </section>

        <section id="empezar" className="mch-sitio-seccion mch-sitio-seccion--oscura">
          <div className="mch-sitio-ancho">
            <p className="mch-sitio-antetitulo">Empezar</p>
            <h2>Tres pasos y estás dentro</h2>
            <ol className="mch-sitio-pasos">
              <li>
                <h3>Crea tu cuenta</h3>
                <p>Con tu correo. Es la que usarás para entrar en Mechanified.</p>
              </li>
              <li>
                <h3>Descarga Mechanified</h3>
                <p>El programa para Windows. Se abre en tu navegador y no hay que instalar nada.</p>
              </li>
              <li>
                <h3>Crea tu organización</h3>
                <p>
                  Tú mismo, en un minuto, o pídenos que la creemos y te acompañamos en la puesta en
                  marcha.
                </p>
              </li>
            </ol>
            <Link to={destino} className="mch-boton mch-sitio-boton-grande mch-sitio-boton-claro">
              {sesion ? 'Ir a mi cuenta' : 'Crear mi cuenta'}
            </Link>
          </div>
        </section>
      </main>

      <PieSitio />
    </div>
  );
}

/**
 * Una ficha de orden dibujada con el propio sistema de diseño.
 *
 * No es una captura: es una ilustración de lo que hace la aplicación —una
 * orden avanzando por sus estados, con el presupuesto ya aprobado por el
 * cliente—, y por eso se ve bien en claro y en oscuro sin imágenes.
 */
function FichaDeMuestra() {
  const estados = [
    { texto: 'Recibido', hecho: true },
    { texto: 'Diagnóstico', hecho: true },
    { texto: 'Presupuesto', hecho: true },
    { texto: 'Reparación', actual: true },
    { texto: 'Calidad' },
    { texto: 'Entrega' },
  ];

  return (
    <figure className="mch-sitio-ficha" aria-label="Ilustración de una orden de servicio">
      <div className="mch-sitio-ficha__cabecera">
        <div>
          <span className="mch-sitio-ficha__folio">TGN-00042</span>
          <span className="mch-sitio-ficha__vehiculo">Sedán 2018 · plata · 87.400 km</span>
        </div>
        <span className="mch-distintivo mch-distintivo--activo">En reparación</span>
      </div>

      <ol className="mch-sitio-ficha__estados">
        {estados.map((e) => (
          <li
            key={e.texto}
            className={
              e.actual
                ? 'mch-sitio-ficha__estado mch-sitio-ficha__estado--actual'
                : e.hecho
                  ? 'mch-sitio-ficha__estado mch-sitio-ficha__estado--hecho'
                  : 'mch-sitio-ficha__estado'
            }
          >
            {e.texto}
          </li>
        ))}
      </ol>

      <dl className="mch-sitio-ficha__datos">
        <div>
          <dt>Diagnóstico</dt>
          <dd>Pastillas delanteras al límite · disco rayado</dd>
        </div>
        <div>
          <dt>Presupuesto</dt>
          <dd>
            Aprobado por el cliente desde su móvil <span className="mch-sitio-ficha__hora">10:42</span>
          </dd>
        </div>
        <div>
          <dt>Repuestos</dt>
          <dd>2 de 2 recibidos</dd>
        </div>
      </dl>

      <figcaption className="mch-sitio-ficha__pie">Ilustración · datos de ejemplo</figcaption>
    </figure>
  );
}
