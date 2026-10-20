import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { PaginaClaveNueva } from '@/features/auth/PaginaClaveNueva';
import { PaginaEncuestaPublica } from '@/features/encuestas/PaginaEncuestaPublica';
import { MarcoSitio } from '@/features/portal/CabeceraSitio';
import { PaginaCuenta } from '@/features/portal/PaginaCuenta';
import { PaginaEntrar } from '@/features/portal/PaginaEntrar';
import { PaginaInicio } from '@/features/portal/PaginaInicio';
import { PaginaPresupuestoPublico } from '@/features/presupuestos/PaginaPresupuestoPublico';
import { ProveedorSesion, RUTA_CLAVE_NUEVA, RUTA_CUENTA } from './sesion';

const clienteConsultas = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

/**
 * El sitio de Mechanified.
 *
 * Tres públicos distintos pasan por aquí:
 *
 *   - quien conoce el producto (`/`) y se registra para descargarlo
 *     (`/entrar`, `/cuenta`);
 *   - quien ya tiene cuenta y vuelve a por el instalador, o a crear su
 *     organización;
 *   - el dueño de un vehículo, que abre el presupuesto o la encuesta que le
 *     mandó su taller. Esas dos rutas son parte del contrato con el backend
 *     (`shared/enlaces.py`) y viven aquí, en el sitio público, porque el
 *     enlace se abre desde cualquier móvil: en el equipo del taller no lo
 *     encontraría nadie.
 */
export function Sitio() {
  return (
    <QueryClientProvider client={clienteConsultas}>
      <ProveedorSesion>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<PaginaInicio />} />
            <Route path="/entrar" element={<PaginaEntrar />} />
            <Route path={RUTA_CUENTA} element={<PaginaCuenta />} />
            <Route
              path={RUTA_CLAVE_NUEVA}
              element={
                <MarcoSitio>
                  <PaginaClaveNueva />
                </MarcoSitio>
              }
            />
            <Route path="/presupuesto/:token" element={<PaginaPresupuestoPublico />} />
            <Route path="/encuesta/:token" element={<PaginaEncuestaPublica />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ProveedorSesion>
    </QueryClientProvider>
  );
}
