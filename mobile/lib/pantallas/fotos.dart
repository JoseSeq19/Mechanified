/// Las fotos de la orden, desde la cámara del móvil.
///
/// Es la razón de ser de una app de campo: la constancia del estado del
/// vehículo la hace quien está delante del vehículo, con el móvil que lleva en
/// el bolsillo. Desde la web se pueden subir archivos, pero nadie va a bajar el
/// coche de la rampa para ir al ordenador.
///
/// La foto va del móvil al bucket privado y después se registran sus metadatos
/// en la API; ver `nucleo/evidencias.dart`. Lo que se ve aquí son URLs firmadas
/// que caducan: el bucket no es público y no hay ninguna dirección permanente
/// que se pueda reenviar por ahí.
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../datos/modelos.dart';
import '../datos/repositorio.dart';
import '../nucleo/api.dart';
import '../nucleo/formato.dart';
import '../nucleo/sesion.dart';
import '../nucleo/tema.dart';
import 'comun.dart';

class SeccionFotos extends ConsumerStatefulWidget {
  const SeccionFotos({super.key, required this.ordenId});

  final String ordenId;

  @override
  ConsumerState<SeccionFotos> createState() => _SeccionFotosState();
}

class _SeccionFotosState extends ConsumerState<SeccionFotos> {
  final _nota = TextEditingController();
  String _contexto = 'ingreso';
  bool _subiendo = false;

  @override
  void dispose() {
    _nota.dispose();
    super.dispose();
  }

  Future<void> _tomar(ImageSource origen) async {
    final tallerId = ref.read(claimsProvider)?.tallerId;
    if (tallerId == null) {
      avisar(context, 'Tu sesión no trae taller, así que no hay dónde guardar la foto.',
          esError: true);
      return;
    }

    final XFile? foto;
    try {
      foto = await ImagePicker().pickImage(
        source: origen,
        // Se reduce antes de salir del móvil: una foto de 12 MP son 6 MB por
        // una red de taller, y para ver un golpe en un parachoques sobra con
        // bastante menos.
        maxWidth: 1800,
        imageQuality: 75,
      );
    } catch (e) {
      if (mounted) avisar(context, 'No se pudo abrir la cámara: $e', esError: true);
      return;
    }

    if (foto == null) return; // la persona canceló

    final datos = await foto.readAsBytes();
    final mime = _mimeDe(foto);

    setState(() => _subiendo = true);
    try {
      await ref.read(repositorioProvider).subirFoto(
            tallerId: tallerId,
            ordenId: widget.ordenId,
            nombre: foto.name,
            mime: mime,
            datos: Uint8List.fromList(datos),
            contexto: _contexto,
            descripcion: _nota.text,
          );
      _nota.clear();
      ref.invalidate(adjuntosProvider(widget.ordenId));
      if (mounted) avisar(context, 'Foto guardada en ${contextosAdjunto[_contexto]}.');
    } on ErrorApi catch (e) {
      if (mounted) avisar(context, e.mensaje, esError: true);
    } catch (e) {
      if (mounted) avisar(context, 'No se pudo subir la foto: $e', esError: true);
    } finally {
      if (mounted) setState(() => _subiendo = false);
    }
  }

  /// `XFile.mimeType` viene vacío en Android, así que se deduce de la extensión.
  String _mimeDe(XFile archivo) {
    final declarado = archivo.mimeType;
    if (declarado != null && declarado.isNotEmpty) return declarado;

    final nombre = archivo.name.toLowerCase();
    if (nombre.endsWith('.png')) return 'image/png';
    if (nombre.endsWith('.webp')) return 'image/webp';
    if (nombre.endsWith('.heic') || nombre.endsWith('.heif')) return 'image/heic';
    if (nombre.endsWith('.pdf')) return 'application/pdf';
    return 'image/jpeg';
  }

  Future<void> _borrar(Adjunto adjunto) async {
    final confirmado = await showDialog<bool>(
      context: context,
      builder: (contexto) => AlertDialog(
        title: const Text('Quitar la foto'),
        content: Text('Se quita de la orden y se borra del archivo. ¿Seguro?\n\n'
            '${adjunto.nombreArchivo}'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(contexto, false),
            child: const Text('Cancelar'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(contexto, true),
            child: const Text('Quitar'),
          ),
        ],
      ),
    );
    if (confirmado != true) return;

    try {
      await ref.read(repositorioProvider).borrarFoto(adjunto);
      ref.invalidate(adjuntosProvider(widget.ordenId));
    } on ErrorApi catch (e) {
      if (mounted) avisar(context, e.mensaje, esError: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final adjuntos = ref.watch(adjuntosProvider(widget.ordenId));

    return Seccion(
      titulo: 'Fotos',
      resumen: adjuntos.maybeWhen(
        data: (lista) => lista.isEmpty
            ? 'Lo que respalda al taller si después hay una discusión.'
            : '${lista.length} ${lista.length == 1 ? 'archivo' : 'archivos'}',
        orElse: () => null,
      ),
      accion: _subiendo
          ? const Padding(
              padding: EdgeInsets.all(8),
              child: SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)),
            )
          : Row(
              children: [
                IconButton(
                  onPressed: () => _tomar(ImageSource.gallery),
                  icon: const Icon(Icons.photo_library_outlined),
                  tooltip: 'Elegir de la galería',
                ),
                IconButton.filled(
                  onPressed: () => _tomar(ImageSource.camera),
                  icon: const Icon(Icons.photo_camera_outlined),
                  tooltip: 'Tomar foto',
                ),
              ],
            ),
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 12, 14, 4),
          child: TextField(
            controller: _nota,
            maxLength: 500,
            decoration: const InputDecoration(
              labelText: 'Nota (opcional)',
              // Se escribe antes de disparar y queda junto a la foto. Es lo que
              // convierte seis fotos del mismo parachoques en seis fotos que
              // dicen algo distinto.
              helperText: 'Golpe lateral derecho, factura de la bomba…',
              counterText: '',
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 4, 14, 4),
          child: DropdownButtonFormField<String>(
            // El momento al que pertenece lo que se vaya a subir. Se elige
            // antes de disparar: después, con la foto hecha, nadie lo cambia.
            value: _contexto,
            decoration: const InputDecoration(labelText: 'La foto es de…'),
            items: contextosAdjunto.entries
                .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
                .toList(),
            onChanged: (valor) => setState(() => _contexto = valor ?? 'ingreso'),
          ),
        ),
        adjuntos.when(
          loading: () => const Padding(
            padding: EdgeInsets.all(14),
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (e, _) => Padding(
            padding: const EdgeInsets.all(14),
            child: Aviso(
              tono: Tonos.error,
              texto: e is ErrorApi ? e.mensaje : 'No se pudieron cargar las fotos.',
            ),
          ),
          data: (lista) => lista.isEmpty
              ? const Vacio(texto: 'Todavía no hay ninguna. Toma la primera con la cámara.')
              : _Galeria(adjuntos: lista, alBorrar: _borrar),
        ),
      ],
    );
  }
}

class _Galeria extends StatelessWidget {
  const _Galeria({required this.adjuntos, required this.alBorrar});

  final List<Adjunto> adjuntos;
  final void Function(Adjunto) alBorrar;

  @override
  Widget build(BuildContext context) {
    final porContexto = <String, List<Adjunto>>{};
    for (final a in adjuntos) {
      porContexto.putIfAbsent(a.contexto, () => <Adjunto>[]).add(a);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final contexto in contextosAdjunto.keys)
          if (porContexto[contexto] != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 8, 14, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    contextosAdjunto[contexto]!.toUpperCase(),
                    style: const TextStyle(
                      fontSize: 11,
                      letterSpacing: 0.6,
                      color: Tonos.textoSecundario,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: porContexto[contexto]!
                        .map((a) => _Miniatura(adjunto: a, alBorrar: alBorrar))
                        .toList(),
                  ),
                ],
              ),
            ),
      ],
    );
  }
}

class _Miniatura extends ConsumerWidget {
  const _Miniatura({required this.adjunto, required this.alBorrar});

  final Adjunto adjunto;
  final void Function(Adjunto) alBorrar;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final url = ref.watch(urlFirmadaProvider(adjunto.rutaStorage));

    return SizedBox(
      width: 104,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          GestureDetector(
            onTap: () {
              final enlace = url.valueOrNull;
              if (enlace != null) _verGrande(context, adjunto, enlace);
            },
            onLongPress: adjunto.puedeBorrar ? () => alBorrar(adjunto) : null,
            child: Container(
              width: 104,
              height: 104,
              decoration: BoxDecoration(
                color: Tonos.lineaSuave,
                border: Border.all(color: Tonos.borde),
                borderRadius: BorderRadius.circular(10),
              ),
              clipBehavior: Clip.antiAlias,
              child: url.when(
                loading: () => const Center(
                  child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
                ),
                error: (_, __) => const Center(child: Icon(Icons.broken_image_outlined)),
                data: (enlace) {
                  if (enlace == null) return const Center(child: Icon(Icons.lock_outline));
                  if (!adjunto.esImagen) {
                    return const Center(child: Icon(Icons.picture_as_pdf_outlined, size: 32));
                  }
                  return Image.network(
                    enlace,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) =>
                        const Center(child: Icon(Icons.broken_image_outlined)),
                  );
                },
              ),
            ),
          ),
          const SizedBox(height: 4),
          Text(
            formatearFecha(adjunto.creadoEn),
            style: const TextStyle(fontSize: 11, color: Tonos.textoSecundario),
          ),
          Text(
            adjunto.autorNombre ?? 'Autor dado de baja',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 11, color: Tonos.textoSecundario),
          ),
        ],
      ),
    );
  }

  void _verGrande(BuildContext context, Adjunto adjunto, String enlace) {
    showDialog<void>(
      context: context,
      builder: (contexto) => Dialog(
        insetPadding: const EdgeInsets.all(12),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Flexible(
              child: adjunto.esImagen
                  ? InteractiveViewer(child: Image.network(enlace))
                  : Padding(
                      padding: const EdgeInsets.all(24),
                      child: Text(
                        'Es un PDF: ${adjunto.nombreArchivo}. Ábrelo desde la web del taller.',
                      ),
                    ),
            ),
            Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                children: [
                  Text(
                    adjunto.descripcion ?? adjunto.nombreArchivo,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8),
                  TextButton(
                    onPressed: () => Navigator.pop(contexto),
                    child: const Text('Cerrar'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// URL firmada de un objeto, cacheada por ruta.
///
/// Es un proveedor y no una llamada dentro del widget para que al reconstruir
/// la lista —y se reconstruye con cada foto nueva— no se vuelva a firmar lo que
/// ya estaba firmado.
final urlFirmadaProvider = FutureProvider.family<String?, String>((ref, ruta) async {
  return ref.watch(repositorioProvider).urlFirmada(ruta);
});
