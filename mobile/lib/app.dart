/// Armazón de la app: rutas y tema.
///
/// El control de acceso vive en el `redirect` del router y en un solo sitio: si
/// no hay sesión, todo lleva al acceso; si la hay, el acceso lleva a las
/// órdenes. Repartir esa decisión por las pantallas es cómo se acaba con una
/// que se olvida de comprobarlo.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'nucleo/sesion.dart';
import 'nucleo/tema.dart';
import 'pantallas/acceso.dart';
import 'pantallas/cuenta.dart';
import 'pantallas/orden.dart';
import 'pantallas/ordenes.dart';

final routerProvider = Provider<GoRouter>((ref) {
  // El router no es un widget y no puede observar providers, así que se le
  // avisa con un notificador: cada cambio de sesión le hace reevaluar el
  // redirect, que es lo que saca a la gente del taller cuando caduca el token.
  final aviso = ValueNotifier<int>(0);
  ref.listen<EstadoSesion>(sesionProvider, (_, __) => aviso.value++);

  final router = GoRouter(
    initialLocation: '/',
    refreshListenable: aviso,
    redirect: (context, state) {
      final sesion = ref.read(sesionProvider);
      final enAcceso = state.matchedLocation == '/acceso';

      switch (sesion.fase) {
        case FaseSesion.comprobando:
          // Mientras se intenta reanudar con el token guardado. Dura lo que
          // tarde una petición; sin esta parada se vería el acceso un instante
          // y se cerraría solo, que parece un fallo.
          return state.matchedLocation == '/cargando' ? null : '/cargando';
        case FaseSesion.fuera:
          return enAcceso ? null : '/acceso';
        case FaseSesion.dentro:
          return enAcceso || state.matchedLocation == '/cargando' ? '/' : null;
      }
    },
    routes: [
      GoRoute(path: '/cargando', builder: (_, __) => const _PantallaCargando()),
      GoRoute(path: '/acceso', builder: (_, __) => const PantallaAcceso()),
      GoRoute(path: '/', builder: (_, __) => const PantallaOrdenes()),
      GoRoute(
        path: '/ordenes/:ordenId',
        builder: (_, estado) => PantallaOrden(ordenId: estado.pathParameters['ordenId']!),
      ),
      GoRoute(path: '/cuenta', builder: (_, __) => const PantallaCuenta()),
    ],
  );

  ref.onDispose(() {
    router.dispose();
    aviso.dispose();
  });

  return router;
});

class AppMeseta extends ConsumerWidget {
  const AppMeseta({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp.router(
      title: 'Mechanified',
      debugShowCheckedModeBanner: false,
      theme: temaMeseta(),
      routerConfig: ref.watch(routerProvider),
    );
  }
}

class _PantallaCargando extends StatelessWidget {
  const _PantallaCargando();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(child: CircularProgressIndicator()),
    );
  }
}
