import { useRef, useState } from 'react';

import { Boton } from '@/components/ui';

/**
 * El inventario de lo que se queda con el vehículo.
 *
 * Es lo que se revisa delante del cliente al recibir el coche y lo que se
 * compara al entregarlo: el gato, la llave de ruedas, el caucho de repuesto.
 * Hasta ahora la columna existía y la API lo aceptaba, pero ningún formulario
 * lo pedía, así que el documento impreso de la orden salía siempre sin esa
 * parte.
 *
 * Son pares libres —nombre y qué se anota de él— porque cada taller inventaría
 * cosas distintas; las sugerencias de arriba son un atajo, no una lista
 * cerrada. El backend los acota: hasta 40 cosas, y nada anidado.
 */

/** Lo que se inventaría en casi cualquier taller. Un toque y está puesto. */
const SUGERENCIAS = [
  'Gato',
  'Llave de ruedas',
  'Caucho de repuesto',
  'Radio',
  'Alfombras',
  'Herramientas',
  'Documentos',
  'Triángulo',
  'Extintor',
];

/** El valor por omisión al añadir algo desde una sugerencia. */
const PRESENTE = 'Sí';

export type Inventario = Record<string, string>;

export function CampoInventario({
  valor,
  onCambio,
}: {
  valor: Inventario | undefined;
  onCambio: (valor: Inventario) => void;
}) {
  // El estado vive aquí como lista de pares y no se vuelve a sincronizar con
  // la prop. Es deliberado: un objeto reordena sus claves al renombrar una, y
  // el campo saltaría de sitio mientras se escribe. La prop solo es el punto
  // de partida, y los dos sitios que usan esto montan el campo de cero.
  const [pares, setPares] = useState<[string, string][]>(() => Object.entries(valor ?? {}));
  const ultimaFila = useRef<HTMLInputElement | null>(null);

  function publicar(siguientes: [string, string][]) {
    setPares(siguientes);

    // Las filas sin nombre todavía no son datos: se quedan en pantalla pero no
    // salen hacia la API. La primera de dos con el mismo nombre es la que vale.
    const objeto: Inventario = {};
    for (const [clave, contenido] of siguientes) {
      const nombre = clave.trim();
      if (nombre && !(nombre in objeto)) objeto[nombre] = contenido.trim();
    }
    onCambio(objeto);
  }

  const puestos = new Set(pares.map(([clave]) => clave.trim().toLowerCase()));
  const disponibles = SUGERENCIAS.filter((s) => !puestos.has(s.toLowerCase()));

  return (
    <div className="mch-campo">
      <span className="mch-campo__etiqueta">Inventario recibido</span>

      {disponibles.length > 0 && (
        <div className="mch-sugerencias">
          {disponibles.map((nombre) => (
            <button
              key={nombre}
              type="button"
              className="mch-sugerencia"
              onClick={() => publicar([...pares, [nombre, PRESENTE]])}
            >
              + {nombre}
            </button>
          ))}
        </div>
      )}

      {pares.length > 0 && (
        <div className="mch-inventario">
          {pares.map(([clave, contenido], indice) => (
            <div key={indice} className="mch-inventario__fila">
              <input
                className="mch-campo__control"
                aria-label={`Qué cosa, fila ${indice + 1}`}
                placeholder="Qué"
                maxLength={60}
                value={clave}
                ref={indice === pares.length - 1 ? ultimaFila : undefined}
                onChange={(e) =>
                  publicar(pares.map((p, i) => (i === indice ? [e.target.value, p[1]] : p)))
                }
              />
              <input
                className="mch-campo__control"
                aria-label={`Qué se anota de ${clave || `la fila ${indice + 1}`}`}
                placeholder="Sí, falta, rayado…"
                maxLength={200}
                value={contenido}
                onChange={(e) =>
                  publicar(pares.map((p, i) => (i === indice ? [p[0], e.target.value] : p)))
                }
              />
              <Boton
                variante="fantasma"
                type="button"
                aria-label={`Quitar ${clave || 'la fila'}`}
                onClick={() => publicar(pares.filter((_, i) => i !== indice))}
              >
                ✕
              </Boton>
            </div>
          ))}
        </div>
      )}

      <div>
        <Boton
          variante="secundario"
          type="button"
          onClick={() => {
            publicar([...pares, ['', '']]);
            // El foco va a la fila nueva en el siguiente pintado; sin esto hay
            // que ir a buscarla con el ratón cada vez.
            requestAnimationFrame(() => ultimaFila.current?.focus());
          }}
        >
          Añadir otra cosa
        </Boton>
      </div>

      <span className="mch-campo__ayuda">
        Lo que se queda con el vehículo. Sale impreso en la orden que firma el cliente, y es con
        lo que se compara al entregarlo.
      </span>
    </div>
  );
}
