/**
 * La cuenta en el sitio: descargar Mechanified y tener una organización.
 *
 * Es una guía de tres pasos, en el orden en que se dan: descargar, crear (o
 * pedir) la organización, y entrar en la aplicación con esta misma cuenta.
 * Quien vuelve con todo hecho ve los tres en verde y el botón de descarga, que
 * es a lo que suele volver.
 *
 * Aquí aterriza también el enlace con el que se confirma el registro, si el
 * proyecto de Supabase lo pide. El cliente de este proyecto no lee sesiones de
 * la URL por su cuenta (ver `lib/supabase.ts`), así que se recoge a mano antes
 * de decidir si hay sesión, igual que hace la página de contraseña nueva.
 */
import { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { Aviso, Boton, Cargando } from '@/components/ui';
import { ETIQUETA_ROL, useSesion } from '@/app/sesion';
import { ErrorApi } from '@/lib/api';
import { supabase } from '@/lib/supabase';
import { CLAVE_CUENTA, obtenerCuenta } from '@/features/organizaciones/api';
import { Incorporacion } from '@/features/organizaciones/Incorporacion';
import { CabeceraSitio, PieSitio } from './CabeceraSitio';
import { descargarInstalador } from './descarga';

type Enlace = 'sin-enlace' | 'recogiendo' | 'recogido' | { error: string };

function hayEnlaceEnLaUrl(): boolean {
  const hash = window.location.hash;
  return (
    hash.includes('access_token=') ||
    hash.includes('error_description=') ||
    new URLSearchParams(window.location.search).has('code')
  );
}

/** Abre la sesión que trae el enlace de confirmación del registro. */
async function recogerSesionDelEnlace(): Promise<string | null> {
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  const consulta = new URLSearchParams(window.location.search);
  const codigo = consulta.get('code');

  // La sesión viaja en claro en la URL: se quita en cuanto se ha leído.
  window.history.replaceState(null, '', window.location.pathname);

  const descripcion = hash.get('error_description') ?? consulta.get('error_description');
  if (descripcion) {
    return descripcion.toLowerCase().includes('expired')
      ? 'El enlace de confirmación caducó. Entra con tu correo y contraseña para pedir otro.'
      : 'El enlace de confirmación no es válido o ya se usó.';
  }

  const accessToken = hash.get('access_token');
  const refreshToken = hash.get('refresh_token');
  if (accessToken && refreshToken) {
    const { error } = await supabase.auth.setSession({
      access_token: accessToken,
      refresh_token: refreshToken,
    });
    return error ? error.message : null;
  }

  if (codigo) {
    const { error } = await supabase.auth.exchangeCodeForSession(codigo);
    return error ? error.message : null;
  }
  return null;
}

export function PaginaCuenta() {
  const { sesion, cargando } = useSesion();
  const [enlace, setEnlace] = useState<Enlace>(() =>
    hayEnlaceEnLaUrl() ? 'recogiendo' : 'sin-enlace',
  );

  useEffect(() => {
    document.title = 'Mi cuenta · Mechanified';
  }, []);

  useEffect(() => {
    if (enlace !== 'recogiendo') return;
    let vigente = true;
    void recogerSesionDelEnlace().then((error) => {
      if (vigente) setEnlace(error ? { error } : 'recogido');
    });
    return () => {
      vigente = false;
    };
  }, [enlace]);

  if (cargando || enlace === 'recogiendo') {
    return (
      <div className="mch-sitio">
        <CabeceraSitio sinAcciones />
        <main className="mch-sitio-acceso">
          <Cargando texto="Abriendo tu cuenta…" />
        </main>
      </div>
    );
  }

  if (typeof enlace === 'object') {
    return (
      <div className="mch-sitio">
        <CabeceraSitio sinAcciones />
        <main className="mch-sitio-acceso">
          <div className="mch-acceso__caja mch-panel mch-sitio-acceso__formulario">
            <Aviso tono="error">{enlace.error}</Aviso>
            <a className="mch-boton" href="/entrar">
              Ir a entrar
            </a>
          </div>
        </main>
      </div>
    );
  }

  if (!sesion) return <Navigate to="/entrar" replace />;

  return <Cuenta />;
}

function Cuenta() {
  const { sesion, renovar, salir } = useSesion();
  const clienteConsultas = useQueryClient();
  const cuenta = useQuery({ queryKey: CLAVE_CUENTA, queryFn: obtenerCuenta });
  const [descargando, setDescargando] = useState(false);
  const [errorDescarga, setErrorDescarga] = useState<string | null>(null);
  const [descargado, setDescargado] = useState(false);

  const nombre = sesion?.user.user_metadata?.nombre_completo as string | undefined;
  const pertenencia = cuenta.data?.organizacion ?? null;
  const conOrganizacion = Boolean(pertenencia?.activo);

  async function alDescargar() {
    setErrorDescarga(null);
    setDescargando(true);
    try {
      await descargarInstalador();
      setDescargado(true);
    } catch (err) {
      setErrorDescarga(err instanceof Error ? err.message : 'No se pudo preparar la descarga.');
    } finally {
      setDescargando(false);
    }
  }

  return (
    <div className="mch-sitio">
      <CabeceraSitio sinAcciones />
      <main className="mch-sitio-cuenta">
        <div className="mch-sitio-ancho mch-sitio-cuenta__columna">
          <header className="mch-sitio-cuenta__cabecera">
            <div>
              <p className="mch-sitio-antetitulo">Tu cuenta</p>
              <h1>{nombre ? `Hola, ${nombre.split(' ')[0]}` : 'Hola'}</h1>
              <p className="mch-sitio-cuenta__correo">{sesion?.user.email}</p>
            </div>
            <Boton variante="secundario" onClick={() => void salir()}>
              Cerrar sesión
            </Boton>
          </header>

          <ol className="mch-sitio-guia">
            <li className={`mch-sitio-guia__paso${descargado ? ' mch-sitio-guia__paso--hecho' : ''}`}>
              <div className="mch-sitio-guia__titulo">
                <span className="mch-sitio-guia__numero">1</span>
                <h2>Descarga Mechanified para Windows</h2>
              </div>
              <p>
                Es un solo archivo. Al abrirlo, Mechanified se abre en tu navegador; no hay que
                instalar nada. Los datos de tu taller no se guardan en el equipo: están en el
                servidor de Mechanified, así que puedes entrar desde otro computador.
              </p>
              <div className="mch-sitio-guia__acciones">
                <Boton onClick={() => void alDescargar()} cargando={descargando}>
                  Descargar Mechanified.exe
                </Boton>
                <span className="mch-sitio-guia__nota">Windows 10 u 11</span>
              </div>
              {errorDescarga && <Aviso tono="error">{errorDescarga}</Aviso>}
              {descargado && (
                <Aviso tono="info">
                  Si Windows avisa de que es una aplicación que no reconoce, pulsa «Más
                  información» y después «Ejecutar de todos modos».
                </Aviso>
              )}
            </li>

            <li
              className={`mch-sitio-guia__paso${conOrganizacion ? ' mch-sitio-guia__paso--hecho' : ''}`}
            >
              <div className="mch-sitio-guia__titulo">
                <span className="mch-sitio-guia__numero">2</span>
                <h2>{conOrganizacion ? 'Tu organización' : 'Crea tu organización'}</h2>
              </div>

              {cuenta.isPending && <Cargando texto="Revisando tu cuenta…" />}
              {cuenta.isError && (
                <Aviso tono="error">
                  {cuenta.error instanceof ErrorApi
                    ? cuenta.error.message
                    : 'No se pudo consultar tu cuenta.'}
                </Aviso>
              )}

              {pertenencia?.activo && (
                <div className="mch-sitio-organizacion">
                  <strong>{pertenencia.organizacion_nombre}</strong>
                  <span>
                    Sede {pertenencia.taller_nombre} · {ETIQUETA_ROL[pertenencia.rol]}
                  </span>
                </div>
              )}

              {pertenencia && !pertenencia.activo && (
                <Aviso tono="alerta">
                  Tu acceso a <strong>{pertenencia.organizacion_nombre}</strong> está desactivado.
                  Habla con la administración de {pertenencia.taller_nombre}.
                </Aviso>
              )}

              {cuenta.data && !pertenencia && (
                <>
                  <p>
                    La organización es tu grupo o tu taller: con su nombre se presentará Mechanified
                    a tu gente. Puedes crearla ahora o pedirnos que lo hagamos; también puedes
                    hacerlo al abrir la aplicación.
                  </p>
                  <Incorporacion
                    estado={cuenta.data}
                    nombreSugerido={nombre}
                    onCreada={async (estado) => {
                      clienteConsultas.setQueryData(CLAVE_CUENTA, estado);
                      // El token en uso se emitió sin taller; el nuevo ya lo trae.
                      await renovar();
                    }}
                    onSolicitada={(estado) => clienteConsultas.setQueryData(CLAVE_CUENTA, estado)}
                  />
                </>
              )}
            </li>

            <li className="mch-sitio-guia__paso">
              <div className="mch-sitio-guia__titulo">
                <span className="mch-sitio-guia__numero">3</span>
                <h2>Entra en Mechanified</h2>
              </div>
              <p>
                Abre <strong>Mechanified.exe</strong> y entra con <strong>{sesion?.user.email}</strong>{' '}
                y tu contraseña.{' '}
                {conOrganizacion
                  ? `Verás ${pertenencia?.organizacion_nombre} en lugar de Mechanified: es tu organización.`
                  : 'Si aún no tienes organización, la aplicación te ofrecerá crearla.'}
              </p>
              <p className="mch-sitio-guia__nota">
                Al resto de tu gente no le hace falta registrarse aquí: la administración de cada
                sede le crea su cuenta desde Personal, dentro de la aplicación.
              </p>
            </li>
          </ol>
        </div>
      </main>
      <PieSitio />
    </div>
  );
}
