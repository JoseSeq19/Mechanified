/// Fechas, dinero y números, con las mismas reglas que la web.
///
/// El dinero se escribe con la moneda del taller, que llega en su
/// configuración (`GET /taller`). Mientras no se sepa cuál es, se escribe el
/// número solo: una cifra sin símbolo es mejor que una cifra con el símbolo de
/// otra moneda.
library;

import 'package:intl/intl.dart';

String? _monedaActual;

void fijarMoneda(String? codigo) {
  _monedaActual = codigo;
}

/// Acepta `String` porque la API serializa los decimales como texto, para no
/// perder precisión por el camino.
String formatearMoneda(Object? valor, {String? moneda}) {
  final numero = _aNumero(valor);
  if (numero == null) return '—';

  final codigo = moneda ?? _monedaActual;
  if (codigo == null || codigo.isEmpty) {
    return NumberFormat('#,##0.00', 'es').format(numero);
  }
  return NumberFormat.currency(locale: 'es', name: codigo, decimalDigits: 2).format(numero);
}

String formatearNumero(Object? valor, {int decimales = 2}) {
  final numero = _aNumero(valor);
  if (numero == null) return '—';

  // Sin decimales el patrón no lleva punto: '#,##0.' no es un patrón válido y
  // `NumberFormat` lo rechaza en marcha, no al compilar.
  final patron = decimales <= 0 ? '#,##0' : '#,##0.${'#' * decimales}';
  return NumberFormat(patron, 'es').format(numero);
}

String formatearFecha(String? iso, {bool conHora = false}) {
  if (iso == null || iso.isEmpty) return '—';
  final fecha = DateTime.tryParse(iso);
  if (fecha == null) return '—';

  final patron = conHora ? 'd MMM y, HH:mm' : 'd MMM y';
  return DateFormat(patron, 'es').format(fecha.toLocal());
}

/// "hace 3 h". Es lo que se mira en una lista: cuánto lleva esperando.
String haceCuanto(String? iso) {
  if (iso == null) return '';
  final fecha = DateTime.tryParse(iso);
  if (fecha == null) return '';

  final minutos = DateTime.now().difference(fecha.toLocal()).inMinutes;
  if (minutos < 1) return 'ahora mismo';
  if (minutos < 60) return 'hace $minutos min';

  final horas = minutos ~/ 60;
  if (horas < 24) return 'hace $horas h';

  final dias = horas ~/ 24;
  return dias == 1 ? 'ayer' : 'hace $dias días';
}

double? _aNumero(Object? valor) {
  if (valor == null) return null;
  if (valor is num) return valor.toDouble();
  return double.tryParse(valor.toString());
}
