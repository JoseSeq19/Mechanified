/// Configuración del entorno.
///
/// Los tres valores llegan por `--dart-define`, no por un archivo que la app
/// lea en marcha: en un móvil el paquete instalado es el que es, y un `.env`
/// dentro del bundle sería un archivo de texto que cualquiera puede abrir.
///
/// En desarrollo no hace falta escribirlos a mano, porque Flutter sabe leerlos
/// del archivo que ya existe en el proyecto:
///
///     flutter run --dart-define-from-file=.env
///
/// `MCH_API_URL` apunta a la API de La Meseta y `MCH_SUPABASE_*` al proyecto
/// de Supabase, que es quien autentica y quien guarda las fotos. Desde el
/// emulador de Android, `localhost` es el propio emulador: la máquina de
/// desarrollo es `10.0.2.2`, y por eso es lo que trae `.env.example`.
library;

class Config {
  const Config._();

  static const apiUrl = String.fromEnvironment('MCH_API_URL');
  static const supabaseUrl = String.fromEnvironment('MCH_SUPABASE_URL');
  static const supabaseAnonKey = String.fromEnvironment('MCH_SUPABASE_ANON_KEY');

  /// Bucket de las fotos. El mismo que declara la migración 001000.
  static const bucketEvidencias = 'mch-evidencias';

  static bool get completa =>
      apiUrl.isNotEmpty && supabaseUrl.isNotEmpty && supabaseAnonKey.isNotEmpty;

  /// Qué falta, para poder decirlo en pantalla en vez de fallar al primer toque.
  static List<String> get faltantes => <String>[
        if (apiUrl.isEmpty) 'MCH_API_URL',
        if (supabaseUrl.isEmpty) 'MCH_SUPABASE_URL',
        if (supabaseAnonKey.isEmpty) 'MCH_SUPABASE_ANON_KEY',
      ];
}
