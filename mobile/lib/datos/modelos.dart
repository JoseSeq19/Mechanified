/// Lo que la API devuelve, con nombres de dominio.
///
/// Los decimales llegan como texto —así los serializa Pydantic, para no perder
/// precisión por el camino— y se guardan como texto. La app no hace cuentas con
/// dinero: las hace Postgres, y aquí solo se muestran. El día que haya que
/// sumar algo, se convierte en ese sitio y se ve.
library;

class Taller {
  const Taller({
    required this.nombre,
    required this.moneda,
    required this.tarifaHora,
    required this.impuestoPct,
    this.telefono,
  });

  final String nombre;
  final String moneda;
  final String tarifaHora;
  final String impuestoPct;
  final String? telefono;

  factory Taller.deJson(Map<String, dynamic> j) => Taller(
        nombre: j['nombre'] as String? ?? 'Taller',
        moneda: j['moneda'] as String? ?? '',
        tarifaHora: '${j['tarifa_hora_default'] ?? '0'}',
        impuestoPct: '${j['impuesto_pct'] ?? '0'}',
        telefono: j['telefono'] as String?,
      );
}

class OrdenResumen {
  const OrdenResumen({
    required this.id,
    required this.folio,
    required this.estado,
    required this.estadoEtiqueta,
    required this.clienteNombre,
    required this.vehiculoPlaca,
    required this.vehiculoDescripcion,
    required this.fechaIngreso,
    required this.total,
    required this.atrasada,
    this.tecnicoNombre,
    this.fechaPromesa,
  });

  final String id;
  final String folio;
  final String estado;
  final String estadoEtiqueta;
  final String clienteNombre;
  final String vehiculoPlaca;
  final String vehiculoDescripcion;
  final String fechaIngreso;
  final String total;
  final bool atrasada;
  final String? tecnicoNombre;
  final String? fechaPromesa;

  factory OrdenResumen.deJson(Map<String, dynamic> j) => OrdenResumen(
        id: j['id'] as String,
        folio: j['folio'] as String,
        estado: j['estado'] as String,
        estadoEtiqueta: j['estado_etiqueta'] as String? ?? '',
        clienteNombre: j['cliente_nombre'] as String? ?? '',
        vehiculoPlaca: j['vehiculo_placa'] as String? ?? '',
        vehiculoDescripcion: j['vehiculo_descripcion'] as String? ?? '',
        fechaIngreso: j['fecha_ingreso'] as String? ?? '',
        total: '${j['total'] ?? '0'}',
        atrasada: j['atrasada'] as bool? ?? false,
        tecnicoNombre: j['tecnico_nombre'] as String?,
        fechaPromesa: j['fecha_promesa'] as String?,
      );
}

class Orden {
  const Orden({
    required this.resumen,
    required this.motivoIngreso,
    required this.totalManoObra,
    required this.totalRepuestos,
    required this.transicionesPosibles,
    this.inventarioIngreso = const {},
    this.kilometrajeIngreso,
    this.nivelCombustible,
    this.fechaEntrega,
    this.asesorNombre,
    this.notasInternas,
    this.motivoCancelacion,
  });

  final OrdenResumen resumen;
  final String motivoIngreso;
  final String totalManoObra;
  final String totalRepuestos;

  /// Qué puede hacer **este** usuario con la orden ahora mismo. Lo decide la
  /// máquina de estados del backend, así que la app pinta un botón por cada uno
  /// y no replica ninguna regla del flujo.
  final List<String> transicionesPosibles;

  /// Lo que se quedó en el taller con el vehículo. La API lo normaliza a pares
  /// de texto, así que aquí solo hay que leerlo.
  final Map<String, String> inventarioIngreso;

  final int? kilometrajeIngreso;
  final int? nivelCombustible;
  final String? fechaEntrega;
  final String? asesorNombre;
  final String? notasInternas;
  final String? motivoCancelacion;

  String get id => resumen.id;
  String get folio => resumen.folio;
  String get estado => resumen.estado;
  bool get cerrada => estado == 'entregado' || estado == 'cancelado';

  factory Orden.deJson(Map<String, dynamic> j) => Orden(
        resumen: OrdenResumen.deJson(j),
        motivoIngreso: j['motivo_ingreso'] as String? ?? '',
        totalManoObra: '${j['total_mano_obra'] ?? '0'}',
        totalRepuestos: '${j['total_repuestos'] ?? '0'}',
        transicionesPosibles:
            ((j['transiciones_posibles'] as List?) ?? const []).map((e) => '$e').toList(),
        inventarioIngreso: {
          for (final par in ((j['inventario_ingreso'] as Map?) ?? const {}).entries)
            '${par.key}': '${par.value ?? ''}',
        },
        kilometrajeIngreso: (j['kilometraje_ingreso'] as num?)?.toInt(),
        nivelCombustible: (j['nivel_combustible'] as num?)?.toInt(),
        fechaEntrega: j['fecha_entrega'] as String?,
        asesorNombre: j['asesor_nombre'] as String?,
        notasInternas: j['notas_internas'] as String?,
        motivoCancelacion: j['motivo_cancelacion'] as String?,
      );
}

class Hallazgo {
  const Hallazgo({
    required this.id,
    required this.sistema,
    required this.descripcion,
    required this.severidad,
    required this.severidadEtiqueta,
    required this.requiereRepuesto,
  });

  final String id;
  final String sistema;
  final String descripcion;
  final String severidad;
  final String severidadEtiqueta;
  final bool requiereRepuesto;

  factory Hallazgo.deJson(Map<String, dynamic> j) => Hallazgo(
        id: j['id'] as String,
        sistema: j['sistema'] as String? ?? '',
        descripcion: j['descripcion'] as String? ?? '',
        severidad: j['severidad'] as String? ?? 'moderada',
        severidadEtiqueta: j['severidad_etiqueta'] as String? ?? '',
        requiereRepuesto: j['requiere_repuesto'] as bool? ?? false,
      );
}

class Diagnostico {
  const Diagnostico({
    required this.id,
    required this.resumen,
    required this.horasEstimadas,
    required this.hallazgos,
    required this.creadoEn,
    this.tecnicoNombre,
  });

  final String id;
  final String resumen;
  final String horasEstimadas;
  final List<Hallazgo> hallazgos;
  final String creadoEn;
  final String? tecnicoNombre;

  factory Diagnostico.deJson(Map<String, dynamic> j) => Diagnostico(
        id: j['id'] as String,
        resumen: j['resumen'] as String? ?? '',
        horasEstimadas: '${j['horas_estimadas'] ?? '0'}',
        hallazgos: ((j['hallazgos'] as List?) ?? const [])
            .map((h) => Hallazgo.deJson(h as Map<String, dynamic>))
            .toList(),
        creadoEn: j['creado_en'] as String? ?? '',
        tecnicoNombre: j['tecnico_nombre'] as String?,
      );
}

class LineaManoObra {
  const LineaManoObra({
    required this.id,
    required this.descripcion,
    required this.horas,
    required this.tarifaHora,
    required this.subtotal,
    this.tecnicoNombre,
  });

  final String id;
  final String descripcion;
  final String horas;
  final String tarifaHora;
  final String subtotal;
  final String? tecnicoNombre;

  factory LineaManoObra.deJson(Map<String, dynamic> j) => LineaManoObra(
        id: j['id'] as String,
        descripcion: j['descripcion'] as String? ?? '',
        horas: '${j['horas'] ?? '0'}',
        tarifaHora: '${j['tarifa_hora'] ?? '0'}',
        subtotal: '${j['subtotal'] ?? '0'}',
        tecnicoNombre: j['tecnico_nombre'] as String?,
      );
}

class ResumenManoObra {
  const ResumenManoObra({required this.lineas, required this.totalHoras, required this.total});

  final List<LineaManoObra> lineas;
  final String totalHoras;
  final String total;

  factory ResumenManoObra.deJson(Map<String, dynamic> j) => ResumenManoObra(
        lineas: ((j['lineas'] as List?) ?? const [])
            .map((l) => LineaManoObra.deJson(l as Map<String, dynamic>))
            .toList(),
        totalHoras: '${j['total_horas'] ?? '0'}',
        total: '${j['total'] ?? '0'}',
      );
}

class LineaRepuesto {
  const LineaRepuesto({
    required this.id,
    required this.descripcion,
    required this.cantidad,
    required this.precioUnitario,
    required this.subtotal,
    required this.estado,
    required this.estadoEtiqueta,
    this.sku,
    this.solicitanteNombre,
  });

  final String id;
  final String descripcion;
  final String cantidad;
  final String precioUnitario;
  final String subtotal;
  final String estado;
  final String estadoEtiqueta;
  final String? sku;
  final String? solicitanteNombre;

  factory LineaRepuesto.deJson(Map<String, dynamic> j) => LineaRepuesto(
        id: j['id'] as String,
        descripcion: j['descripcion'] as String? ?? '',
        cantidad: '${j['cantidad'] ?? '0'}',
        precioUnitario: '${j['precio_unitario'] ?? '0'}',
        subtotal: '${j['subtotal'] ?? '0'}',
        estado: j['estado'] as String? ?? '',
        estadoEtiqueta: j['estado_etiqueta'] as String? ?? '',
        sku: j['sku'] as String?,
        solicitanteNombre: j['solicitante_nombre'] as String?,
      );
}

class ResumenRepuestos {
  const ResumenRepuestos({required this.lineas, required this.total, required this.pendientes});

  final List<LineaRepuesto> lineas;
  final String total;
  final int pendientes;

  factory ResumenRepuestos.deJson(Map<String, dynamic> j) => ResumenRepuestos(
        lineas: ((j['lineas'] as List?) ?? const [])
            .map((l) => LineaRepuesto.deJson(l as Map<String, dynamic>))
            .toList(),
        total: '${j['total'] ?? '0'}',
        pendientes: (j['pendientes'] as num?)?.toInt() ?? 0,
      );
}

class Adjunto {
  const Adjunto({
    required this.id,
    required this.contexto,
    required this.contextoEtiqueta,
    required this.rutaStorage,
    required this.nombreArchivo,
    required this.puedeBorrar,
    required this.creadoEn,
    this.mime,
    this.tamanoBytes,
    this.descripcion,
    this.autorNombre,
  });

  final String id;
  final String contexto;
  final String contextoEtiqueta;
  final String rutaStorage;
  final String nombreArchivo;
  final bool puedeBorrar;
  final String creadoEn;
  final String? mime;
  final int? tamanoBytes;
  final String? descripcion;
  final String? autorNombre;

  bool get esImagen => (mime ?? '').startsWith('image/');

  factory Adjunto.deJson(Map<String, dynamic> j) => Adjunto(
        id: j['id'] as String,
        contexto: j['contexto'] as String? ?? 'ingreso',
        contextoEtiqueta: j['contexto_etiqueta'] as String? ?? '',
        rutaStorage: j['ruta_storage'] as String,
        nombreArchivo: j['nombre_archivo'] as String? ?? 'archivo',
        puedeBorrar: j['puede_borrar'] as bool? ?? false,
        creadoEn: j['creado_en'] as String? ?? '',
        mime: j['mime'] as String?,
        tamanoBytes: (j['tamano_bytes'] as num?)?.toInt(),
        descripcion: j['descripcion'] as String?,
        autorNombre: j['autor_nombre'] as String?,
      );
}

/// Los momentos de la orden a los que puede pertenecer una foto. Reflejan el
/// enum `public.contexto_adjunto`.
const contextosAdjunto = <String, String>{
  'ingreso': 'Recepción',
  'diagnostico': 'Diagnóstico',
  'reparacion': 'Reparación',
  'calidad': 'Control de calidad',
  'entrega': 'Entrega',
};

/// Etiquetas de los estados de la orden. Reflejan `public.estado_orden`.
const etiquetasEstado = <String, String>{
  'recibido': 'Recibido',
  'en_diagnostico': 'En diagnóstico',
  'presupuesto_pendiente': 'Presupuesto pendiente',
  'aprobado': 'Aprobado',
  'en_reparacion': 'En reparación',
  'control_calidad': 'Control de calidad',
  'listo_para_entrega': 'Listo para entrega',
  'entregado': 'Entregado',
  'cancelado': 'Cancelado',
};

/// Transiciones que el backend exige justificar. Es la misma lista que la web.
const exigenComentario = <String>{'cancelado'};
