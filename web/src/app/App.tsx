import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { Cargando } from '@/components/ui';
import { PaginaLogin } from '@/features/auth/PaginaLogin';
import { PaginaClientes } from '@/features/clientes/PaginaClientes';
import { PaginaOrden } from '@/features/ordenes/PaginaOrden';
import { PaginaOrdenes } from '@/features/ordenes/PaginaOrdenes';
import { PaginaVehiculos } from '@/features/vehiculos/PaginaVehiculos';
import { Layout } from './Layout';
import { ProveedorSesion, useSesion } from './sesion';

const clienteConsultas = new QueryClient({
  defaultOptions: {
    queries: {
      // Los datos de un taller los cambian varias personas a la vez; refrescar
      // al volver a la pestaña evita trabajar sobre una lista vieja.
      refetchOnWindowFocus: true,
      staleTime: 15_000,
      retry: 1,
    },
  },
});

function Rutas() {
  const { sesion, cargando } = useSesion();

  if (cargando) return <Cargando texto="Abriendo sesión…" />;
  if (!sesion) return <PaginaLogin />;

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/ordenes" element={<PaginaOrdenes />} />
        <Route path="/ordenes/:ordenId" element={<PaginaOrden />} />
        <Route path="/vehiculos" element={<PaginaVehiculos />} />
        <Route path="/clientes" element={<PaginaClientes />} />
        <Route path="*" element={<Navigate to="/ordenes" replace />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <QueryClientProvider client={clienteConsultas}>
      <ProveedorSesion>
        <BrowserRouter>
          <Rutas />
        </BrowserRouter>
      </ProveedorSesion>
    </QueryClientProvider>
  );
}
