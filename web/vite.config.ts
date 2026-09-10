import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    // import.meta.dirname en lugar de __dirname: el cargador nativo de config
    // de Vite no define __dirname y pasará a ser el predeterminado.
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  server: {
    port: 5173,
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
});
