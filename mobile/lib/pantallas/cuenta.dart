/// Mi cuenta: quién soy, en qué taller y cómo salir.
///
/// La contraseña se cambia desde aquí porque el alta entrega una temporal, y
/// quien trabaja en campo no vuelve al ordenador para cambiarla. Va directa a
/// Supabase, sin pasar por la API de La Meseta, para que el backend no vea
/// nunca una contraseña.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../datos/repositorio.dart';
import '../nucleo/auth.dart';
import '../nucleo/formato.dart';
import '../nucleo/sesion.dart';
import '../nucleo/tema.dart';
import 'comun.dart';

class PantallaCuenta extends ConsumerWidget {
  const PantallaCuenta({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final claims = ref.watch(claimsProvider);
    final taller = ref.watch(tallerProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Mi cuenta')),
      body: ListView(
        padding: const EdgeInsets.only(bottom: 32),
        children: [
          Seccion(
            titulo: 'Quién soy',
            children: [
              Linea(titulo: claims?.email ?? 'Sin correo', detalle: claims?.rolEtiqueta),
              const Divider(height: 1),
              taller.when(
                loading: () => const Vacio(texto: 'Cargando el taller…'),
                error: (e, _) => Padding(
                  padding: const EdgeInsets.all(14),
                  child: Aviso(tono: Tonos.error, texto: 'No se pudo leer el taller: $e'),
                ),
                data: (t) => Column(
                  children: [
                    Linea(titulo: t.nombre, detalle: 'Taller'),
                    const Divider(height: 1),
                    Linea(
                      titulo: 'Tarifa por hora',
                      detalle: 'Impuesto ${t.impuestoPct}%',
                      importe: formatearMoneda(t.tarifaHora, moneda: t.moneda),
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (claims != null && !claims.completos)
            Padding(
              padding: const EdgeInsets.all(12),
              child: Aviso(
                tono: Tonos.alerta,
                texto: 'Tu sesión no trae taller ni rol. Mientras siga así, la API va a '
                    'rechazar todo: avisa a quien administra el taller.',
              ),
            ),
          Seccion(
            titulo: 'Acceso',
            children: [
              ListTile(
                leading: const Icon(Icons.key_outlined),
                title: const Text('Cambiar mi contraseña'),
                onTap: () => _cambiarClave(context, ref),
              ),
              const Divider(height: 1),
              ListTile(
                leading: const Icon(Icons.logout, color: Tonos.error),
                title: const Text('Cerrar sesión', style: TextStyle(color: Tonos.error)),
                subtitle: const Text('Habrá que volver a escribir la contraseña'),
                onTap: () => ref.read(sesionProvider.notifier).salir(),
              ),
            ],
          ),
          const Padding(
            padding: EdgeInsets.all(16),
            child: Text(
              'Mechanified · app de campo',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 12, color: Tonos.textoSecundario),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _cambiarClave(BuildContext context, WidgetRef ref) async {
    final clave = await mostrarHoja<String>(
      context: context,
      titulo: 'Cambiar mi contraseña',
      contenido: (_) => const _FormularioClave(),
    );
    if (clave == null) return;

    try {
      await ref.read(sesionProvider.notifier).cambiarClave(clave);
      if (context.mounted) {
        avisar(context, 'Contraseña cambiada. La próxima vez que entres, usa la nueva.');
      }
    } on ErrorAuth catch (e) {
      if (context.mounted) avisar(context, e.mensaje, esError: true);
    }
  }
}

class _FormularioClave extends StatefulWidget {
  const _FormularioClave();

  @override
  State<_FormularioClave> createState() => _FormularioClaveState();
}

class _FormularioClaveState extends State<_FormularioClave> {
  final _nueva = TextEditingController();
  final _repetida = TextEditingController();

  @override
  void dispose() {
    _nueva.dispose();
    _repetida.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final nueva = _nueva.text;
    final coinciden = nueva.isNotEmpty && nueva == _repetida.text;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: _nueva,
          obscureText: true,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Contraseña nueva'),
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _repetida,
          obscureText: true,
          decoration: InputDecoration(
            labelText: 'Repítela',
            errorText: _repetida.text.isNotEmpty && !coinciden ? 'No coinciden' : null,
          ),
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: 14),
        FilledButton(
          onPressed: coinciden ? () => Navigator.pop(context, nueva) : null,
          child: const Text('Cambiar'),
        ),
      ],
    );
  }
}
