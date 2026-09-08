/** Arranque de la aplicación web. Router y providers llegan en la Fase 5. */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './styles/tokens.css';

createRoot(document.getElementById('raiz')!).render(
  <StrictMode>
    <main style={{ padding: '2rem', fontFamily: 'var(--mch-fuente-base)' }}>
      <h1>Mechanified</h1>
      <p>Interfaz en construcción — Fase 5.</p>
    </main>
  </StrictMode>,
);
