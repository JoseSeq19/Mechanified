/**
 * Entrada del sitio de Mechanified: lo que se publica en internet.
 *
 * Se compila con `vite build --mode sitio` (ver `vite.config.ts`). La
 * aplicación de cada sede tiene su propia entrada, `main.tsx`, y va dentro de
 * Mechanified.exe.
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { Sitio } from './app/Sitio';
import './styles/tokens.css';
import './styles/base.css';
import './styles/publico.css';
import './styles/cuenta.css';
import './styles/sitio.css';
// Al final: sus reglas de @media print tienen que poder pisar a las demás. El
// presupuesto que recibe el dueño del vehículo se imprime desde aquí.
import './styles/impresion.css';

createRoot(document.getElementById('raiz')!).render(
  <StrictMode>
    <Sitio />
  </StrictMode>,
);
