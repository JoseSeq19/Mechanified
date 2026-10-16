/// Arranque de la app de campo de La Meseta.
///
/// Es la app del técnico y del asesor junto al vehículo: mover la orden por el
/// flujo, anotar lo que se encontró, cargar horas, pedir piezas y, sobre todo,
/// hacer las fotos que respaldan el estado del coche.
///
/// Los datos de negocio salen de la API de La Meseta, no de Supabase: de
/// Supabase solo salen la identidad y el almacén de las fotos. Es la misma
/// división que en la web.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'app.dart';

void main() {
  // Sin esto, `DateFormat` con la configuración española se queda sin los
  // nombres de los meses y escribe las fechas en inglés.
  initializeDateFormatting('es');

  runApp(const ProviderScope(child: AppMeseta()));
}
