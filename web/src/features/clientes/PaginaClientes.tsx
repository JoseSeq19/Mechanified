import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Aviso, Boton, Cargando, Distintivo, Vacio } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { useSesion } from '@/app/sesion';
import { FormularioCliente } from './FormularioCliente';
import { borrarCliente, crearCliente, editarCliente, listarClientes, type Cliente } from './api';

const POR_PAGINA = 15;

export function PaginaClientes() {
  const { claims } = useSesion();
  const clienteQuery = useQueryClient();

  const [texto, setTexto] = useState('');
  const [busqueda, setBusqueda] = useState('');
  const [incluirInactivos, setIncluirInactivos] = useState(false);
  const [desplazamiento, setDesplazamiento] = useState(0);
  const [editando, setEditando] = useState<Cliente | 'nuevo' | null>(null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);

  // El backend ignora los términos de menos de 3 caracteres, así que no tiene
  // sentido consultar mientras se escriben las primeras letras.
  useEffect(() => {
    const t = setTimeout(() => {
      setBusqueda(texto.trim().length >= 3 ? texto.trim() : '');
      setDesplazamiento(0);
    }, 300);
    return () => clearTimeout(t);
  }, [texto]);

  const filtros = { busqueda, incluirInactivos, limite: POR_PAGINA, desplazamiento };

  const consulta = useQuery({
    queryKey: ['clientes', filtros],
    queryFn: () => listarClientes(filtros),
  });

  const refrescar = () => clienteQuery.invalidateQueries({ queryKey: ['clientes'] });

  const mutBorrar = useMutation({
    mutationFn: borrarCliente,
    onSuccess: () => {
      setErrorAccion(null);
      refrescar();
    },
    onError: (e) =>
      setErrorAccion(e instanceof ErrorApi ? e.message : 'No se pudo borrar el cliente.'),
  });

  const mutActivo = useMutation({
    mutationFn: ({ id, activo }: { id: string; activo: boolean }) => editarCliente(id, { activo }),
    onSuccess: refrescar,
  });

  const puedeEscribir =
    claims?.rol === 'admin_taller' || claims?.rol === 'asesor_servicio';
  const puedeBorrar = claims?.rol === 'admin_taller';

  const total = consulta.data?.total ?? 0;
  const paginaActual = Math.floor(desplazamiento / POR_PAGINA) + 1;
  const paginas = Math.max(1, Math.ceil(total / POR_PAGINA));

  const cuerpo = useMemo(() => {
    if (consulta.isLoading) return <Cargando />;

    if (consulta.isError) {
      const e = consulta.error;
      return (
        <div style={{ padding: 'var(--mch-esp-6)' }}>
          <Aviso tono="error">
            {e instanceof ErrorApi ? e.message : 'No se pudieron cargar los clientes.'}
          </Aviso>
        </div>
      );
    }

    const items = consulta.data?.items ?? [];
    if (items.length === 0) {
      return busqueda ? (
        <Vacio titulo="Sin resultados" detalle={`Ningún cliente coincide con "${busqueda}".`} />
      ) : (
        <Vacio
          titulo="Todavía no hay clientes"
          detalle="Registra el primero para empezar a abrir órdenes de servicio."
        />
      );
    }

    return (
      <div className="mch-tabla-envoltura">
        <table className="mch-tabla">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Documento</th>
              <th>Contacto</th>
              <th>Estado</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id}>
                <td>
                  <div style={{ fontWeight: 560 }}>{c.nombre}</div>
                  <div style={{ color: 'var(--mch-texto-secundario)', fontSize: 'var(--mch-txt-xs)' }}>
                    {c.tipo === 'empresa' ? 'Empresa' : 'Persona'}
                  </div>
                </td>
                <td style={{ fontFamily: 'var(--mch-fuente-mono)', fontSize: 'var(--mch-txt-xs)' }}>
                  {c.documento ?? '—'}
                </td>
                <td>
                  <div>{c.telefono ?? '—'}</div>
                  {c.email && (
                    <div style={{ color: 'var(--mch-texto-secundario)', fontSize: 'var(--mch-txt-xs)' }}>
                      {c.email}
                    </div>
                  )}
                </td>
                <td>
                  <Distintivo tono={c.activo ? 'activo' : 'inactivo'}>
                    {c.activo ? 'Activo' : 'Inactivo'}
                  </Distintivo>
                </td>
                <td>
                  <div className="mch-tabla__acciones">
                    {puedeEscribir && (
                      <>
                        <Boton variante="fantasma" onClick={() => setEditando(c)}>
                          Editar
                        </Boton>
                        <Boton
                          variante="fantasma"
                          onClick={() => mutActivo.mutate({ id: c.id, activo: !c.activo })}
                        >
                          {c.activo ? 'Desactivar' : 'Reactivar'}
                        </Boton>
                      </>
                    )}
                    {puedeBorrar && (
                      <Boton variante="fantasma" onClick={() => mutBorrar.mutate(c.id)}>
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
    );
  }, [consulta.isLoading, consulta.isError, consulta.error, consulta.data, busqueda, puedeEscribir, puedeBorrar, mutActivo, mutBorrar]);

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
          <h1 style={{ fontSize: 'var(--mch-txt-xl)' }}>Clientes</h1>
          <p style={{ margin: 'var(--mch-esp-1) 0 0', color: 'var(--mch-texto-secundario)', fontSize: 'var(--mch-txt-sm)' }}>
            {total} {total === 1 ? 'cliente registrado' : 'clientes registrados'}
          </p>
        </div>
        {puedeEscribir && <Boton onClick={() => setEditando('nuevo')}>Nuevo cliente</Boton>}
      </header>

      <div
        style={{
          display: 'flex',
          gap: 'var(--mch-esp-4)',
          alignItems: 'center',
          flexWrap: 'wrap',
          marginBottom: 'var(--mch-esp-4)',
        }}
      >
        <input
          className="mch-campo__control"
          style={{ maxWidth: 320 }}
          type="search"
          placeholder="Buscar por nombre, documento o teléfono…"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          aria-label="Buscar clientes"
        />
        <label
          style={{
            display: 'flex',
            gap: 'var(--mch-esp-2)',
            alignItems: 'center',
            fontSize: 'var(--mch-txt-sm)',
            color: 'var(--mch-texto-secundario)',
          }}
        >
          <input
            type="checkbox"
            checked={incluirInactivos}
            onChange={(e) => {
              setIncluirInactivos(e.target.checked);
              setDesplazamiento(0);
            }}
          />
          Incluir inactivos
        </label>
        {texto.length > 0 && texto.trim().length < 3 && (
          <span style={{ fontSize: 'var(--mch-txt-xs)', color: 'var(--mch-texto-secundario)' }}>
            Escribe al menos 3 caracteres
          </span>
        )}
      </div>

      {errorAccion && (
        <div style={{ marginBottom: 'var(--mch-esp-4)' }}>
          <Aviso tono="alerta">{errorAccion}</Aviso>
        </div>
      )}

      <div className="mch-panel">{cuerpo}</div>

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
        <FormularioCliente
          cliente={editando === 'nuevo' ? undefined : editando}
          onCerrar={() => setEditando(null)}
          onGuardar={async (datos) => {
            if (editando === 'nuevo') await crearCliente(datos);
            else await editarCliente(editando.id, datos);
            await refrescar();
          }}
        />
      )}
    </>
  );
}
