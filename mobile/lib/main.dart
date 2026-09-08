/// Arranque de la app de campo de Mechanified.
/// Router, tema y pantallas llegan en la Fase 6.
import 'package:flutter/material.dart';

void main() => runApp(const AppMechanified());

class AppMechanified extends StatelessWidget {
  const AppMechanified({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Mechanified',
      debugShowCheckedModeBanner: false,
      home: const Scaffold(
        body: Center(child: Text('Mechanified — Fase 6')),
      ),
    );
  }
}
