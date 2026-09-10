import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';

import { Aviso, Boton, Campo, Dialogo, Selector } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { listarClientes } from '@/features/clientes/api';
import { listarVehiculos } from '@/features/vehiculos/api';
import { listarUsuarios } from '@/features/usuarios/api';
import type { DatosOrden } from './api';

interface Props {
  onCerrar: () => void;
  onGuardar: (datos: DatosOrden) => Promise<void>;
}

const dosColumnas = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--mch-esp-4)' };

export function FormularioOrden({ onCerrar, onGuardar }: Props) {
  const [clienteId, setClienteId] = useState('');
  const [datos, setDatos] = useState<DatosOrden>({
    cliente_id: '',
    vehiculo_id: '',
    motivo_ingreso: '',
  });
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  const clientes = useQuery({
    queryKey: ['clientes', 'selector'],
    queryFn: () => listarClientes({ limite: 200, desplazamiento: 0 }),
  });

  // Los vehículos se piden filtrados por el cliente elegido. Es lo que evita
  // que se pueda abrir una orden con el carro de otra persona, que la base
  // rechazaría después con un error difícil de entender.
  const vehiculos = useQuery({
    queryKey: ['vehiculos', 'de-cliente', clienteId],
    queryFn: () => listarVehiculos({ clienteId, limite: 100, desplazamiento: 0 }),
    enabled: Boolean(clienteId),
  });

  const tecnicos = useQuery({
    queryKey: ['usuarios', 'tecnico'],
    queryFn: () => listarUsuarios('tecnico'),
  });

  const listaVehiculos = useMemo(() => vehiculos.data?.items ?? [], [vehiculos.data]);

  // Al cambiar de cliente el vehículo anterior deja de valer.
  useEffect(() => {
    setDatos((d) => ({
      ...d,
      cliente_id: clienteId,
      vehiculo_id: listaVehiculos.length === 1 ? listaVehiculos[0].id : '',
    }));
  }, [clienteId, listaVehiculos]);

  const cambiar = <K extends keyof DatosOrden>(campo: K, valor: DatosOrden[K]) =>
    setDatos((d) => ({ ...d, [campo]: valor }));

  const sinVehiculos = Boolean(clienteId) && !vehiculos.isLoading && listaVehiculos.length === 0;

  async function alEnviar(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!datos.cliente_id || !datos.vehiculo_id) {
      setError('Hay que elegir el cliente y el vehículo que entra.');
      return;
    }
    setGuardando(true);
    try {
      await onGuardar(datos);
      onCerrar();
    } catch (err) {
      setError(
        err instanceof ErrorApi && err.esDeUsuario ? err.message : 'No se pudo abrir la orden.',
      );
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Dialogo
      titulo="Recibir un vehículo"
      onCerrar={onCerrar}
      pie={
        <>
          <Boton variante="secundario" type="button" onClick={onCerrar}>
            Cancelar
          </Boton>
          <Boton type="submit" form="formulario-orden" cargando={guardando} disabled={sinVehiculos}>
            Abrir orden
          </Boton>
        </>
      }
    >
      <form
        id="formulario-orden"
        onSubmit={alEnviar}
        style={{ display: 'grid', gap: 'var(--mch-esp-4)' }}
      >
        {error && <Aviso tono="error">{error}</Aviso>}

        <Selector
          etiqueta="Cliente"
          value={clienteId}
          onChange={(e) => setClienteId(e.target.value)}
          opciones={[
            { valor: '', texto: clientes.isLoading ? 'Cargando…' : 'Selecciona un cliente' },
            ...(clientes.data?.items ?? []).map((c) => ({ valor: c.id, texto: c.nombre })),
          ]}
        />

        <Selector
          etiqueta="Vehículo"
          value={datos.vehiculo_id}
          disabled={!clienteId || listaVehiculos.length === 0}
          onChange={(e) => cambiar('vehiculo_id', e.target.value)}
          opciones={[
            {
              valor: '',
              texto: !clienteId
                ? 'Elige primero el cliente'
                : vehiculos.isLoading
                  ? 'Cargando…'
                  : listaVehiculos.length === 0
                    ? 'Este cliente no tiene vehículos'
                    : 'Selecciona un vehículo',
            },
            ...listaVehiculos.map((v) => ({
              valor: v.id,
              texto: `${v.placa} — ${v.marca} ${v.modelo}`,
            })),
          ]}
        />

        {sinVehiculos && (
          <Aviso tono="alerta">
            Ese cliente no tiene vehículos registrados. Regístraselo en la sección Vehículos
            antes de abrir la orden.
          </Aviso>
        )}

        <Campo
          etiqueta="Motivo de ingreso"
          required
          ayuda="Lo que reporta el cliente, con sus palabras"
          value={datos.motivo_ingreso}
          onChange={(e) => cambiar('motivo_ingreso', e.target.value)}
        />

        <div style={dosColumnas}>
          <Campo
            etiqueta="Kilometraje de entrada"
            type="number"
            min={0}
            value={datos.kilometraje_ingreso ?? ''}
            onChange={(e) =>
              cambiar('kilometraje_ingreso', e.target.value ? Number(e.target.value) : null)
            }
          />
          <Campo
            etiqueta="Combustible (%)"
            type="number"
            min={0}
            max={100}
            value={datos.nivel_combustible ?? ''}
            onChange={(e) =>
              cambiar('nivel_combustible', e.target.value ? Number(e.target.value) : null)
            }
          />
        </div>

        <div style={dosColumnas}>
          <Selector
            etiqueta="Técnico asignado"
            value={datos.tecnico_id ?? ''}
            onChange={(e) => cambiar('tecnico_id', e.target.value || null)}
            opciones={[
              { valor: '', texto: 'Sin asignar' },
              ...(tecnicos.data ?? []).map((t) => ({ valor: t.id, texto: t.nombre_completo })),
            ]}
          />
          <Campo
            etiqueta="Fecha prometida"
            type="datetime-local"
            value={datos.fecha_promesa?.slice(0, 16) ?? ''}
            onChange={(e) =>
              cambiar('fecha_promesa', e.target.value ? new Date(e.target.value).toISOString() : null)
            }
          />
        </div>

        <Campo
          etiqueta="Notas internas"
          ayuda="No se muestran al cliente"
          value={datos.notas_internas ?? ''}
          onChange={(e) => cambiar('notas_internas', e.target.value)}
        />
      </form>
    </Dialogo>
  );
}
