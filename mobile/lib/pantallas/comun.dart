/// Piezas que comparten las pantallas de la ficha.
///
/// La `Seccion` es la misma idea que `Seccion` en el sistema de diseño de la
/// web: un bloque con título, resumen y una acción a la derecha. La ficha apila
/// cinco, y sin esto cada una repetiría la misma cabecera con medidas
/// ligeramente distintas.
library;

import 'package:flutter/material.dart';

import '../nucleo/tema.dart';

class Seccion extends StatelessWidget {
  const Seccion({
    super.key,
    required this.titulo,
    required this.children,
    this.resumen,
    this.accion,
  });

  final String titulo;
  final String? resumen;
  final Widget? accion;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Panel(
      padding: EdgeInsets.zero,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 12, 10, 12),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        titulo,
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                      ),
                      if (resumen != null)
                        Padding(
                          padding: const EdgeInsets.only(top: 2),
                          child: Text(
                            resumen!,
                            style: const TextStyle(
                              fontSize: 12,
                              color: Tonos.textoSecundario,
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
                if (accion != null) accion!,
              ],
            ),
          ),
          const Divider(height: 1),
          ...children,
        ],
      ),
    );
  }
}

/// Fila de una lista dentro de una sección.
class Linea extends StatelessWidget {
  const Linea({super.key, required this.titulo, this.detalle, this.importe, this.alFinal});

  final String titulo;
  final String? detalle;
  final String? importe;
  final Widget? alFinal;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(titulo, style: const TextStyle(fontWeight: FontWeight.w600)),
                if (detalle != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(
                      detalle!,
                      style: const TextStyle(fontSize: 12, color: Tonos.textoSecundario),
                    ),
                  ),
              ],
            ),
          ),
          if (importe != null)
            Padding(
              padding: const EdgeInsets.only(left: 8),
              child: Text(importe!, style: const TextStyle(fontWeight: FontWeight.w600)),
            ),
          if (alFinal != null) alFinal!,
        ],
      ),
    );
  }
}

/// Texto para cuando una sección está vacía. Dice qué iría ahí, no "sin datos".
class Vacio extends StatelessWidget {
  const Vacio({super.key, required this.texto});

  final String texto;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(14),
      child: Text(
        texto,
        style: const TextStyle(color: Tonos.textoSecundario, fontSize: 13),
      ),
    );
  }
}

class Aviso extends StatelessWidget {
  const Aviso({super.key, required this.tono, required this.texto});

  final Color tono;
  final String texto;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Tonos.fondoDe(tono),
        border: Border.all(color: Tonos.borde),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(texto, style: TextStyle(color: tono)),
    );
  }
}

/// Mensaje breve de resultado. En un móvil en la mano es la forma de confirmar
/// algo sin robar la pantalla.
void avisar(BuildContext context, String mensaje, {bool esError = false}) {
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(mensaje),
      backgroundColor: esError ? Tonos.error : null,
      duration: Duration(seconds: esError ? 6 : 3),
    ),
  );
}

/// Un formulario en una hoja que sube desde abajo.
///
/// Se usa en vez de un diálogo centrado porque aquí se escribe con el pulgar:
/// la hoja deja el teclado y los campos en la mitad baja de la pantalla, que es
/// donde llega la mano.
Future<T?> mostrarHoja<T>({
  required BuildContext context,
  required String titulo,
  required Widget Function(BuildContext) contenido,
}) {
  return showModalBottomSheet<T>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Tonos.panel,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
    ),
    builder: (contexto) => Padding(
      // El hueco del teclado, para que el campo que se escribe no quede debajo.
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(contexto).bottom),
      child: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Center(
                child: Container(
                  width: 44,
                  height: 4,
                  margin: const EdgeInsets.only(bottom: 14),
                  decoration: BoxDecoration(
                    color: Tonos.borde,
                    borderRadius: BorderRadius.circular(999),
                  ),
                ),
              ),
              Text(titulo, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
              const SizedBox(height: 14),
              contenido(contexto),
            ],
          ),
        ),
      ),
    ),
  );
}
