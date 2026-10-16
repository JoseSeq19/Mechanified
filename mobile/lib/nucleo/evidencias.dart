/// Subida y lectura de fotos en el bucket privado de Supabase Storage.
///
/// La foto **no pasa por la API de La Meseta**, igual que en la web: va del
/// móvil al bucket con el token de la sesión, y después se registran los
/// metadatos en la API. Hacer pasar varios MB por FastAPI no añadiría ninguna
/// comprobación que la política del bucket no haga ya, y ocuparía un trabajador
/// del servidor al ritmo de la cobertura del taller.
///
/// La ruta es un contrato con el backend y con la base de datos:
///
///     {taller_id}/{orden_id}/{uuid}-{nombre}
///
/// La valida `app/modules/adjuntos/service.py` y la refuerza el trigger
/// `mch_adjuntos_ruta_guard`, que compara la primera carpeta con el taller de
/// la sesión. Es lo que impide que una foto acabe colgada de la orden de otro
/// taller.
library;

import 'dart:math';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api.dart';
import 'config.dart';
import 'sesion.dart';

/// Lo que acepta el bucket, declarado en la migración 001000.
const mimesPermitidos = <String>{
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/heic',
  'application/pdf',
};

/// 25 MiB, el tope del bucket.
const tamanoMaximo = 26214400;

final evidenciasProvider = Provider<Evidencias>((ref) {
  return Evidencias(() => ref.read(sesionProvider.notifier).tokenVigente());
});

class Evidencias {
  Evidencias(this._token, {Dio? cliente})
      : _dio = cliente ??
            Dio(BaseOptions(
              baseUrl: '${Config.supabaseUrl}/storage/v1',
              connectTimeout: const Duration(seconds: 15),
              // Una foto de taller son varios MB por una red de taller.
              sendTimeout: const Duration(seconds: 120),
              receiveTimeout: const Duration(seconds: 60),
              validateStatus: (_) => true,
            ));

  final Dio _dio;
  final DameToken _token;

  static final _azar = Random.secure();

  /// Compone la ruta del objeto respetando la convención del contrato.
  ///
  /// El último tramo se escribe tal cual dentro de una URL firmada, así que no
  /// puede llevar espacios ni acentos; el nombre bonito viaja aparte, en los
  /// metadatos, que es lo que se le muestra a la gente.
  static String componerRuta({
    required String tallerId,
    required String ordenId,
    required String nombre,
  }) {
    final limpio = nombre
        .replaceAll(RegExp(r'[^A-Za-z0-9._-]+'), '-')
        .replaceAll(RegExp(r'^-+|-+$'), '');
    final base = limpio.isEmpty ? 'archivo' : limpio;
    final corto = base.length > 120 ? base.substring(base.length - 120) : base;

    return '$tallerId/$ordenId/${_identificador()}-$corto';
  }

  static String _identificador() {
    // Un uuid v4 a mano: es lo único que se necesita de un paquete de uuid.
    const hex = '0123456789abcdef';
    final b = StringBuffer();
    for (var i = 0; i < 32; i++) {
      b.write(hex[_azar.nextInt(16)]);
    }
    return b.toString();
  }

  /// Qué le pasa al archivo antes de salir del móvil.
  static String? revisar({required String mime, required int bytes, required String nombre}) {
    if (!mimesPermitidos.contains(mime)) {
      return 'Solo se admiten fotos (JPG, PNG, WebP, HEIC) y PDF.';
    }
    if (bytes <= 0) return 'El archivo está vacío.';
    if (bytes > tamanoMaximo) return 'La foto pasa de 25 MB. Hazla con menos resolución.';
    return null;
  }

  /// Sube el objeto al bucket. Devuelve la ruta con la que registrarlo.
  Future<String> subir({
    required String tallerId,
    required String ordenId,
    required String nombre,
    required String mime,
    required Uint8List datos,
  }) async {
    final token = await _token();
    if (token == null) throw ErrorApi(401, 'La sesión caducó. Vuelve a entrar.');

    final ruta = componerRuta(tallerId: tallerId, ordenId: ordenId, nombre: nombre);

    Response<dynamic> respuesta;
    try {
      respuesta = await _dio.post<dynamic>(
        '/object/${Config.bucketEvidencias}/$ruta',
        data: Stream.fromIterable([datos]),
        options: Options(
          headers: {
            'Authorization': 'Bearer $token',
            'apikey': Config.supabaseAnonKey,
            'Content-Type': mime,
            'Content-Length': datos.length,
            // Sin sobrescribir: la ruta lleva un identificador único, así que
            // un choque significaría que algo se está repitiendo.
            'x-upsert': 'false',
          },
        ),
      );
    } on DioException catch (e) {
      throw ErrorApi(0, 'No se pudo subir la foto: ${e.message ?? e.type.name}.');
    }

    final estado = respuesta.statusCode ?? 0;
    if (estado >= 200 && estado < 300) return ruta;

    throw ErrorApi(estado, _traducir(estado, respuesta.data));
  }

  /// URL temporal para mostrar un objeto. El bucket es privado: no hay otra.
  Future<String?> urlFirmada(String ruta, {int segundos = 600}) async {
    final token = await _token();
    if (token == null) return null;

    try {
      final respuesta = await _dio.post<dynamic>(
        '/object/sign/${Config.bucketEvidencias}/$ruta',
        data: {'expiresIn': segundos},
        options: Options(headers: {
          'Authorization': 'Bearer $token',
          'apikey': Config.supabaseAnonKey,
          'Content-Type': 'application/json',
        }),
      );

      final cuerpo = respuesta.data;
      if (cuerpo is Map && cuerpo['signedURL'] is String) {
        final firmada = cuerpo['signedURL'] as String;
        // Supabase devuelve la ruta relativa a /storage/v1.
        return '${Config.supabaseUrl}/storage/v1$firmada';
      }
    } on DioException {
      return null;
    }
    return null;
  }

  /// Borra el objeto. Se llama después de que la API acepte quitar la fila.
  Future<void> borrar(String ruta) async {
    final token = await _token();
    if (token == null) return;

    try {
      await _dio.delete<dynamic>(
        '/object/${Config.bucketEvidencias}/$ruta',
        options: Options(headers: {
          'Authorization': 'Bearer $token',
          'apikey': Config.supabaseAnonKey,
        }),
      );
    } on DioException {
      // El registro ya no está, que es lo que se ve en la ficha. Un objeto
      // huérfano en el bucket no justifica dejar a medias la operación.
    }
  }

  String _traducir(int estado, Object? cuerpo) {
    final mensaje = cuerpo is Map
        ? (cuerpo['message'] as String? ?? cuerpo['error'] as String? ?? '')
        : '';
    final m = mensaje.toLowerCase();

    if (m.contains('exceeded the maximum allowed size')) {
      return 'La foto pasa del tamaño que acepta el bucket (25 MB).';
    }
    if (m.contains('mime type')) return 'El bucket no acepta ese tipo de archivo.';
    if (estado == 401 || estado == 403 || m.contains('row-level security')) {
      return 'Tu sesión no tiene permiso para subir archivos a este taller.';
    }
    if (m.contains('already exists')) return 'Ya hay un archivo con ese nombre. Reinténtalo.';
    return mensaje.isEmpty ? 'No se pudo subir la foto (error $estado).' : mensaje;
  }
}
