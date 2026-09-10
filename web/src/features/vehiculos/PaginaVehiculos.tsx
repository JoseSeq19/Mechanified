import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Aviso, Boton, Cargando, Distintivo, Vacio } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { useSesion } from '@/app/sesion';
import { FormularioVehiculo } from './FormularioVehiculo';
import { borrarVehiculo, crearVehiculo, editarVehiculo, listarVehiculos, type Vehiculo } from './api';

const POR_PAGINA = 15;

export function PaginaVehiculos() {
  const { claims } = useSesion();
  const clienteQuery = useQueryClient();

  const [texto, setTexto] = useState('');
  const [busqueda, setBusqueda] = useState('');
  const [desplazamiento, setDesplazamiento] = useState(0);
  const [editando, setEditando] = useState<Vehiculo | 'nuevo' | null>(null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      setBusqueda(texto.trim().length >= 3 ? texto.trim() : '');
      setDesplazamiento(0);
    }, 300);
    return () => clearTimeout(t);
  }, [texto]);

  const filtros = { busqueda, limite: POR_PAGINA, desplazamiento };
  const consulta = useQuery({
    queryKey: ['vehiculos', filtros],
    queryFn: () => listarVehiculos(filtros),
  });

  const refrescar = () => clienteQuery.invalidateQueries({ queryKey: ['vehiculos'] });

  const mutBorrar = useMutation({
    mutationFn: borrarVehiculo,
    onSuccess: () => {
      setErrorAccion(null);
      refrescar();
    },
    onError: (e) =>
      setErrorAccion(e instanceof ErrorApi ? e.message : 'No se pudo borrar el vehículo.'),
  });

  const puedeEscribir = claims?.rol === 'admin_taller' || claims?.rol === 'asesor_servicio';
  const puedeBorrar = claims?.rol === 'admin_taller';

  const total = consulta.data?.total ?? 0;
  const paginas = Math.max(1, Math.ceil(total / POR_PAGINA));
  const paginaActual = Math.floor(desplazamiento / POR_PAGINA) + 1;
  const items = consulta.data?.items ?? [];

  return (
    <>
      <header
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          justifyContent: 'space-between',
          gap: 'var(--mch-esp-4)',
          flexWrap: 'wrap',
          marginBottom: 'var(--mch-esp-6)',
        }}
      >
        <div>
          <h1 style={{ fontSize: 'var(--mch-txt-xl)' }}>Vehículos</h1>
          <p
            style={{
              margin: 'var(--mch-esp-1) 0 0',
              color: 'var(--mch-texto-secundario)',
              fontSize: 'var(--mch-txt-sm)',
            }}
          >
            {total} {total === 1 ? 'vehículo registrado' : 'vehículos registrados'}
          </p>
        </div>
        {puedeEscribir && <Boton onClick={() => setEditando('nuevo')}>Nuevo vehículo</Boton>}
      </header>

      <div style={{ marginBottom: 'var(--mch-esp-4)' }}>
        <input
          className="mch-campo__control"
          style={{ maxWidth: 320 }}
          type="search"
          placeholder="Buscar por placa, VIN, marca o modelo…"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          aria-label="Buscar vehículos"
        />
      </div>

      {errorAccion && (
        <div style={{ marginBottom: 'var(--mch-esp-4)' }}>
          <Aviso tono="alerta">{errorAccion}</Aviso>
        </div>
      )}

      <div className="mch-panel">
        {consulta.isLoading ? (
          <Cargando />
        ) : consulta.isError ? (
          <div style={{ padding: 'var(--mch-esp-6)' }}>
            <Aviso tono="error">
              {consulta.error instanceof ErrorApi
                ? consulta.error.message
                : 'No se pudieron cargar los vehículos.'}
            </Aviso>
          </div>
        ) : items.length === 0 ? (
          <Vacio
            titulo={busqueda ? 'Sin resultados' : 'Todavía no hay vehículos'}
            detalle={
              busqueda
                ? `Ningún vehículo coincide con "${busqueda}".`
                : 'Registra uno para poder abrir órdenes de servicio.'
            }
          />
        ) : (
          <div className="mch-tabla-envoltura">
            <table className="mch-tabla">
              <thead>
                <tr>
                  <th>Placa</th>
                  <th>Vehículo</th>
                  <th>Propietario</th>
                  <th>Kilometraje</th>
                  <th>Estado</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((v) => (
                  <tr key={v.id}>
                    <td style={{ fontFamily: 'var(--mch-fuente-mono)', fontWeight: 600 }}>
                      {v.placa}
                    </td>
                    <td>
                      <div style={{ fontWeight: 560 }}>
                        {v.marca} {v.modelo}
                      </div>
                      <div
                        style={{
                          color: 'var(--mch-texto-secundario)',
                          fontSize: 'var(--mch-txt-xs)',
                        }}
                      >
                        {[v.anio, v.color].filter(Boolean).join(' · ') || '—'}
                      </div>
                    </td>
                    <td>{v.cliente_nombre ?? '—'}</td>
                    <td>{v.kilometraje_ultimo?.toLocaleString('es') ?? '—'}</td>
                    <td>
                      <Distintivo tono={v.activo ? 'activo' : 'inactivo'}>
                        {v.activo ? 'Activo' : 'Inactivo'}
                      </Distintivo>
                    </td>
                    <td>
                      <div className="mch-tabla__acciones">
                        <Link className="mch-boton mch-boton--fantasma" to={`/ordenes?vehiculo=${v.id}`}>
                          Órdenes
                        </Link>
                        {puedeEscribir && (
                          <Boton variante="fantasma" onClick={() => setEditando(v)}>
                            Editar
                          </Boton>
                        )}
                        {puedeBorrar && (
                          <Boton variante="fantasma" onClick={() => mutBorrar.mutate(v.id)}>
                            Borrar
                          </Boton>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {paginas > 1 && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: 'var(--mch-esp-4)',
            fontSize: 'var(--mch-txt-sm)',
            color: 'var(--mch-texto-secundario)',
          }}
        >
          <span>
            Página {paginaActual} de {paginas}
          </span>
          <div style={{ display: 'flex', gap: 'var(--mch-esp-2)' }}>
            <Boton
              variante="secundario"
              disabled={desplazamiento === 0}
              onClick={() => setDesplazamiento((d) => Math.max(0, d - POR_PAGINA))}
            >
              Anterior
            </Boton>
            <Boton
              variante="secundario"
              disabled={desplazamiento + POR_PAGINA >= total}
              onClick={() => setDesplazamiento((d) => d + POR_PAGINA)}
            >
              Siguiente
            </Boton>
          </div>
        </div>
      )}

      {editando && (
        <FormularioVehiculo
          vehiculo={editando === 'nuevo' ? undefined : editando}
          onCerrar={() => setEditando(null)}
          onGuardar={async (datos) => {
            if (editando === 'nuevo') await crearVehiculo(datos);
            else await editarVehiculo(editando.id, datos);
            await refrescar();
          }}
        />
      )}
    </>
  );
}
