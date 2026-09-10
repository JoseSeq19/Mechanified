import { useEffect, useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';

import { Aviso, Boton, Campo, Dialogo, Selector } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import { listarClientes } from '@/features/clientes/api';
import type { DatosVehiculo, Vehiculo } from './api';

interface Props {
  vehiculo?: Vehiculo;
  clienteFijo?: string;
  onCerrar: () => void;
  onGuardar: (datos: DatosVehiculo) => Promise<void>;
}

const dosColumnas = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--mch-esp-4)' };

export function FormularioVehiculo({ vehiculo, clienteFijo, onCerrar, onGuardar }: Props) {
  const editando = Boolean(vehiculo);

  const [datos, setDatos] = useState<DatosVehiculo>({
    cliente_id: vehiculo?.cliente_id ?? clienteFijo ?? '',
    placa: vehiculo?.placa ?? '',
    marca: vehiculo?.marca ?? '',
    modelo: vehiculo?.modelo ?? '',
    vin: vehiculo?.vin ?? '',
    anio: vehiculo?.anio ?? null,
    color: vehiculo?.color ?? '',
    tipo_combustible: vehiculo?.tipo_combustible ?? '',
    transmision: vehiculo?.transmision ?? '',
    kilometraje_ultimo: vehiculo?.kilometraje_ultimo ?? null,
  });
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  const clientes = useQuery({
    queryKey: ['clientes', 'todos-para-selector'],
    queryFn: () => listarClientes({ limite: 200, desplazamiento: 0 }),
    enabled: !clienteFijo && !editando,
  });

  // Con un solo cliente en el taller, preseleccionarlo ahorra un clic en el
  // caso más común de un taller que arranca.
  useEffect(() => {
    const lista = clientes.data?.items ?? [];
    if (!datos.cliente_id && lista.length === 1) {
      setDatos((d) => ({ ...d, cliente_id: lista[0].id }));
    }
  }, [clientes.data, datos.cliente_id]);

  const cambiar = <K extends keyof DatosVehiculo>(campo: K, valor: DatosVehiculo[K]) =>
    setDatos((d) => ({ ...d, [campo]: valor }));

  async function alEnviar(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!datos.cliente_id) {
      setError('Hay que indicar de quién es el vehículo.');
      return;
    }
    setGuardando(true);
    try {
      await onGuardar(datos);
      onCerrar();
    } catch (err) {
      setError(
        err instanceof ErrorApi && err.esDeUsuario ? err.message : 'No se pudo guardar el vehículo.',
      );
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Dialogo
      titulo={editando ? `Editar ${vehiculo?.placa}` : 'Nuevo vehículo'}
      onCerrar={onCerrar}
      pie={
        <>
          <Boton variante="secundario" type="button" onClick={onCerrar}>
            Cancelar
          </Boton>
          <Boton type="submit" form="formulario-vehiculo" cargando={guardando}>
            {editando ? 'Guardar cambios' : 'Registrar vehículo'}
          </Boton>
        </>
      }
    >
      <form
        id="formulario-vehiculo"
        onSubmit={alEnviar}
        style={{ display: 'grid', gap: 'var(--mch-esp-4)' }}
      >
        {error && <Aviso tono="error">{error}</Aviso>}

        {!clienteFijo && !editando && (
          <Selector
            etiqueta="Propietario"
            value={datos.cliente_id}
            onChange={(e) => cambiar('cliente_id', e.target.value)}
            opciones={[
              { valor: '', texto: clientes.isLoading ? 'Cargando…' : 'Selecciona un cliente' },
              ...(clientes.data?.items ?? []).map((c) => ({ valor: c.id, texto: c.nombre })),
            ]}
          />
        )}

        <div style={dosColumnas}>
          <Campo
            etiqueta="Placa"
            required
            autoFocus
            ayuda="Se guarda en mayúsculas"
            value={datos.placa}
            onChange={(e) => cambiar('placa', e.target.value)}
          />
          <Campo
            etiqueta="VIN"
            value={datos.vin ?? ''}
            onChange={(e) => cambiar('vin', e.target.value)}
          />
        </div>

        <div style={dosColumnas}>
          <Campo
            etiqueta="Marca"
            required
            value={datos.marca}
            onChange={(e) => cambiar('marca', e.target.value)}
          />
          <Campo
            etiqueta="Modelo"
            required
            value={datos.modelo}
            onChange={(e) => cambiar('modelo', e.target.value)}
          />
        </div>

        <div style={dosColumnas}>
          <Campo
            etiqueta="Año"
            type="number"
            min={1900}
            max={2100}
            value={datos.anio ?? ''}
            onChange={(e) => cambiar('anio', e.target.value ? Number(e.target.value) : null)}
          />
          <Campo
            etiqueta="Color"
            value={datos.color ?? ''}
            onChange={(e) => cambiar('color', e.target.value)}
          />
        </div>

        <div style={dosColumnas}>
          <Selector
            etiqueta="Combustible"
            value={datos.tipo_combustible ?? ''}
            onChange={(e) => cambiar('tipo_combustible', e.target.value)}
            opciones={[
              { valor: '', texto: 'Sin especificar' },
              { valor: 'Gasolina', texto: 'Gasolina' },
              { valor: 'Diésel', texto: 'Diésel' },
              { valor: 'Gas', texto: 'Gas' },
              { valor: 'Híbrido', texto: 'Híbrido' },
              { valor: 'Eléctrico', texto: 'Eléctrico' },
            ]}
          />
          <Selector
            etiqueta="Transmisión"
            value={datos.transmision ?? ''}
            onChange={(e) => cambiar('transmision', e.target.value)}
            opciones={[
              { valor: '', texto: 'Sin especificar' },
              { valor: 'Manual', texto: 'Manual' },
              { valor: 'Automática', texto: 'Automática' },
            ]}
          />
        </div>

        <Campo
          etiqueta="Kilometraje"
          type="number"
          min={0}
          value={datos.kilometraje_ultimo ?? ''}
          onChange={(e) =>
            cambiar('kilometraje_ultimo', e.target.value ? Number(e.target.value) : null)
          }
        />
      </form>
    </Dialogo>
  );
}
