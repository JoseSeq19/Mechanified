/// Entrar al taller.
///
/// Dos modos en la misma pantalla: la contraseña, y pedir el correo de
/// recuperación cuando no se recuerda. Lo segundo abre la web, no la app: la
/// pantalla que pone una contraseña nueva desde un enlace ya existe allí.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../nucleo/auth.dart';
import '../nucleo/config.dart';
import '../nucleo/sesion.dart';
import '../nucleo/tema.dart';

class PantallaAcceso extends ConsumerStatefulWidget {
  const PantallaAcceso({super.key});

  @override
  ConsumerState<PantallaAcceso> createState() => _PantallaAccesoState();
}

class _PantallaAccesoState extends ConsumerState<PantallaAcceso> {
  final _correo = TextEditingController();
  final _clave = TextEditingController();

  bool _recuperando = false;
  bool _enviando = false;
  bool _pedido = false;
  String? _error;

  @override
  void dispose() {
    _correo.dispose();
    _clave.dispose();
    super.dispose();
  }

  Future<void> _entrar() async {
    setState(() {
      _error = null;
      _enviando = true;
    });
    try {
      await ref.read(sesionProvider.notifier).entrar(_correo.text, _clave.text);
    } on ErrorAuth catch (e) {
      if (mounted) setState(() => _error = e.mensaje);
    } catch (e) {
      if (mounted) setState(() => _error = 'No se pudo iniciar sesión: $e');
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  Future<void> _pedirEnlace() async {
    setState(() {
      _error = null;
      _enviando = true;
    });
    try {
      await ref.read(authProvider).pedirRecuperacion(_correo.text);
      if (mounted) setState(() => _pedido = true);
    } on ErrorAuth catch (e) {
      if (mounted) setState(() => _error = e.mensaje);
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!Config.completa) return const _PantallaSinConfigurar();

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const _Marca(),
                  const SizedBox(height: 8),
                  Text(
                    _recuperando
                        ? 'Escribe el correo con el que entras y te llega un enlace para cambiar la contraseña.'
                        : 'Entra con la cuenta que te dio tu administrador.',
                    style: const TextStyle(color: Tonos.textoSecundario),
                  ),
                  const SizedBox(height: 24),
                  if (_pedido)
                    _AvisoCaja(
                      tono: Tonos.marca,
                      texto: 'Si esa dirección tiene cuenta, va en camino un correo con un '
                          'enlace. Se abre en la web, sirve una vez y caduca.',
                    )
                  else ...[
                    TextField(
                      controller: _correo,
                      keyboardType: TextInputType.emailAddress,
                      autocorrect: false,
                      textInputAction: TextInputAction.next,
                      decoration: const InputDecoration(labelText: 'Correo'),
                    ),
                    const SizedBox(height: 12),
                    if (!_recuperando)
                      TextField(
                        controller: _clave,
                        obscureText: true,
                        textInputAction: TextInputAction.done,
                        decoration: const InputDecoration(labelText: 'Contraseña'),
                        onSubmitted: (_) => _enviando ? null : _entrar(),
                      ),
                    if (_error != null) ...[
                      const SizedBox(height: 12),
                      _AvisoCaja(tono: Tonos.error, texto: _error!),
                    ],
                    const SizedBox(height: 20),
                    FilledButton(
                      onPressed: _enviando ? null : (_recuperando ? _pedirEnlace : _entrar),
                      child: Text(
                        _enviando
                            ? 'Un momento…'
                            : (_recuperando ? 'Mandarme el enlace' : 'Entrar'),
                      ),
                    ),
                  ],
                  const SizedBox(height: 12),
                  TextButton(
                    onPressed: _enviando
                        ? null
                        : () => setState(() {
                              _recuperando = !_recuperando;
                              _pedido = false;
                              _error = null;
                            }),
                    child: Text(
                      _recuperando ? 'Volver al acceso' : 'No recuerdo mi contraseña',
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Sistema interno. Las cuentas las crea la administración del taller.',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 12, color: Tonos.textoSecundario),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _Marca extends StatelessWidget {
  const _Marca();

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 36,
          height: 36,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            gradient: const LinearGradient(colors: [Tonos.marca, Tonos.marcaOscura]),
            borderRadius: BorderRadius.circular(9),
          ),
          child: const Text(
            'M',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 18),
          ),
        ),
        const SizedBox(width: 10),
        const Text(
          'Mechanified',
          style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
        ),
      ],
    );
  }
}

class _AvisoCaja extends StatelessWidget {
  const _AvisoCaja({required this.tono, required this.texto});

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

/// Qué se ve si la app se compiló sin apuntar a ningún servidor.
///
/// Es un fallo de arranque, no del usuario, así que dice exactamente qué falta
/// y cómo se pasa, en vez de fallar al primer toque con un error de red.
class _PantallaSinConfigurar extends StatelessWidget {
  const _PantallaSinConfigurar();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Falta configurar la app',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 12),
              Text('No llegaron estos valores: ${Config.faltantes.join(', ')}.'),
              const SizedBox(height: 12),
              const Text(
                'Se pasan al compilar. En desarrollo basta con el archivo que ya '
                'existe en el proyecto:',
                style: TextStyle(color: Tonos.textoSecundario),
              ),
              const SizedBox(height: 8),
              const SelectableText(
                'flutter run --dart-define-from-file=.env',
                style: TextStyle(fontFamily: 'monospace'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
