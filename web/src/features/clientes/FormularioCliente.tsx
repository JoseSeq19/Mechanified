import { useState, type FormEvent } from 'react';

import { Aviso, Boton, Campo, Dialogo, Selector } from '@/components/ui';
import { ErrorApi } from '@/lib/api';
import type { Cliente, DatosCliente, TipoCliente } from './api';

interface Props {
  cliente?: Cliente;
  onCerrar: () => void;
  onGuardar: (datos: DatosCliente) => Promise<void>;
}

export function FormularioCliente({ cliente, onCerrar, onGuardar }: Props) {
  const editando = Boolean(cliente);

  const [datos, setDatos] = useState<DatosCliente>({
    nombre: cliente?.nombre ?? '',
    tipo: cliente?.tipo ?? 'persona',
    documento: cliente?.documento ?? '',
    telefono: cliente?.telefono ?? '',
    email: cliente?.email ?? '',
    direccion: cliente?.direccion ?? '',
    notas: cliente?.notas ?? '',
  });
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  const cambiar = <K extends keyof DatosCliente>(campo: K, valor: DatosCliente[K]) =>
    setDatos((d) => ({ ...d, [campo]: valor }));

  async function alEnviar(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setGuardando(true);
    try {
      await onGuardar(datos);
      onCerrar();
    } catch (err) {
      // Los 4xx son culpa del dato que se escribió y su mensaje ya viene
      // redactado por el backend; el resto es un fallo y no conviene mostrarlo
      // crudo.
      setError(
        err instanceof ErrorApi && err.esDeUsuario
          ? err.message
          : 'No se pudo guardar. Revisa que el backend esté corriendo.',
      );
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Dialogo
      titulo={editando ? 'Editar cliente' : 'Nuevo cliente'}
      onCerrar={onCerrar}
      pie={
        <>
          <Boton variante="secundario" type="button" onClick={onCerrar}>
            Cancelar
          </Boton>
          <Boton type="submit" form="formulario-cliente" cargando={guardando}>
            {editando ? 'Guardar cambios' : 'Registrar cliente'}
          </Boton>
        </>
      }
    >
      <form id="formulario-cliente" onSubmit={alEnviar} style={{ display: 'grid', gap: 'var(--mch-esp-4)' }}>
        {error && <Aviso tono="error">{error}</Aviso>}

        <Campo
          etiqueta="Nombre o razón social"
          required
          autoFocus
          value={datos.nombre}
          onChange={(e) => cambiar('nombre', e.target.value)}
        />

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--mch-esp-4)' }}>
          <Selector
            etiqueta="Tipo"
            value={datos.tipo}
            onChange={(e) => cambiar('tipo', e.target.value as TipoCliente)}
            opciones={[
              { valor: 'persona', texto: 'Persona' },
              { valor: 'empresa', texto: 'Empresa' },
            ]}
          />
          <Campo
            etiqueta="Documento"
            ayuda="Único dentro del taller"
            value={datos.documento ?? ''}
            onChange={(e) => cambiar('documento', e.target.value)}
          />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--mch-esp-4)' }}>
          <Campo
            etiqueta="Teléfono"
            value={datos.telefono ?? ''}
            onChange={(e) => cambiar('telefono', e.target.value)}
          />
          <Campo
            etiqueta="Correo"
            type="email"
            value={datos.email ?? ''}
            onChange={(e) => cambiar('email', e.target.value)}
          />
        </div>

        <Campo
          etiqueta="Dirección"
          value={datos.direccion ?? ''}
          onChange={(e) => cambiar('direccion', e.target.value)}
        />
        <Campo
          etiqueta="Notas"
          value={datos.notas ?? ''}
          onChange={(e) => cambiar('notas', e.target.value)}
        />
      </form>
    </Dialogo>
  );
}
