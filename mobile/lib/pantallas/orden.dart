/// La ficha de la orden en el móvil.
///
/// Lo mismo que la ficha de la web, recortado a lo que se hace de pie junto al
/// coche: mover la orden al paso siguiente, anotar lo que se encontró, cargar
/// las horas, pedir una pieza y hacer fotos. Lo que no está —presupuestos,
/// control de calidad, encuestas— es trabajo de mostrador, y se hace mejor en
/// una pantalla grande.
///
/// Los botones de estado no los decide esta app: vienen en
/// `transiciones_posibles`, que el backend calcula con la máquina de estados y
/// el rol de quien pregunta. Aquí se pinta uno por cada uno, y así ninguna
/// regla del flujo vive en dos sitios.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../datos/modelos.dart';
import '../datos/repositorio.dart';
import '../nucleo/api.dart';
import '../nucleo/formato.dart';
import '../nucleo/sesion.dart';
import '../nucleo/tema.dart';
import 'comun.dart';
import 'fotos.dart';

class PantallaOrden extends ConsumerWidget {
  const PantallaOrden({super.key, required this.ordenId});

  final String ordenId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final orden = ref.watch(ordenProvider(ordenId));

    return Scaffold(
      appBar: AppBar(
        title: Text(orden.maybeWhen(data: (o) => o.folio, orElse: () => 'Orden')),
      ),
      body: orden.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Padding(
          padding: const EdgeInsets.all(24),
          child: Aviso(
            tono: Tonos.error,
            texto: e is ErrorApi ? e.mensaje : 'No se pudo abrir la orden.',
          ),
        ),
        data: (o) => RefreshIndicator(
          onRefresh: () async {
            ref.invalidate(ordenProvider(ordenId));
            ref.invalidate(diagnosticosProvider(ordenId));
            ref.invalidate(manoObraProvider(ordenId));
            ref.invalidate(repuestosProvider(ordenId));
            ref.invalidate(adjuntosProvider(ordenId));
          },
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.only(bottom: 32),
            children: [
              _Cabecera(orden: o),
              _SiguientePaso(orden: o),
              _Datos(orden: o),
              _SeccionDiagnostico(ordenId: ordenId, cerrada: o.cerrada),
              _SeccionManoObra(ordenId: ordenId, cerrada: o.cerrada),
              _SeccionRepuestos(ordenId: ordenId, cerrada: o.cerrada),
              SeccionFotos(ordenId: ordenId),
            ],
          ),
        ),
      ),
    );
  }
}

class _Cabecera extends StatelessWidget {
  const _Cabecera({required this.orden});

  final Orden orden;

  @override
  Widget build(BuildContext context) {
    final r = orden.resumen;

    return Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '${r.vehiculoPlaca} · ${r.vehiculoDescripcion}',
                  style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
                ),
              ),
              if (r.atrasada) const Distintivo(texto: 'Atrasada', tono: Tonos.alerta),
            ],
          ),
          const SizedBox(height: 4),
          Text(r.clienteNombre, style: const TextStyle(color: Tonos.textoSecundario)),
          const SizedBox(height: 10),
          Row(
            children: [
              Distintivo(
                texto: etiquetasEstado[orden.estado] ?? orden.estado,
                tono: Tonos.porEstado(orden.estado),
              ),
              const Spacer(),
              Text(
                formatearMoneda(r.total),
                style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// Las transiciones que este usuario puede hacer ahora mismo.
class _SiguientePaso extends ConsumerStatefulWidget {
  const _SiguientePaso({required this.orden});

  final Orden orden;

  @override
  ConsumerState<_SiguientePaso> createState() => _SiguientePasoState();
}

class _SiguientePasoState extends ConsumerState<_SiguientePaso> {
  bool _moviendo = false;

  Future<void> _mover(String estado) async {
    final etiqueta = etiquetasEstado[estado] ?? estado;
    final exigeMotivo = exigenComentario.contains(estado);

    final comentario = await mostrarHoja<String>(
      context: context,
      titulo: estado == 'cancelado' ? 'Cancelar la orden' : 'Pasar a $etiqueta',
      contenido: (contexto) => _FormularioComentario(
        exigeMotivo: exigeMotivo,
        etiquetaBoton: estado == 'cancelado' ? 'Cancelar la orden' : 'Confirmar',
      ),
    );
    if (comentario == null) return; // se cerró la hoja sin confirmar

    setState(() => _moviendo = true);
    try {
      await ref
          .read(repositorioProvider)
          .cambiarEstado(widget.orden.id, estado, comentario: comentario);
      ref.invalidate(ordenProvider(widget.orden.id));
      ref.invalidate(ordenesProvider);
      if (mounted) avisar(context, 'La orden pasó a $etiqueta.');
    } on ErrorApi catch (e) {
      if (mounted) avisar(context, e.mensaje, esError: true);
    } finally {
      if (mounted) setState(() => _moviendo = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final posibles = widget.orden.transicionesPosibles;

    return Seccion(
      titulo: 'Siguiente paso',
      children: [
        if (posibles.isEmpty)
          Vacio(
            texto: widget.orden.cerrada
                ? 'La orden está cerrada.'
                : 'Tu rol no puede mover la orden desde este estado.',
          )
        else
          Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              children: [
                for (final estado in posibles)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: estado == 'cancelado'
                        ? OutlinedButton(
                            onPressed: _moviendo ? null : () => _mover(estado),
                            child: const Text('Cancelar orden'),
                          )
                        : FilledButton(
                            onPressed: _moviendo ? null : () => _mover(estado),
                            child: Text('Pasar a ${etiquetasEstado[estado] ?? estado}'),
                          ),
                  ),
              ],
            ),
          ),
      ],
    );
  }
}

class _FormularioComentario extends StatefulWidget {
  const _FormularioComentario({required this.exigeMotivo, required this.etiquetaBoton});

  final bool exigeMotivo;
  final String etiquetaBoton;

  @override
  State<_FormularioComentario> createState() => _FormularioComentarioState();
}

class _FormularioComentarioState extends State<_FormularioComentario> {
  final _texto = TextEditingController();

  @override
  void dispose() {
    _texto.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final valido = !widget.exigeMotivo || _texto.text.trim().isNotEmpty;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: _texto,
          autofocus: widget.exigeMotivo,
          maxLines: 3,
          decoration: InputDecoration(
            labelText: widget.exigeMotivo ? 'Motivo (obligatorio)' : 'Comentario (opcional)',
            helperText: 'Queda en el historial de la orden',
          ),
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: 14),
        FilledButton(
          onPressed: valido ? () => Navigator.pop(context, _texto.text.trim()) : null,
          child: Text(widget.etiquetaBoton),
        ),
      ],
    );
  }
}

class _Datos extends StatelessWidget {
  const _Datos({required this.orden});

  final Orden orden;

  @override
  Widget build(BuildContext context) {
    final r = orden.resumen;

    return Seccion(
      titulo: 'Datos',
      children: [
        Linea(titulo: 'Motivo de ingreso', detalle: orden.motivoIngreso),
        const Divider(height: 1),
        Linea(
          titulo: 'Kilometraje',
          detalle: orden.kilometrajeIngreso == null
              ? '—'
              : formatearNumero(orden.kilometrajeIngreso, decimales: 0),
        ),
        const Divider(height: 1),
        Linea(
          titulo: 'Combustible',
          detalle: orden.nivelCombustible == null ? '—' : '${orden.nivelCombustible}%',
        ),
        const Divider(height: 1),
        Linea(titulo: 'Ingreso', detalle: formatearFecha(r.fechaIngreso, conHora: true)),
        const Divider(height: 1),
        Linea(titulo: 'Prometida', detalle: formatearFecha(r.fechaPromesa, conHora: true)),
        const Divider(height: 1),
        Linea(titulo: 'Técnico', detalle: r.tecnicoNombre ?? 'Sin asignar'),
        const Divider(height: 1),
        Linea(titulo: 'Asesor', detalle: orden.asesorNombre ?? 'Sin asignar'),
        const Divider(height: 1),
        Linea(
          titulo: 'Mano de obra',
          importe: formatearMoneda(orden.totalManoObra),
        ),
        const Divider(height: 1),
        Linea(titulo: 'Repuestos', importe: formatearMoneda(orden.totalRepuestos)),
        if (orden.inventarioIngreso.isNotEmpty) ...[
          const Divider(height: 1),
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'INVENTARIO RECIBIDO',
                  style: TextStyle(
                    fontSize: 11,
                    letterSpacing: 0.6,
                    color: Tonos.textoSecundario,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 6),
                // Lo que se revisó con el cliente al recibir el coche, que es
                // con lo que se compara al entregarlo.
                for (final par in orden.inventarioIngreso.entries)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 2),
                    child: Text(
                      par.value.isEmpty ? par.key : '${par.key} · ${par.value}',
                      style: const TextStyle(fontSize: 13),
                    ),
                  ),
              ],
            ),
          ),
        ],
        if (orden.motivoCancelacion != null) ...[
          const Divider(height: 1),
          Padding(
            padding: const EdgeInsets.all(14),
            child: Aviso(tono: Tonos.alerta, texto: 'Cancelada: ${orden.motivoCancelacion}'),
          ),
        ],
      ],
    );
  }
}

// -----------------------------------------------------------------------------
// Diagnóstico
// -----------------------------------------------------------------------------

class _SeccionDiagnostico extends ConsumerWidget {
  const _SeccionDiagnostico({required this.ordenId, required this.cerrada});

  final String ordenId;
  final bool cerrada;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final claims = ref.watch(claimsProvider);
    final diagnosticos = ref.watch(diagnosticosProvider(ordenId));

    // El diagnóstico lo escribe el técnico; administración también, por si hay
    // que corregir algo. Es la misma regla que aplica RLS.
    final puedeEscribir = !cerrada && ((claims?.esTecnico ?? false) || (claims?.esAdmin ?? false));

    return Seccion(
      titulo: 'Diagnóstico',
      accion: puedeEscribir
          ? IconButton.filled(
              onPressed: () => _nuevoDiagnostico(context, ref),
              icon: const Icon(Icons.add),
              tooltip: 'Registrar diagnóstico',
            )
          : null,
      children: diagnosticos.when(
        loading: () => const [
          Padding(padding: EdgeInsets.all(14), child: Center(child: CircularProgressIndicator())),
        ],
        error: (e, _) => [
          Padding(
            padding: const EdgeInsets.all(14),
            child: Aviso(
              tono: Tonos.error,
              texto: e is ErrorApi ? e.mensaje : 'No se pudo cargar el diagnóstico.',
            ),
          ),
        ],
        data: (lista) {
          if (lista.isEmpty) {
            return [
              Vacio(
                texto: cerrada
                    ? 'La orden se cerró sin diagnóstico registrado.'
                    : 'Anota aquí lo que encontraste al revisar el vehículo.',
              ),
            ];
          }

          return [
            for (final d in lista) ...[
              Linea(
                titulo: d.resumen,
                detalle: '${d.tecnicoNombre ?? 'Sin técnico'} · '
                    '${formatearNumero(d.horasEstimadas)} h estimadas · ${haceCuanto(d.creadoEn)}',
                alFinal: puedeEscribir
                    ? IconButton(
                        onPressed: () => _nuevoHallazgo(context, ref, d.id),
                        icon: const Icon(Icons.add_circle_outline),
                        tooltip: 'Añadir hallazgo',
                      )
                    : null,
              ),
              for (final h in d.hallazgos)
                Padding(
                  padding: const EdgeInsets.fromLTRB(28, 0, 14, 10),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        margin: const EdgeInsets.only(top: 6, right: 8),
                        width: 8,
                        height: 8,
                        decoration: BoxDecoration(
                          color: _tonoSeveridad(h.severidad),
                          shape: BoxShape.circle,
                        ),
                      ),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('${h.sistema}: ${h.descripcion}'),
                            Text(
                              h.requiereRepuesto
                                  ? '${h.severidadEtiqueta} · necesita repuesto'
                                  : h.severidadEtiqueta,
                              style: const TextStyle(
                                fontSize: 12,
                                color: Tonos.textoSecundario,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              const Divider(height: 1),
            ],
          ];
        },
      ),
    );
  }

  static Color _tonoSeveridad(String severidad) {
    switch (severidad) {
      case 'critica':
        return Tonos.error;
      case 'moderada':
        return Tonos.alerta;
      default:
        return Tonos.textoSecundario;
    }
  }

  Future<void> _nuevoDiagnostico(BuildContext context, WidgetRef ref) async {
    final datos = await mostrarHoja<_DatosDiagnostico>(
      context: context,
      titulo: 'Registrar diagnóstico',
      contenido: (_) => const _FormularioDiagnostico(),
    );
    if (datos == null) return;

    try {
      await ref.read(repositorioProvider).crearDiagnostico(
            ordenId,
            resumen: datos.resumen,
            horasEstimadas: datos.horas,
          );
      ref.invalidate(diagnosticosProvider(ordenId));
      if (context.mounted) avisar(context, 'Diagnóstico registrado.');
    } on ErrorApi catch (e) {
      if (context.mounted) avisar(context, e.mensaje, esError: true);
    }
  }

  Future<void> _nuevoHallazgo(BuildContext context, WidgetRef ref, String diagnosticoId) async {
    final datos = await mostrarHoja<_DatosHallazgo>(
      context: context,
      titulo: 'Añadir hallazgo',
      contenido: (_) => const _FormularioHallazgo(),
    );
    if (datos == null) return;

    try {
      await ref.read(repositorioProvider).agregarHallazgo(
            diagnosticoId,
            sistema: datos.sistema,
            descripcion: datos.descripcion,
            severidad: datos.severidad,
            requiereRepuesto: datos.requiereRepuesto,
          );
      ref.invalidate(diagnosticosProvider(ordenId));
      if (context.mounted) avisar(context, 'Hallazgo añadido.');
    } on ErrorApi catch (e) {
      if (context.mounted) avisar(context, e.mensaje, esError: true);
    }
  }
}

class _DatosDiagnostico {
  const _DatosDiagnostico(this.resumen, this.horas);
  final String resumen;
  final double horas;
}

class _FormularioDiagnostico extends StatefulWidget {
  const _FormularioDiagnostico();

  @override
  State<_FormularioDiagnostico> createState() => _FormularioDiagnosticoState();
}

class _FormularioDiagnosticoState extends State<_FormularioDiagnostico> {
  final _resumen = TextEditingController();
  final _horas = TextEditingController();

  @override
  void dispose() {
    _resumen.dispose();
    _horas.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final resumen = _resumen.text.trim();
    final horas = double.tryParse(_horas.text.replaceAll(',', '.'));
    final valido = resumen.length >= 3 && horas != null && horas >= 0;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: _resumen,
          autofocus: true,
          maxLines: 3,
          decoration: const InputDecoration(
            labelText: 'Qué encontraste',
            helperText: 'Lo que resume la revisión. Los hallazgos se añaden después.',
          ),
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _horas,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(labelText: 'Horas estimadas'),
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: 14),
        FilledButton(
          onPressed: valido
              ? () => Navigator.pop(context, _DatosDiagnostico(resumen, horas))
              : null,
          child: const Text('Registrar'),
        ),
      ],
    );
  }
}

class _DatosHallazgo {
  const _DatosHallazgo(this.sistema, this.descripcion, this.severidad, this.requiereRepuesto);
  final String sistema;
  final String descripcion;
  final String severidad;
  final bool requiereRepuesto;
}

class _FormularioHallazgo extends StatefulWidget {
  const _FormularioHallazgo();

  @override
  State<_FormularioHallazgo> createState() => _FormularioHallazgoState();
}

class _FormularioHallazgoState extends State<_FormularioHallazgo> {
  final _sistema = TextEditingController();
  final _descripcion = TextEditingController();
  String _severidad = 'moderada';
  bool _requiereRepuesto = false;

  @override
  void dispose() {
    _sistema.dispose();
    _descripcion.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final sistema = _sistema.text.trim();
    final descripcion = _descripcion.text.trim();
    final valido = sistema.isNotEmpty && descripcion.length >= 3;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: _sistema,
          autofocus: true,
          decoration: const InputDecoration(
            labelText: 'Sistema',
            hintText: 'Frenos, suspensión, motor…',
          ),
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _descripcion,
          maxLines: 2,
          decoration: const InputDecoration(labelText: 'Qué le pasa'),
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          value: _severidad,
          decoration: const InputDecoration(labelText: 'Severidad'),
          items: const [
            DropdownMenuItem(value: 'leve', child: Text('Leve')),
            DropdownMenuItem(value: 'moderada', child: Text('Moderada')),
            DropdownMenuItem(value: 'critica', child: Text('Crítica')),
          ],
          onChanged: (valor) => setState(() => _severidad = valor ?? 'moderada'),
        ),
        SwitchListTile(
          value: _requiereRepuesto,
          onChanged: (valor) => setState(() => _requiereRepuesto = valor),
          title: const Text('Necesita repuesto'),
          contentPadding: EdgeInsets.zero,
        ),
        const SizedBox(height: 6),
        FilledButton(
          onPressed: valido
              ? () => Navigator.pop(
                    context,
                    _DatosHallazgo(sistema, descripcion, _severidad, _requiereRepuesto),
                  )
              : null,
          child: const Text('Añadir'),
        ),
      ],
    );
  }
}

// -----------------------------------------------------------------------------
// Mano de obra
// -----------------------------------------------------------------------------

class _SeccionManoObra extends ConsumerWidget {
  const _SeccionManoObra({required this.ordenId, required this.cerrada});

  final String ordenId;
  final bool cerrada;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final claims = ref.watch(claimsProvider);
    final manoObra = ref.watch(manoObraProvider(ordenId));

    // Técnico, asesoría y administración: los mismos que deja la política de
    // `orden_mano_obra`.
    final puedeEscribir = !cerrada &&
        ((claims?.esTecnico ?? false) || (claims?.esAsesor ?? false) || (claims?.esAdmin ?? false));

    return Seccion(
      titulo: 'Mano de obra',
      resumen: manoObra.maybeWhen(
        data: (m) => '${formatearNumero(m.totalHoras)} h · ${formatearMoneda(m.total)}',
        orElse: () => null,
      ),
      accion: puedeEscribir
          ? IconButton.filled(
              onPressed: () => _cargar(context, ref),
              icon: const Icon(Icons.add),
              tooltip: 'Cargar trabajo',
            )
          : null,
      children: manoObra.when(
        loading: () => const [
          Padding(padding: EdgeInsets.all(14), child: Center(child: CircularProgressIndicator())),
        ],
        error: (e, _) => [
          Padding(
            padding: const EdgeInsets.all(14),
            child: Aviso(
              tono: Tonos.error,
              texto: e is ErrorApi ? e.mensaje : 'No se pudo cargar el trabajo.',
            ),
          ),
        ],
        data: (m) => m.lineas.isEmpty
            ? [
                Vacio(
                  texto: cerrada
                      ? 'No se cargó trabajo a esta orden.'
                      : 'Cada línea son horas por la tarifa del taller.',
                ),
              ]
            : [
                for (final l in m.lineas) ...[
                  Linea(
                    titulo: l.descripcion,
                    detalle: '${formatearNumero(l.horas)} h × ${formatearMoneda(l.tarifaHora)}'
                        '${l.tecnicoNombre == null ? '' : ' · ${l.tecnicoNombre}'}',
                    importe: formatearMoneda(l.subtotal),
                  ),
                  const Divider(height: 1),
                ],
              ],
      ),
    );
  }

  Future<void> _cargar(BuildContext context, WidgetRef ref) async {
    final datos = await mostrarHoja<_DatosTrabajo>(
      context: context,
      titulo: 'Cargar trabajo',
      contenido: (_) => const _FormularioTrabajo(),
    );
    if (datos == null) return;

    final claims = ref.read(claimsProvider);
    try {
      await ref.read(repositorioProvider).cargarManoObra(
            ordenId,
            descripcion: datos.descripcion,
            horas: datos.horas,
            // Si lo registra un técnico, el trabajo es suyo. Es lo que hace que
            // el panel pueda medir productividad sin que nadie lo reasigne a
            // mano después.
            tecnicoId: (claims?.esTecnico ?? false) ? claims?.sub : null,
          );
      ref.invalidate(manoObraProvider(ordenId));
      ref.invalidate(ordenProvider(ordenId));
      if (context.mounted) avisar(context, 'Trabajo cargado.');
    } on ErrorApi catch (e) {
      if (context.mounted) avisar(context, e.mensaje, esError: true);
    }
  }
}

class _DatosTrabajo {
  const _DatosTrabajo(this.descripcion, this.horas);
  final String descripcion;
  final double horas;
}

class _FormularioTrabajo extends ConsumerStatefulWidget {
  const _FormularioTrabajo();

  @override
  ConsumerState<_FormularioTrabajo> createState() => _FormularioTrabajoState();
}

class _FormularioTrabajoState extends ConsumerState<_FormularioTrabajo> {
  final _descripcion = TextEditingController();
  final _horas = TextEditingController();

  @override
  void dispose() {
    _descripcion.dispose();
    _horas.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final taller = ref.watch(tallerProvider);
    final descripcion = _descripcion.text.trim();
    final horas = double.tryParse(_horas.text.replaceAll(',', '.'));
    final valido = descripcion.length >= 3 && horas != null && horas > 0;

    final tarifa = taller.maybeWhen(data: (t) => t.tarifaHora, orElse: () => null);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: _descripcion,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Qué se hizo'),
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _horas,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(
            labelText: 'Horas',
            // La tarifa no se pide: la pone el taller y queda congelada en la
            // línea. Se muestra para que nadie tenga que adivinar el importe.
            helperText: tarifa == null
                ? 'Se aplica la tarifa del taller'
                : 'A ${formatearMoneda(tarifa)} la hora'
                    '${horas == null ? '' : ' · ${formatearMoneda(horas * (double.tryParse(tarifa) ?? 0))}'}',
          ),
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: 14),
        FilledButton(
          onPressed:
              valido ? () => Navigator.pop(context, _DatosTrabajo(descripcion, horas)) : null,
          child: const Text('Cargar'),
        ),
      ],
    );
  }
}

// -----------------------------------------------------------------------------
// Repuestos
// -----------------------------------------------------------------------------

class _SeccionRepuestos extends ConsumerWidget {
  const _SeccionRepuestos({required this.ordenId, required this.cerrada});

  final String ordenId;
  final bool cerrada;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final claims = ref.watch(claimsProvider);
    final repuestos = ref.watch(repuestosProvider(ordenId));

    // El técnico puede *pedir* piezas —es quien descubre que hacen falta— pero
    // no ponerles precio ni darlas por recibidas. Eso lo aplica la política de
    // `orden_repuestos`, no esta pantalla.
    final puedePedir = !cerrada && claims != null && claims.rol != null;

    return Seccion(
      titulo: 'Repuestos',
      resumen: repuestos.maybeWhen(
        data: (r) => r.pendientes > 0
            ? '${r.pendientes} ${r.pendientes == 1 ? 'pieza' : 'piezas'} sin llegar · ${formatearMoneda(r.total)}'
            : formatearMoneda(r.total),
        orElse: () => null,
      ),
      accion: puedePedir
          ? IconButton.filled(
              onPressed: () => _pedir(context, ref),
              icon: const Icon(Icons.add),
              tooltip: 'Pedir pieza',
            )
          : null,
      children: repuestos.when(
        loading: () => const [
          Padding(padding: EdgeInsets.all(14), child: Center(child: CircularProgressIndicator())),
        ],
        error: (e, _) => [
          Padding(
            padding: const EdgeInsets.all(14),
            child: Aviso(
              tono: Tonos.error,
              texto: e is ErrorApi ? e.mensaje : 'No se pudieron cargar las piezas.',
            ),
          ),
        ],
        data: (r) => r.lineas.isEmpty
            ? [
                Vacio(
                  texto: cerrada
                      ? 'No se usaron piezas en esta orden.'
                      : 'Si hace falta una pieza, pídela aquí y repuestos la ve en su lista.',
                ),
              ]
            : [
                for (final l in r.lineas) ...[
                  Linea(
                    titulo: l.descripcion,
                    detalle: '${formatearNumero(l.cantidad)} × ${formatearMoneda(l.precioUnitario)}'
                        ' · ${l.estadoEtiqueta}'
                        '${l.solicitanteNombre == null ? '' : ' · pidió ${l.solicitanteNombre}'}',
                    importe: formatearMoneda(l.subtotal),
                  ),
                  const Divider(height: 1),
                ],
              ],
      ),
    );
  }

  Future<void> _pedir(BuildContext context, WidgetRef ref) async {
    final datos = await mostrarHoja<_DatosPieza>(
      context: context,
      titulo: 'Pedir una pieza',
      contenido: (_) => const _FormularioPieza(),
    );
    if (datos == null) return;

    try {
      await ref.read(repositorioProvider).pedirRepuesto(
            ordenId,
            descripcion: datos.descripcion,
            cantidad: datos.cantidad,
            notas: datos.notas,
          );
      ref.invalidate(repuestosProvider(ordenId));
      ref.invalidate(ordenProvider(ordenId));
      if (context.mounted) avisar(context, 'Pieza pedida. Repuestos la verá en su lista.');
    } on ErrorApi catch (e) {
      if (context.mounted) avisar(context, e.mensaje, esError: true);
    }
  }
}

class _DatosPieza {
  const _DatosPieza(this.descripcion, this.cantidad, this.notas);
  final String descripcion;
  final double cantidad;
  final String? notas;
}

class _FormularioPieza extends StatefulWidget {
  const _FormularioPieza();

  @override
  State<_FormularioPieza> createState() => _FormularioPiezaState();
}

class _FormularioPiezaState extends State<_FormularioPieza> {
  final _descripcion = TextEditingController();
  final _cantidad = TextEditingController(text: '1');
  final _notas = TextEditingController();

  @override
  void dispose() {
    _descripcion.dispose();
    _cantidad.dispose();
    _notas.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final descripcion = _descripcion.text.trim();
    final cantidad = double.tryParse(_cantidad.text.replaceAll(',', '.'));
    final valido = descripcion.length >= 3 && cantidad != null && cantidad > 0;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: _descripcion,
          autofocus: true,
          decoration: const InputDecoration(
            labelText: 'Qué pieza',
            helperText: 'Como la pedirías en el mostrador',
          ),
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _cantidad,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(labelText: 'Cantidad'),
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _notas,
          maxLines: 2,
          decoration: const InputDecoration(
            labelText: 'Notas (opcional)',
            helperText: 'Medida, lado, referencia que leíste en la pieza vieja…',
          ),
        ),
        const SizedBox(height: 14),
        FilledButton(
          onPressed: valido
              ? () => Navigator.pop(
                    context,
                    _DatosPieza(descripcion, cantidad, _notas.text),
                  )
              : null,
          child: const Text('Pedir'),
        ),
      ],
    );
  }
}
