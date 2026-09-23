import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { Cargando } from '@/components/ui';
import { PaginaLogin } from '@/features/auth/PaginaLogin';
import { PaginaPlantillas } from '@/features/calidad/PaginaPlantillas';
import { PaginaClientes } from '@/features/clientes/PaginaClientes';
import { PaginaEncuestaPublica } from '@/features/encuestas/PaginaEncuestaPublica';
import { PaginaEncuestas } from '@/features/encuestas/PaginaEncuestas';
import { PaginaPanel } from '@/features/metricas/PaginaPanel';
import { PaginaOrden } from '@/features/ordenes/PaginaOrden';
import { PaginaOrdenes } from '@/features/ordenes/PaginaOrdenes';
import { PaginaPresupuestoPublico } from '@/features/presupuestos/PaginaPresupuestoPublico';
import { PaginaRepuestos } from '@/features/repuestos/PaginaRepuestos';
import { PaginaUsuarios } from '@/features/usuarios/PaginaUsuarios';
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

/**
 * Rutas que exigen sesión. Todo lo de dentro pasa por el control de acceso.
 */
function RutasPrivadas() {
  const { sesion, cargando } = useSesion();

  if (cargando) return <Cargando texto="Abriendo sesión…" />;
  if (!sesion) return <PaginaLogin />;

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/ordenes" element={<PaginaOrdenes />} />
        <Route path="/ordenes/:ordenId" element={<PaginaOrden />} />
        <Route path="/vehiculos" element={<PaginaVehiculos />} />
        <Route path="/repuestos" element={<PaginaRepuestos />} />
        <Route path="/calidad" element={<PaginaPlantillas />} />
        <Route path="/encuestas" element={<PaginaEncuestas />} />
        <Route path="/informes" element={<PaginaPanel />} />
        <Route path="/personal" element={<PaginaUsuarios />} />
        <Route path="/clientes" element={<PaginaClientes />} />
        <Route path="*" element={<Navigate to="/ordenes" replace />} />
      </Route>
    </Routes>
  );
}

/**
 * Las dos páginas públicas van fuera del control de sesión, y tienen que
 * resolverse antes: quien abre esos enlaces es un cliente sin cuenta, y si
 * pasaran por RutasPrivadas verían la pantalla de inicio de sesión.
 *
 * Estas rutas son parte del contrato con el backend: `shared/enlaces.py` arma
 * con ellas los enlaces que van en los correos. Cambiar una aquí sin cambiarla
 * allí rompe los mensajes ya enviados.
 */
function Rutas() {
  return (
    <Routes>
      <Route path="/presupuesto/:token" element={<PaginaPresupuestoPublico />} />
      <Route path="/encuesta/:token" element={<PaginaEncuestaPublica />} />
      <Route path="*" element={<RutasPrivadas />} />
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
