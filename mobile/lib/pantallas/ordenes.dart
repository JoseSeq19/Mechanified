/// Las órdenes: lo primero que se ve al entrar.
///
/// Para un técnico, por omisión, solo las suyas. Es el filtro que hace que la
/// pantalla sirva de pie junto a la rampa: la pregunta que se hace al abrir la
/// app es "qué me toca ahora", no "qué hay en el taller". El interruptor deja
/// ver el taller entero cuando hace falta —el coche de al lado, el que alguien
/// pregunta por teléfono—.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../datos/modelos.dart';
import '../datos/repositorio.dart';
import '../nucleo/api.dart';
import '../nucleo/formato.dart';
import '../nucleo/sesion.dart';
import '../nucleo/tema.dart';

class PantallaOrdenes extends ConsumerStatefulWidget {
  const PantallaOrdenes({super.key});

  @override
  ConsumerState<PantallaOrdenes> createState() => _PantallaOrdenesState();
}

class _PantallaOrdenesState extends ConsumerState<PantallaOrdenes> {
  final _busqueda = TextEditingController();

  @override
  void dispose() {
    _busqueda.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final claims = ref.watch(claimsProvider);
    final ordenes = ref.watch(ordenesProvider);
    final taller = ref.watch(tallerProvider);
    final soloMias = ref.watch(soloMiasProvider);

    // La moneda del taller, en cuanto se sepa. Hasta entonces las cifras van
    // sin símbolo, que es mejor que con el símbolo de otra moneda.
    taller.whenData((t) => fijarMoneda(t.moneda));

    return Scaffold(
      appBar: AppBar(
        title: Text(taller.maybeWhen(data: (t) => t.nombre, orElse: () => 'Mechanified')),
        actions: [
          IconButton(
            onPressed: () => context.push('/cuenta'),
            icon: const Icon(Icons.person_outline),
            tooltip: 'Mi cuenta',
          ),
        ],
      ),
      body: Column(
        children: [
          if (claims != null && !claims.completos)
            const Padding(
              padding: EdgeInsets.fromLTRB(12, 12, 12, 0),
              child: _Aviso(
                tono: Tonos.alerta,
                texto: 'Tu sesión no trae taller ni rol, así que la API va a rechazar todo. '
                    'Suele ser que tu usuario no tiene perfil activo.',
              ),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
            child: TextField(
              controller: _busqueda,
              textInputAction: TextInputAction.search,
              decoration: InputDecoration(
                hintText: 'Folio, placa o cliente',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _busqueda.text.isEmpty
                    ? null
                    : IconButton(
                        icon: const Icon(Icons.close),
                        onPressed: () {
                          _busqueda.clear();
                          ref.read(busquedaProvider.notifier).state = '';
                          setState(() {});
                        },
                      ),
              ),
              onChanged: (texto) {
                // Se manda a partir de tres caracteres, que es el mínimo que
                // usa el índice de búsqueda del backend.
                ref.read(busquedaProvider.notifier).state = texto.trim().length >= 3 ? texto : '';
                setState(() {});
              },
            ),
          ),
          if (claims?.esTecnico ?? false)
            SwitchListTile(
              value: soloMias,
              onChanged: (valor) => ref.read(soloMiasProvider.notifier).state = valor,
              title: const Text('Solo mis órdenes'),
              dense: true,
            ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () async => ref.invalidate(ordenesProvider),
              child: ordenes.when(
                loading: () => const Center(child: CircularProgressIndicator()),
                error: (e, _) => _Error(
                  mensaje: e is ErrorApi ? e.mensaje : 'No se pudieron cargar las órdenes.',
                  alReintentar: () => ref.invalidate(ordenesProvider),
                ),
                data: (lista) => lista.isEmpty
                    ? _Vacio(soloMias: soloMias, buscando: _busqueda.text.trim().length >= 3)
                    : ListView.builder(
                        // Siempre desplazable, para que el gesto de refrescar
                        // funcione aunque la lista sea corta.
                        physics: const AlwaysScrollableScrollPhysics(),
                        padding: const EdgeInsets.only(bottom: 24, top: 6),
                        itemCount: lista.length,
                        itemBuilder: (context, i) => _Tarjeta(orden: lista[i]),
                      ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Tarjeta extends StatelessWidget {
  const _Tarjeta({required this.orden});

  final OrdenResumen orden;

  @override
  Widget build(BuildContext context) {
    final tono = Tonos.porEstado(orden.estado);

    return Panel(
      alPulsar: () => context.push('/ordenes/${orden.id}'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  orden.folio,
                  style: const TextStyle(
                    fontFamily: 'monospace',
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              Distintivo(
                texto: orden.estadoEtiqueta.isEmpty
                    ? (etiquetasEstado[orden.estado] ?? orden.estado)
                    : orden.estadoEtiqueta,
                tono: tono,
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '${orden.vehiculoPlaca} · ${orden.vehiculoDescripcion}',
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
          Text(orden.clienteNombre, style: const TextStyle(color: Tonos.textoSecundario)),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: Text(
                  '${orden.tecnicoNombre ?? 'Sin técnico'} · ${haceCuanto(orden.fechaIngreso)}',
                  style: const TextStyle(fontSize: 12, color: Tonos.textoSecundario),
                ),
              ),
              if (orden.atrasada)
                const Padding(
                  padding: EdgeInsets.only(right: 8),
                  child: Distintivo(texto: 'Atrasada', tono: Tonos.alerta),
                ),
              Text(
                formatearMoneda(orden.total),
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Vacio extends StatelessWidget {
  const _Vacio({required this.soloMias, required this.buscando});

  final bool soloMias;
  final bool buscando;

  @override
  Widget build(BuildContext context) {
    final String detalle;
    if (buscando) {
      detalle = 'Ninguna orden coincide con lo que escribiste.';
    } else if (soloMias) {
      detalle = 'No tienes órdenes asignadas. Quita "solo mis órdenes" para ver el taller.';
    } else {
      detalle = 'Cuando recepción reciba un vehículo, aparecerá aquí.';
    }

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      children: [
        const SizedBox(height: 80),
        const Icon(Icons.inbox_outlined, size: 48, color: Tonos.textoSecundario),
        const SizedBox(height: 12),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 32),
          child: Text(
            detalle,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Tonos.textoSecundario),
          ),
        ),
      ],
    );
  }
}

class _Error extends StatelessWidget {
  const _Error({required this.mensaje, required this.alReintentar});

  final String mensaje;
  final VoidCallback alReintentar;

  @override
  Widget build(BuildContext context) {
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(24),
      children: [
        const SizedBox(height: 48),
        _Aviso(tono: Tonos.error, texto: mensaje),
        const SizedBox(height: 16),
        OutlinedButton(onPressed: alReintentar, child: const Text('Reintentar')),
      ],
    );
  }
}

class _Aviso extends StatelessWidget {
  const _Aviso({required this.tono, required this.texto});

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
