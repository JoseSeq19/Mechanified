import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

/**
 * Dos destinos salen de este mismo código:
 *
 *   - la aplicación (`vite`, `vite build`): lo que va dentro de Mechanified.exe
 *     y lo que usa la gente de cada sede. Sale en `dist/`.
 *   - el sitio (`vite --mode sitio`, `vite build --mode sitio`): la página de
 *     presentación, el registro, la descarga y el alta de la organización, más
 *     las dos páginas que abre el dueño del vehículo desde su correo. Es lo que
 *     se publica en internet. Sale en `dist-sitio/`.
 *
 * Comparten sistema de diseño, sesión y cliente de la API; cambia el punto de
 * entrada. Con `--mode sitio`, Vite lee además `.env.sitio` si existe.
 */
const ES_SITIO = (mode: string) => mode === 'sitio';

/**
 * Cambia el script de entrada del index.html según el destino.
 *
 * Tiene que ser `order: 'pre'`: sin eso, Vite aplica el hook después de haber
 * leído el HTML para decidir qué empaquetar, y el sitio salía compilado desde
 * la entrada de la aplicación con solo el título cambiado.
 */
function entradaSegunDestino(mode: string): Plugin {
  return {
    name: 'mch-entrada-segun-destino',
    transformIndexHtml: {
      order: 'pre',
      handler(html) {
        if (!ES_SITIO(mode)) return html;
        return html
          .replace('/src/main.tsx', '/src/sitio.tsx')
          .replace(
            '<title>Mechanified</title>',
            '<title>Mechanified · gestión de talleres mecánicos</title>',
          );
      },
    },
  };
}

export default defineConfig(({ mode }) => ({
  plugins: [react(), entradaSegunDestino(mode)],
  resolve: {
    // import.meta.dirname en lugar de __dirname: el cargador nativo de config
    // de Vite no define __dirname y pasará a ser el predeterminado.
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  build: {
    outDir: ES_SITIO(mode) ? 'dist-sitio' : 'dist',
  },
  server: {
    // El sitio en el puerto de al lado, para poder tener los dos abiertos.
    port: ES_SITIO(mode) ? 5174 : 5173,
    proxy: {
      // La web llama a `/api/...`, mismo origen que la página, y Vite reenvía
      // a la API. En desarrollo no hay petición entre orígenes, así que CORS
      // no interviene.
      //
      // No es comodidad: `localhost` puede resolver a ::1 o a 127.0.0.1 según
      // el proceso, Vite escucha en una pila y uvicorn en la otra, y el
      // navegador acaba anunciando un origen que la API no reconoce. El
      // síntoma es un preflight con 400 y un "no se pudo contactar la API" que
      // manda a buscar donde no es. Con el proxy, ese cruce desaparece.
      //
      // El destino es 127.0.0.1 explícito, no localhost, para que Vite no
      // vuelva a caer en la misma ambigüedad al reenviar.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (ruta) => ruta.replace(/^\/api/, ''),
      },
    },
  },
}));
