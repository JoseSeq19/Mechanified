/// Cliente de la API de La Meseta.
///
/// Pone el token de la sesión en cada petición y traduce los dos formatos de
/// error del backend a un mensaje legible, igual que hace `web/src/lib/api.ts`:
///
///   - Errores de dominio:    `{ error: { codigo, mensaje, detalles } }`
///   - Validación de FastAPI: `{ detail: [{ loc, msg, type }] }`
///
/// Sin esa traducción, la app mostraría JSON en pantalla. Y como aquí la
/// pantalla es un móvil en un taller, el mensaje importa más que en la web: no
/// hay una consola al lado donde mirar qué pasó.
library;

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'config.dart';
import 'sesion.dart';

class ErrorApi implements Exception {
  ErrorApi(this.estado, this.mensaje, {this.codigo});

  final int estado;
  final String mensaje;
  final String? codigo;

  /// True cuando el problema es lo que se mandó, no un fallo del servidor.
  bool get esDeUsuario => estado >= 400 && estado < 500;

  /// True cuando hay que volver a entrar.
  bool get esDeSesion => estado == 401;

  bool get sinConexion => estado == 0;

  @override
  String toString() => mensaje;
}

final apiProvider = Provider<ApiMeseta>((ref) {
  // Pide el token al notificador en cada petición en vez de guardarse una
  // copia: una renovación a mitad de jornada no debe dejar a este cliente
  // llamando con el token viejo.
  return ApiMeseta(() => ref.read(sesionProvider.notifier).tokenVigente());
});

typedef DameToken = Future<String?> Function();

class ApiMeseta {
  ApiMeseta(this._token, {Dio? cliente})
      : _dio = cliente ??
            Dio(BaseOptions(
              baseUrl: Config.apiUrl,
              connectTimeout: const Duration(seconds: 15),
              // Generoso a propósito: la cobertura dentro de un taller con
              // estructura metálica es lo que es.
              receiveTimeout: const Duration(seconds: 30),
              validateStatus: (_) => true,
              contentType: 'application/json',
            ));

  final Dio _dio;
  final DameToken _token;

  Future<dynamic> get(String ruta, {Map<String, dynamic>? consulta}) =>
      _pedir('GET', ruta, consulta: consulta);

  Future<dynamic> post(String ruta, Object? cuerpo) => _pedir('POST', ruta, cuerpo: cuerpo);

  Future<dynamic> patch(String ruta, Object? cuerpo) => _pedir('PATCH', ruta, cuerpo: cuerpo);

  Future<dynamic> delete(String ruta) => _pedir('DELETE', ruta);

  Future<dynamic> _pedir(
    String metodo,
    String ruta, {
    Object? cuerpo,
    Map<String, dynamic>? consulta,
  }) async {
    final token = await _token();
    if (token == null) {
      throw ErrorApi(401, 'La sesión caducó. Vuelve a entrar.', codigo: 'sin_sesion');
    }

    Response<dynamic> respuesta;
    try {
      respuesta = await _dio.request<dynamic>(
        ruta,
        data: cuerpo,
        queryParameters: consulta,
        options: Options(
          method: metodo,
          headers: {'Authorization': 'Bearer $token'},
        ),
      );
    } on DioException catch (e) {
      throw ErrorApi(0, _mensajeDeRed(e), codigo: 'sin_conexion');
    }

    final estado = respuesta.statusCode ?? 0;
    if (estado >= 200 && estado < 300) return respuesta.data;
    throw _construirError(estado, respuesta.data);
  }

  String _mensajeDeRed(DioException e) {
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
        return 'La API tardó demasiado en responder. Puede ser la cobertura.';
      case DioExceptionType.connectionError:
        return 'No se pudo contactar la API en ${Config.apiUrl}. '
            'Comprueba que esté levantada y que el móvil la alcance.';
      default:
        return 'No se pudo completar la petición: ${e.message ?? e.type.name}.';
    }
  }

  ErrorApi _construirError(int estado, Object? cuerpo) {
    if (cuerpo is Map) {
      final error = cuerpo['error'];
      if (error is Map) {
        return ErrorApi(
          estado,
          (error['mensaje'] as String?) ?? 'Error inesperado.',
          codigo: error['codigo'] as String?,
        );
      }

      final detalle = cuerpo['detail'];
      if (detalle is List) {
        final mensajes = detalle.map(_traducirValidacion).where((m) => m.isNotEmpty);
        return ErrorApi(estado, mensajes.join('. '), codigo: 'validacion');
      }
      if (detalle is String) return ErrorApi(estado, detalle);
    }
    return ErrorApi(estado, 'Error $estado al contactar la API.');
  }

  /// Los mensajes de Pydantic que más se ven desde un formulario.
  String _traducirValidacion(Object? detalle) {
    if (detalle is! Map) return '';

    final ubicacion = (detalle['loc'] as List?) ?? const [];
    final campo = ubicacion.where((p) => p != 'body').join('.');
    final tipo = detalle['type'] as String? ?? '';

    const traducciones = {
      'string_too_short': 'es demasiado corto',
      'string_too_long': 'es demasiado largo',
      'missing': 'es obligatorio',
      'value_error': 'no tiene un formato válido',
      'enum': 'no es un valor permitido',
    };

    final motivo = traducciones[tipo] ?? (detalle['msg'] as String? ?? 'no es válido');
    return '${campo.isEmpty ? 'el dato' : campo}: $motivo';
  }
}
