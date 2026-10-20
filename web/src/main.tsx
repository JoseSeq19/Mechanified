import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './app/App';
// La letra del logo. Va dentro de Mechanified.exe: no depende de internet.
import '@fontsource/montserrat/400.css';
import '@fontsource/montserrat/700.css';
import './styles/tokens.css';
import './styles/base.css';
import './styles/layout.css';
import './styles/tablero.css';
import './styles/panel.css';
import './styles/publico.css';
import './styles/cuenta.css';
// Al final: sus reglas de @media print tienen que poder pisar a las demás.
import './styles/impresion.css';

createRoot(document.getElementById('raiz')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
