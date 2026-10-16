/// Lo que la app de campo le pide a la API, en un solo sitio.
///
/// No hay lógica de negocio aquí, y no debe haberla: las reglas —qué rol puede
/// mover la orden, qué tarifa se aplica, si una pieza se puede pedir— viven en
/// el backend y en las políticas de Postgres. Este archivo solo traduce entre
/// JSON y los modelos del dominio.
///
/// Los proveedores de Riverpod que hay al final son la otra mitad: cada
/// pantalla observa el que necesita y vuelve a pedirlo invalidándolo, en vez de
/// guardarse copias que se queden viejas mientras el taller trabaja.
library;

import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../nucleo/api.dart';
import '../nucleo/evidencias.dart';
import '../nucleo/sesion.dart';
import 'modelos.dart';

class Repositorio {
  const Repositorio(this._api, this._evidencias);

  final ApiMeseta _api;
  final Evidencias _evidencias;

  // --- Taller ---------------------------------------------------------------

  Future<Taller> taller() async {
    final datos = await _api.get('/taller');
    return Taller.deJson(datos as Map<String, dynamic>);
  }

  // --- Órdenes --------------------------------------------------------------

  /// Órdenes abiertas, opcionalmente solo las de un técnico.
  ///
  /// Para el técnico, "mis órdenes" es exactamente lo que tiene asignado: el
  /// filtro lo hace la API con `tecnico_id`, no la app descartando lo que ya se
  /// trajo, que sería traerse el taller entero por el móvil.
  Future<List<OrdenResumen>> ordenes({
    String? tecnicoId,
    String? busqueda,
    bool incluirCerradas = false,
    int limite = 50,
    int desplazamiento = 0,
  }) async {
    final datos = await _api.get('/ordenes', consulta: {
      'limite': limite,
      'desplazamiento': desplazamiento,
      if (tecnicoId != null) 'tecnico_id': tecnicoId,
      if (busqueda != null && busqueda.trim().length >= 3) 'busqueda': busqueda.trim(),
      if (incluirCerradas) 'incluir_cerradas': true,
    });

    final items = (datos as Map<String, dynamic>)['items'] as List? ?? const [];
    return items.map((o) => OrdenResumen.deJson(o as Map<String, dynamic>)).toList();
  }

  Future<Orden> orden(String ordenId) async {
    final datos = await _api.get('/ordenes/$ordenId');
    return Orden.deJson(datos as Map<String, dynamic>);
  }

  Future<Orden> cambiarEstado(String ordenId, String estado, {String? comentario}) async {
    final datos = await _api.post('/ordenes/$ordenId/estado', {
      'estado': estado,
      'comentario': (comentario ?? '').trim().isEmpty ? null : comentario!.trim(),
    });
    return Orden.deJson(datos as Map<String, dynamic>);
  }

  // --- Diagnóstico y trabajo -----------------------------------------------

  Future<List<Diagnostico>> diagnosticos(String ordenId) async {
    final datos = await _api.get('/ordenes/$ordenId/diagnosticos');
    return (datos as List).map((d) => Diagnostico.deJson(d as Map<String, dynamic>)).toList();
  }

  Future<Diagnostico> crearDiagnostico(
    String ordenId, {
    required String resumen,
    required double horasEstimadas,
    List<Map<String, Object?>> hallazgos = const [],
  }) async {
    final datos = await _api.post('/ordenes/$ordenId/diagnosticos', {
      'resumen': resumen,
      'horas_estimadas': horasEstimadas,
      'hallazgos': hallazgos,
    });
    return Diagnostico.deJson(datos as Map<String, dynamic>);
  }

  Future<Diagnostico> agregarHallazgo(
    String diagnosticoId, {
    required String sistema,
    required String descripcion,
    required String severidad,
    required bool requiereRepuesto,
  }) async {
    final datos = await _api.post('/diagnosticos/$diagnosticoId/hallazgos', {
      'sistema': sistema,
      'descripcion': descripcion,
      'severidad': severidad,
      'requiere_repuesto': requiereRepuesto,
    });
    return Diagnostico.deJson(datos as Map<String, dynamic>);
  }

  Future<ResumenManoObra> manoObra(String ordenId) async {
    final datos = await _api.get('/ordenes/$ordenId/mano-obra');
    return ResumenManoObra.deJson(datos as Map<String, dynamic>);
  }

  /// Carga una línea de trabajo. Sin tarifa, el backend aplica la del taller y
  /// la congela en la línea, que es lo que hace que subirla luego no cambie lo
  /// ya facturado.
  Future<void> cargarManoObra(
    String ordenId, {
    required String descripcion,
    required double horas,
    String? tecnicoId,
  }) async {
    await _api.post('/ordenes/$ordenId/mano-obra', {
      'descripcion': descripcion,
      'horas': horas,
      'tarifa_hora': null,
      'tecnico_id': tecnicoId,
    });
  }

  // --- Repuestos ------------------------------------------------------------

  Future<ResumenRepuestos> repuestos(String ordenId) async {
    final datos = await _api.get('/ordenes/$ordenId/repuestos');
    return ResumenRepuestos.deJson(datos as Map<String, dynamic>);
  }

  /// Pide una pieza para la orden.
  ///
  /// El técnico puede *pedirla* —es quien descubre que hace falta— pero no
  /// ponerle precio ni darla por recibida: eso lo aplica la política de
  /// `orden_repuestos`, no esta app.
  Future<void> pedirRepuesto(
    String ordenId, {
    required String descripcion,
    required double cantidad,
    String? notas,
  }) async {
    await _api.post('/ordenes/$ordenId/repuestos', {
      'descripcion': descripcion,
      'cantidad': cantidad,
      'notas': (notas ?? '').trim().isEmpty ? null : notas!.trim(),
    });
  }

  // --- Fotos ----------------------------------------------------------------

  Future<List<Adjunto>> adjuntos(String ordenId) async {
    final datos = await _api.get('/ordenes/$ordenId/adjuntos');
    return (datos as List).map((a) => Adjunto.deJson(a as Map<String, dynamic>)).toList();
  }

  /// Sube la foto al bucket y registra sus metadatos.
  ///
  /// Si el registro falla, se borra el objeto que acababa de subirse: sin esa
  /// compensación el bucket acumularía fotos que ninguna ficha menciona y que
  /// nadie puede encontrar para borrar.
  Future<Adjunto> subirFoto({
    required String tallerId,
    required String ordenId,
    required String nombre,
    required String mime,
    required Uint8List datos,
    required String contexto,
    String? descripcion,
  }) async {
    final problema = Evidencias.revisar(mime: mime, bytes: datos.length, nombre: nombre);
    if (problema != null) throw ErrorApi(422, problema);

    final ruta = await _evidencias.subir(
      tallerId: tallerId,
      ordenId: ordenId,
      nombre: nombre,
      mime: mime,
      datos: datos,
    );

    try {
      final fila = await _api.post('/ordenes/$ordenId/adjuntos', {
        'contexto': contexto,
        'ruta_storage': ruta,
        'nombre_archivo': nombre,
        'mime': mime,
        'tamano_bytes': datos.length,
        'descripcion': (descripcion ?? '').trim().isEmpty ? null : descripcion!.trim(),
      });
      return Adjunto.deJson(fila as Map<String, dynamic>);
    } catch (_) {
      await _evidencias.borrar(ruta);
      rethrow;
    }
  }

  /// Quita la foto: primero el registro, que es el que tiene la política
  /// estricta, y solo si la API lo acepta, el archivo.
  Future<void> borrarFoto(Adjunto adjunto) async {
    await _api.delete('/adjuntos/${adjunto.id}');
    await _evidencias.borrar(adjunto.rutaStorage);
  }

  Future<String?> urlFirmada(String ruta) => _evidencias.urlFirmada(ruta);
}

// -----------------------------------------------------------------------------
// Proveedores
// -----------------------------------------------------------------------------

final repositorioProvider = Provider<Repositorio>(
  (ref) => Repositorio(ref.watch(apiProvider), ref.watch(evidenciasProvider)),
);

/// Configuración del taller. Se pide una vez y de ahí sale la moneda con la que
/// se escribe cada cifra de la app.
final tallerProvider = FutureProvider<Taller>((ref) async {
  return ref.watch(repositorioProvider).taller();
});

/// Si el técnico ve solo lo suyo o el taller entero.
///
/// Para un técnico, lo suyo es lo asignado; para asesoría y administración, el
/// taller entero, porque su trabajo es repartirlo. El interruptor existe porque
/// un técnico a veces necesita mirar una orden que no es suya —la del coche que
/// tiene al lado en la rampa—.
final soloMiasProvider = StateProvider<bool>((ref) {
  final claims = ref.watch(claimsProvider);
  return claims?.esTecnico ?? false;
});

final busquedaProvider = StateProvider<String>((ref) => '');

final ordenesProvider = FutureProvider<List<OrdenResumen>>((ref) async {
  final claims = ref.watch(claimsProvider);
  final soloMias = ref.watch(soloMiasProvider);
  final busqueda = ref.watch(busquedaProvider);

  return ref.watch(repositorioProvider).ordenes(
        tecnicoId: soloMias ? claims?.sub : null,
        busqueda: busqueda,
        // Buscando por folio o placa se busca en todo el historial: el caso es
        // "¿qué pasó con este coche?", y casi siempre ya está entregado.
        incluirCerradas: busqueda.trim().length >= 3,
      );
});

final ordenProvider = FutureProvider.family<Orden, String>((ref, ordenId) async {
  return ref.watch(repositorioProvider).orden(ordenId);
});

final diagnosticosProvider = FutureProvider.family<List<Diagnostico>, String>((ref, ordenId) async {
  return ref.watch(repositorioProvider).diagnosticos(ordenId);
});

final manoObraProvider = FutureProvider.family<ResumenManoObra, String>((ref, ordenId) async {
  return ref.watch(repositorioProvider).manoObra(ordenId);
});

final repuestosProvider = FutureProvider.family<ResumenRepuestos, String>((ref, ordenId) async {
  return ref.watch(repositorioProvider).repuestos(ordenId);
});

final adjuntosProvider = FutureProvider.family<List<Adjunto>, String>((ref, ordenId) async {
  return ref.watch(repositorioProvider).adjuntos(ordenId);
});
