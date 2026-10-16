/// Tema de la app de campo.
///
/// Los colores son los mismos tokens que `web/src/styles/tokens.css`: es el
/// mismo producto, y quien usa las dos cosas tiene que reconocerlo. Lo que
/// cambia son las medidas, porque aquí se toca con el dedo y muchas veces con
/// guantes: los objetivos no bajan de 48 puntos y el texto no baja de 15.
library;

import 'package:flutter/material.dart';

class Tonos {
  const Tonos._();

  /// Petróleo de la marca. Los valores son los de `--mch-petroleo-*`.
  static const marca = Color(0xFF0F5C63);
  static const marcaOscura = Color(0xFF0A4046);
  static const marcaTenue = Color(0xFFEFF6F5);

  static const fondo = Color(0xFFF4F7F6);
  static const panel = Color(0xFFFFFFFF);
  static const borde = Color(0xFFDDE4E4);
  static const lineaSuave = Color(0xFFEBEFEF);
  static const texto = Color(0xFF10191C);
  static const textoSecundario = Color(0xFF4A5A5E);

  static const exito = Color(0xFF1F7A4D);
  static const exitoFondo = Color(0xFFE4F2EA);
  static const alerta = Color(0xFFB3541E);
  static const alertaFondo = Color(0xFFFBEADF);
  static const error = Color(0xFFA32B2B);
  static const errorFondo = Color(0xFFF8E5E5);

  /// El fondo que acompaña a cada color de aviso.
  ///
  /// Son constantes y no transparencias calculadas a propósito: el valor
  /// mezclado ya está decidido en los tokens de la web, y calcularlo aquí
  /// daría dos productos con el mismo color pero distinto tono.
  static Color fondoDe(Color tono) {
    if (tono == error) return errorFondo;
    if (tono == alerta) return alertaFondo;
    if (tono == exito) return exitoFondo;
    return marcaTenue;
  }

  /// Un color por familia de estado, igual que los tonos del tablero de la web.
  static Color porEstado(String estado) {
    switch (estado) {
      case 'recibido':
        return textoSecundario;
      case 'en_diagnostico':
      case 'en_reparacion':
        return marca;
      case 'presupuesto_pendiente':
        return alerta;
      case 'aprobado':
      case 'control_calidad':
        return marcaOscura;
      case 'listo_para_entrega':
        return exito;
      case 'entregado':
        return textoSecundario;
      case 'cancelado':
        return error;
      default:
        return textoSecundario;
    }
  }
}

ThemeData temaMeseta() {
  final base = ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(
      seedColor: Tonos.marca,
      primary: Tonos.marca,
      surface: Tonos.panel,
    ),
    scaffoldBackgroundColor: Tonos.fondo,
  );

  return base.copyWith(
    textTheme: base.textTheme.apply(
      bodyColor: Tonos.texto,
      displayColor: Tonos.texto,
      // Un punto por encima del tamaño de serie: la pantalla se mira a un brazo
      // de distancia y con luz de taller.
      fontSizeDelta: 1,
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: Tonos.marca,
      foregroundColor: Colors.white,
      elevation: 0,
      centerTitle: false,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Tonos.panel,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 16),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: Tonos.borde),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: Tonos.borde),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: Tonos.marca,
        foregroundColor: Colors.white,
        // 52 de alto: se pulsa con el dedo, de pie, al lado del coche.
        minimumSize: const Size.fromHeight(52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: Tonos.marca,
        minimumSize: const Size.fromHeight(52),
        side: const BorderSide(color: Tonos.borde),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
      ),
    ),
    snackBarTheme: const SnackBarThemeData(behavior: SnackBarBehavior.floating),
    dividerTheme: const DividerThemeData(color: Tonos.borde, space: 1, thickness: 1),
  );
}

/// Panel del sistema de diseño: fondo, borde y esquina, y nada más.
///
/// Se escribe aquí en vez de configurar `cardTheme` porque el tipo de ese ajuste
/// cambió de nombre entre versiones de Flutter, y esta app tiene que compilar
/// con la que tenga instalada quien la despliegue.
class Panel extends StatelessWidget {
  const Panel({super.key, required this.child, this.padding, this.alPulsar});

  final Widget child;
  final EdgeInsetsGeometry? padding;
  final VoidCallback? alPulsar;

  @override
  Widget build(BuildContext context) {
    final contenido = Padding(
      padding: padding ?? const EdgeInsets.all(14),
      child: child,
    );

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: Tonos.panel,
        border: Border.all(color: Tonos.borde),
        borderRadius: BorderRadius.circular(12),
      ),
      clipBehavior: Clip.antiAlias,
      child: alPulsar == null
          ? contenido
          : InkWell(onTap: alPulsar, child: contenido),
    );
  }
}

/// Distintivo de estado: un punto de color y el texto.
///
/// El color nunca informa solo, igual que en la web: al lado va siempre la
/// etiqueta, porque un taller con luz mala y guantes sucios no es sitio para
/// distinguir dos verdes.
class Distintivo extends StatelessWidget {
  const Distintivo({super.key, required this.texto, required this.tono});

  final String texto;
  final Color tono;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: Tonos.fondoDe(tono),
        border: Border.all(color: Tonos.borde),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: tono, shape: BoxShape.circle),
          ),
          const SizedBox(width: 6),
          Text(
            texto,
            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: tono),
          ),
        ],
      ),
    );
  }
}
