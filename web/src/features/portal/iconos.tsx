/**
 * Iconos del sitio.
 *
 * Trazos simples sobre una rejilla de 24 px, dibujados para este proyecto. Toman
 * el color del texto (`currentColor`) y son decorativos: lo que significan lo
 * dice siempre el texto que los acompaña.
 */
import type { ReactNode } from 'react';

function Trazo({ tamano, children }: { tamano: number; children: ReactNode }) {
  return (
    <svg
      width={tamano}
      height={tamano}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

interface PropsIcono {
  tamano?: number;
}

export function IconoFlecha({ tamano = 16 }: PropsIcono) {
  return (
    <Trazo tamano={tamano}>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </Trazo>
  );
}

export function IconoVisto({ tamano = 20 }: PropsIcono) {
  return (
    <Trazo tamano={tamano}>
      <path d="M5 12.5l4.2 4.2L19 7" />
    </Trazo>
  );
}

export function IconoVistoCirculo({ tamano = 16 }: PropsIcono) {
  return (
    <Trazo tamano={tamano}>
      <circle cx="12" cy="12" r="9" />
      <path d="M8.3 12.3l2.5 2.5 4.9-5" />
    </Trazo>
  );
}

/** Columnas de un tablero: las órdenes por estado. */
export function IconoTablero({ tamano = 20 }: PropsIcono) {
  return (
    <Trazo tamano={tamano}>
      <rect x="3" y="4" width="18" height="16" rx="3" />
      <path d="M9 4v16M15 4v16" />
    </Trazo>
  );
}

/** Una tuerca: los repuestos. */
export function IconoTuerca({ tamano = 20 }: PropsIcono) {
  return (
    <Trazo tamano={tamano}>
      <path d="M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9z" />
      <circle cx="12" cy="12" r="3" />
    </Trazo>
  );
}

export function IconoSobre({ tamano = 20 }: PropsIcono) {
  return (
    <Trazo tamano={tamano}>
      <rect x="3" y="5" width="18" height="14" rx="3" />
      <path d="M4 7.5l8 5.5 8-5.5" />
    </Trazo>
  );
}

export function IconoBarras({ tamano = 20 }: PropsIcono) {
  return (
    <Trazo tamano={tamano}>
      <path d="M4 20h16M7 16v-4M12 16V7M17 16v-6" />
    </Trazo>
  );
}

export function IconoImpresora({ tamano = 20 }: PropsIcono) {
  return (
    <Trazo tamano={tamano}>
      <path d="M7 8V4h10v4" />
      <rect x="3" y="8" width="18" height="9" rx="2.5" />
      <path d="M7 14h10v6H7z" />
    </Trazo>
  );
}

export function IconoPersonas({ tamano = 20 }: PropsIcono) {
  return (
    <Trazo tamano={tamano}>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20a6.5 6.5 0 0113 0M16 4.5a3.5 3.5 0 010 7M18.5 14.5a6.5 6.5 0 013 5.5" />
    </Trazo>
  );
}

export function IconoDescarga({ tamano = 16 }: PropsIcono) {
  return (
    <Trazo tamano={tamano}>
      <path d="M12 4v11M7 10l5 5 5-5M5 20h14" />
    </Trazo>
  );
}

export function IconoCandado({ tamano = 14 }: PropsIcono) {
  return (
    <Trazo tamano={tamano}>
      <rect x="5" y="10.5" width="14" height="10" rx="2.5" />
      <path d="M8 10.5V8a4 4 0 018 0v2.5" />
    </Trazo>
  );
}

/** El chip de la tarjeta de la portada. */
export function IconoChip({ tamano = 32 }: PropsIcono) {
  return (
    <Trazo tamano={tamano}>
      <rect x="3" y="5" width="18" height="14" rx="3" />
      <path d="M3 10h5M3 14h5M16 10h5M16 14h5M8 5v14M16 5v14" />
    </Trazo>
  );
}

export function IconoRayo({ tamano = 20 }: PropsIcono) {
  return (
    <Trazo tamano={tamano}>
      <path d="M13.5 2.5L5 13.5h6l-1 8 8.5-11h-6z" fill="currentColor" stroke="none" />
    </Trazo>
  );
}

export function IconoMenu({ tamano = 24 }: PropsIcono) {
  return (
    <Trazo tamano={tamano}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </Trazo>
  );
}

export function IconoCerrar({ tamano = 24 }: PropsIcono) {
  return (
    <Trazo tamano={tamano}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Trazo>
  );
}
