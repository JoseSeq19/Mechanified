/// Autenticación contra Supabase Auth, por su API REST.
///
/// La app no usa el SDK de Supabase. No es purismo: el único trato que tiene
/// con Supabase es iniciar sesión, renovar el token y hablar con Storage, y eso
/// son cuatro peticiones HTTP. Traer el SDK entero para eso ataría la app de
/// campo a su ciclo de versiones, y los datos de negocio no salen de ahí: salen
/// de la API de La Meseta.
///
/// El token de acceso dura una hora y vive en memoria. El de refresco vive en
/// el almacén cifrado del sistema (Keychain en iOS, Keystore en Android), que
/// es lo que permite que el técnico abra la app por la mañana sin volver a
/// escribir su contraseña.
library;

import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'config.dart';

/// Lo que el JWT trae dentro y de lo que depende todo lo demás.
///
/// `taller_id` y `rol` los inyecta el hook `mch_hook_access_token` de Supabase
/// leyendo el perfil. Si faltan, la API responde 401 a todo, así que la app lo
/// detecta y lo dice en vez de dejar pantallas vacías sin explicación.
class Claims {
  const Claims({this.sub, this.tallerId, this.rol, this.email});

  final String? sub;
  final String? tallerId;
  final String? rol;
  final String? email;

  bool get completos => (tallerId ?? '').isNotEmpty && (rol ?? '').isNotEmpty;

  bool get esTecnico => rol == 'tecnico';
  bool get esAdmin => rol == 'admin_taller';
  bool get esAsesor => rol == 'asesor_servicio';

  String get rolEtiqueta {
    switch (rol) {
      case 'admin_taller':
        return 'Administración';
      case 'asesor_servicio':
        return 'Asesoría de servicio';
      case 'tecnico':
        return 'Técnico';
      case 'encargado_repuestos':
        return 'Repuestos';
      default:
        return 'Sin rol';
    }
  }

  /// Lee el cuerpo del token sin verificar la firma: la verifica el backend.
  static Claims? deToken(String? token) {
    if (token == null) return null;
    final partes = token.split('.');
    if (partes.length < 2) return null;

    try {
      final json = utf8.decode(base64Url.decode(base64Url.normalize(partes[1])));
      final mapa = jsonDecode(json) as Map<String, dynamic>;
      return Claims(
        sub: mapa['sub'] as String?,
        tallerId: mapa['taller_id'] as String?,
        rol: mapa['rol'] as String?,
        email: mapa['email'] as String?,
      );
    } catch (_) {
      return null;
    }
  }
}

class Credenciales {
  const Credenciales({
    required this.accessToken,
    required this.refreshToken,
    required this.expiraEn,
  });

  final String accessToken;
  final String refreshToken;
  final DateTime expiraEn;

  Claims? get claims => Claims.deToken(accessToken);

  /// Se renueva un minuto antes de la hora: así ninguna petición sale con un
  /// token que caduca mientras viaja.
  bool get porCaducar => DateTime.now().isAfter(expiraEn.subtract(const Duration(seconds: 60)));
}

/// Lo que puede salir mal, ya traducido.
class ErrorAuth implements Exception {
  ErrorAuth(this.mensaje);
  final String mensaje;

  @override
  String toString() => mensaje;
}

class AuthSupabase {
  AuthSupabase({Dio? cliente, FlutterSecureStorage? almacen})
      : _dio = cliente ??
            Dio(BaseOptions(
              baseUrl: '${Config.supabaseUrl}/auth/v1',
              connectTimeout: const Duration(seconds: 15),
              receiveTimeout: const Duration(seconds: 20),
              // Los errores se interpretan abajo, con su cuerpo: Supabase
              // explica en el JSON lo que un código de estado no dice.
              validateStatus: (_) => true,
            )),
        _almacen = almacen ?? const FlutterSecureStorage();

  final Dio _dio;
  final FlutterSecureStorage _almacen;

  static const _claveRefresco = 'mch_refresh_token';

  Map<String, String> get _cabeceras => {
        'apikey': Config.supabaseAnonKey,
        'Content-Type': 'application/json',
      };

  Future<Credenciales> entrar(String correo, String clave) async {
    final respuesta = await _dio.post<dynamic>(
      '/token',
      queryParameters: {'grant_type': 'password'},
      options: Options(headers: _cabeceras),
      data: {'email': correo.trim(), 'password': clave},
    );
    return _credencialesDe(respuesta);
  }

  /// Recupera la sesión guardada. Devuelve null si no hay o si ya no vale.
  Future<Credenciales?> reanudar() async {
    final refresco = await _almacen.read(key: _claveRefresco);
    if (refresco == null || refresco.isEmpty) return null;

    try {
      return await renovar(refresco);
    } on ErrorAuth {
      // El refresco caducó o se revocó: se olvida y se pide la contraseña.
      await olvidar();
      return null;
    }
  }

  Future<Credenciales> renovar(String refreshToken) async {
    final respuesta = await _dio.post<dynamic>(
      '/token',
      queryParameters: {'grant_type': 'refresh_token'},
      options: Options(headers: _cabeceras),
      data: {'refresh_token': refreshToken},
    );
    return _credencialesDe(respuesta);
  }

  Future<void> cambiarClave(String accessToken, String clave) async {
    final respuesta = await _dio.put<dynamic>(
      '/user',
      options: Options(headers: {..._cabeceras, 'Authorization': 'Bearer $accessToken'}),
      data: {'password': clave},
    );
    if (respuesta.statusCode != 200) {
      throw ErrorAuth(_traducir(_mensajeDe(respuesta.data)));
    }
  }

  /// Pide el correo con el enlace para poner una contraseña nueva.
  ///
  /// El enlace abre la web, no la app: la pantalla que cambia la contraseña
  /// desde un enlace ya existe allí (`/clave`), y duplicarla aquí obligaría a
  /// registrar un esquema de enlaces profundos para ganar un paso.
  Future<void> pedirRecuperacion(String correo) async {
    final respuesta = await _dio.post<dynamic>(
      '/recover',
      options: Options(headers: _cabeceras),
      data: {'email': correo.trim()},
    );
    final codigo = respuesta.statusCode ?? 0;
    if (codigo < 200 || codigo >= 300) {
      throw ErrorAuth(_traducir(_mensajeDe(respuesta.data)));
    }
  }

  Future<void> guardar(Credenciales credenciales) =>
      _almacen.write(key: _claveRefresco, value: credenciales.refreshToken);

  Future<void> olvidar() => _almacen.delete(key: _claveRefresco);

  Credenciales _credencialesDe(Response<dynamic> respuesta) {
    final codigo = respuesta.statusCode ?? 0;
    // El cuerpo no siempre es JSON: un proxy delante de Supabase puede
    // responder una página de error, y eso no debe estallar como un casteo.
    final cuerpo = respuesta.data is Map
        ? (respuesta.data as Map).cast<String, dynamic>()
        : const <String, dynamic>{};

    if (codigo < 200 || codigo >= 300) {
      throw ErrorAuth(_traducir(_mensajeDe(respuesta.data)));
    }

    final acceso = cuerpo['access_token'] as String?;
    final refresco = cuerpo['refresh_token'] as String?;
    if (acceso == null || refresco == null) {
      throw ErrorAuth('Supabase respondió sin token. Revisa la URL y la llave anónima.');
    }

    final segundos = (cuerpo['expires_in'] as num?)?.toInt() ?? 3600;
    return Credenciales(
      accessToken: acceso,
      refreshToken: refresco,
      expiraEn: DateTime.now().add(Duration(seconds: segundos)),
    );
  }

  String _mensajeDe(Object? cuerpo) {
    if (cuerpo is Map) {
      for (final clave in ['error_description', 'msg', 'message', 'error']) {
        final valor = cuerpo[clave];
        if (valor is String && valor.isNotEmpty) return valor;
      }
    }
    return 'No se pudo contactar a Supabase.';
  }

  String _traducir(String mensaje) {
    final m = mensaje.toLowerCase();
    if (m.contains('invalid login credentials')) return 'Correo o contraseña incorrectos.';
    if (m.contains('email not confirmed')) return 'La cuenta aún no está confirmada.';
    if (m.contains('invalid refresh token') || m.contains('refresh token not found')) {
      return 'La sesión caducó. Vuelve a entrar.';
    }
    if (m.contains('password should be at least')) {
      final minimo = RegExp(r'\d+').firstMatch(mensaje)?.group(0) ?? '6';
      return 'La contraseña necesita al menos $minimo caracteres.';
    }
    if (m.contains('for security purposes') || m.contains('rate limit')) {
      return 'Se pidió demasiadas veces seguidas. Espera un minuto.';
    }
    return mensaje;
  }
}
