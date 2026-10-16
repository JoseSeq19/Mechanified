/// Estado de sesión de la app de campo.
///
/// Guarda las credenciales en memoria y las renueva cuando están por caducar.
/// Todo lo que hable con la API pide el token aquí, con `tokenVigente()`, en
/// vez de guardarse una copia: así una renovación no deja a nadie con el token
/// viejo en la mano.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'auth.dart';

enum FaseSesion { comprobando, fuera, dentro }

class EstadoSesion {
  const EstadoSesion({required this.fase, this.credenciales, this.error});

  final FaseSesion fase;
  final Credenciales? credenciales;
  final String? error;

  Claims? get claims => credenciales?.claims;
  bool get dentro => fase == FaseSesion.dentro && credenciales != null;
}

final authProvider = Provider<AuthSupabase>((ref) => AuthSupabase());

final sesionProvider = StateNotifierProvider<SesionNotifier, EstadoSesion>(
  (ref) => SesionNotifier(ref.watch(authProvider))..reanudar(),
);

/// Atajo para quien solo necesita saber quién es el usuario.
final claimsProvider = Provider<Claims?>((ref) => ref.watch(sesionProvider).claims);

class SesionNotifier extends StateNotifier<EstadoSesion> {
  SesionNotifier(this._auth) : super(const EstadoSesion(fase: FaseSesion.comprobando));

  final AuthSupabase _auth;

  /// Intenta abrir sesión con el token de refresco guardado en el dispositivo.
  Future<void> reanudar() async {
    try {
      final credenciales = await _auth.reanudar();
      if (!mounted) return;
      state = credenciales == null
          ? const EstadoSesion(fase: FaseSesion.fuera)
          : EstadoSesion(fase: FaseSesion.dentro, credenciales: credenciales);
    } catch (_) {
      if (!mounted) return;
      // Sin red al arrancar no es un error que merezca pantalla: se pide la
      // contraseña, que es lo que se podrá hacer cuando vuelva la cobertura.
      state = const EstadoSesion(fase: FaseSesion.fuera);
    }
  }

  Future<void> entrar(String correo, String clave) async {
    final credenciales = await _auth.entrar(correo, clave);
    await _auth.guardar(credenciales);
    if (!mounted) return;
    state = EstadoSesion(fase: FaseSesion.dentro, credenciales: credenciales);
  }

  Future<void> salir() async {
    await _auth.olvidar();
    if (!mounted) return;
    state = const EstadoSesion(fase: FaseSesion.fuera);
  }

  Future<void> cambiarClave(String clave) async {
    final token = await tokenVigente();
    if (token == null) throw ErrorAuth('La sesión caducó. Vuelve a entrar.');
    await _auth.cambiarClave(token, clave);
  }

  /// El token con el que se puede llamar ahora mismo, renovándolo si toca.
  ///
  /// Devuelve null cuando la sesión ya no se puede sostener; quien llama
  /// responde con un error de autenticación y el router manda al acceso.
  Future<String?> tokenVigente() async {
    final actuales = state.credenciales;
    if (actuales == null) return null;
    if (!actuales.porCaducar) return actuales.accessToken;

    try {
      final frescas = await _auth.renovar(actuales.refreshToken);
      await _auth.guardar(frescas);
      if (mounted) {
        state = EstadoSesion(fase: FaseSesion.dentro, credenciales: frescas);
      }
      return frescas.accessToken;
    } on ErrorAuth {
      await _auth.olvidar();
      if (mounted) {
        state = const EstadoSesion(
          fase: FaseSesion.fuera,
          error: 'La sesión caducó. Vuelve a entrar.',
        );
      }
      return null;
    }
  }
}
