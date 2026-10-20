/**
 * Lo que ve en la aplicación quien entra con una cuenta sin organización.
 *
 * Es el caso de quien se registró en el sitio, descargó Mechanified y lo abrió
 * antes de crear su organización: se le ofrece crearla aquí mismo, o pedirla.
 *
 * Hay otros dos casos que llegan aquí con el mismo síntoma —un token sin taller—
 * y que conviene distinguir, porque la salida es otra:
 *
 *   - La organización ya existe, pero el token es de antes (se creó desde el
 *     sitio con esta aplicación abierta). Basta con renovarlo, y se hace solo.
 *   - La cuenta tiene organización y aun así el token renovado no trae taller:
 *     o la dieron de baja, o el hook de Auth no está activo en el proyecto.
 */
import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { Aviso, Boton, Cargando, Marca } from '@/components/ui';
import { useSesion } from '@/app/sesion';
import { ErrorApi } from '@/lib/api';
import { URL_SITIO } from '@/lib/marca';
import { CLAVE_CUENTA, obtenerCuenta, type EstadoCuenta } from './api';
import { Incorporacion } from './Incorporacion';

/**
 * Cómo fue pedir un token nuevo. `fallida` es que no hubo respuesta (sin red,
 * por lo general); `hecha` con esta pantalla todavía delante es que el token
 * llegó y aun así sin taller.
 */
type Renovacion = 'pendiente' | 'en-curso' | 'hecha' | 'fallida';

export function PaginaSinOrganizacion() {
  const { sesion, renovar, salir } = useSesion();
  const clienteConsultas = useQueryClient();
  const cuenta = useQuery({ queryKey: CLAVE_CUENTA, queryFn: obtenerCuenta });
  const [renovacion, setRenovacion] = useState<Renovacion>('pendiente');

  const pertenencia = cuenta.data?.organizacion ?? null;

  // Si trae taller, la aplicación entra sola y esta pantalla desaparece; si al
  // terminar seguimos aquí, abajo se explica por qué.
  async function renovarSesion() {
    setRenovacion('en-curso');
    try {
      await renovar();
      setRenovacion('hecha');
    } catch {
      setRenovacion('fallida');
    }
  }

  // La organización existe pero el token se emitió antes: se pide uno nuevo,
  // una vez. Pasa cuando se creó desde el sitio con esta aplicación abierta.
  useEffect(() => {
    if (pertenencia?.activo && renovacion === 'pendiente') void renovarSesion();
  });

  async function alCrear(estado: EstadoCuenta) {
    clienteConsultas.setQueryData(CLAVE_CUENTA, estado);
    await renovarSesion();
  }

  const nombreRegistro = sesion?.user.user_metadata?.nombre_completo as string | undefined;

  return (
    <main className="mch-bienvenida">
      <div className="mch-bienvenida__caja">
        <header className="mch-bienvenida__cabecera">
          <Marca />
          <button type="button" className="mch-acceso__enlace" onClick={() => void salir()}>
            Cerrar sesión
          </button>
        </header>

        {cuenta.isPending && <Cargando texto="Revisando tu cuenta…" />}

        {cuenta.isError && (
          <Aviso tono="error">
            {cuenta.error instanceof ErrorApi
              ? cuenta.error.message
              : 'No se pudo consultar tu cuenta.'}
          </Aviso>
        )}

        {pertenencia && !pertenencia.activo && (
          <Aviso tono="alerta">
            Tu acceso a <strong>{pertenencia.organizacion_nombre}</strong> está desactivado. Si
            crees que es un error, habla con la administración de {pertenencia.taller_nombre}.
          </Aviso>
        )}

        {renovacion === 'en-curso' && (
          <Cargando
            texto={pertenencia ? `Abriendo ${pertenencia.organizacion_nombre}…` : 'Abriendo…'}
          />
        )}

        {pertenencia?.activo && renovacion === 'fallida' && (
          <>
            <Aviso tono="alerta">
              <strong>{pertenencia.organizacion_nombre}</strong> está lista, pero no pudimos abrirla:
              el servidor de acceso no respondió. Revisa tu conexión y vuelve a intentarlo.
            </Aviso>
            <div>
              <Boton onClick={() => void renovarSesion()}>Reintentar</Boton>
            </div>
          </>
        )}

        {/* El token nuevo llegó y aun así sin taller: es el hook de Auth
            (mch_hook_access_token) apagado en el proyecto de Supabase. Eso no
            lo arregla quien usa la aplicación, así que el aviso le dice a quién
            acudir y no qué tocar. */}
        {pertenencia?.activo && renovacion === 'hecha' && (
          <Aviso tono="alerta">
            Tu cuenta pertenece a <strong>{pertenencia.organizacion_nombre}</strong>, pero tu sesión
            no trae tu sede. Cierra sesión y vuelve a entrar; si sigue igual, avisa al equipo de
            Mechanified.
          </Aviso>
        )}

        {cuenta.data && !pertenencia && renovacion !== 'en-curso' && (
          <>
            <div className="mch-bienvenida__texto">
              <h1>Te damos la bienvenida a Mechanified</h1>
              <p>
                Tu cuenta ({cuenta.data.email ?? sesion?.user.email}) todavía no pertenece a
                ninguna organización. Créala ahora y entras como su administrador, o pide que la
                cree el equipo de Mechanified.
              </p>
            </div>
            <Incorporacion
              estado={cuenta.data}
              nombreSugerido={nombreRegistro}
              onCreada={alCrear}
              onSolicitada={(estado) => clienteConsultas.setQueryData(CLAVE_CUENTA, estado)}
            />
            <p className="mch-bienvenida__pie">
              También puedes hacerlo desde <a href={`${URL_SITIO}/cuenta`}>tu cuenta en el sitio</a>.
            </p>
          </>
        )}

        {cuenta.isError && (
          <Boton variante="secundario" onClick={() => void cuenta.refetch()}>
            Reintentar
          </Boton>
        )}
      </div>
    </main>
  );
}
