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
  server: { port: 5173 },
});
