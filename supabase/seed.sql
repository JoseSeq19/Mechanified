-- =============================================================================
-- Mechanified · seed de desarrollo
--
-- Taller ficticio "Delta Motors" con datos suficientes para trabajar contra la
-- API sin capturar nada a mano.
--
-- SOLO PARA DESARROLLO LOCAL. Crea usuarios directamente en auth.users con una
-- contraseña conocida; nunca debe correr contra un entorno real.
--
-- Corre con el rol `postgres`, que omite RLS. Es la única vía del proyecto que
-- escribe sin pasar por las políticas.
--
-- Las órdenes no se insertan con su estado final: se avanzan paso a paso, así
-- que este archivo también ejercita la máquina de estados y deja la bitácora
-- de `orden_eventos` poblada de forma realista.
-- =============================================================================

-- Identificadores fijos para que el seed sea reproducible entre reinicios.
\set taller_id       '''a1000000-0000-4000-8000-000000000001'''
\set u_admin         '''b1000000-0000-4000-8000-000000000001'''
\set u_asesor        '''b1000000-0000-4000-8000-000000000002'''
\set u_tecnico       '''b1000000-0000-4000-8000-000000000003'''
\set u_repuestos     '''b1000000-0000-4000-8000-000000000004'''

-- -----------------------------------------------------------------------------
-- Taller
-- -----------------------------------------------------------------------------

insert into public.talleres (
  id, nombre, slug, identificacion_fiscal, direccion, telefono, email,
  zona_horaria, moneda, tarifa_hora_default, impuesto_pct, prefijo_orden,
  dias_validez_presupuesto
) values (
  :taller_id, 'Delta Motors', 'delta-motors', 'J-40123456-7',
  'Av. Principal de Los Ruices, Galpón 14, Caracas',
  '+58 212 555 0142', 'contacto@deltamotors.test',
  'America/Caracas', 'USD', 18.00, 16.00, 'DLT', 15
);

-- -----------------------------------------------------------------------------
-- Usuarios de Supabase Auth
-- Contraseña de los cuatro: Mechanified123!
-- -----------------------------------------------------------------------------

insert into auth.users (
  instance_id, id, aud, role, email, encrypted_password,
  email_confirmed_at, created_at, updated_at,
  raw_app_meta_data, raw_user_meta_data, is_super_admin
)
select
  '00000000-0000-0000-0000-000000000000',
  u.id, 'authenticated', 'authenticated', u.email,
  extensions.crypt('Mechanified123!', extensions.gen_salt('bf')),
  now(), now(), now(),
  '{"provider":"email","providers":["email"]}'::jsonb,
  jsonb_build_object('nombre_completo', u.nombre),
  false
from (values
  (:u_admin::uuid,     'admin@deltamotors.test',     'Marisol Peñaranda'),
  (:u_asesor::uuid,    'asesor@deltamotors.test',    'Gustavo Alcántara'),
  (:u_tecnico::uuid,   'tecnico@deltamotors.test',   'Reinaldo Chirinos'),
  (:u_repuestos::uuid, 'repuestos@deltamotors.test', 'Yelitza Bermúdez')
) as u(id, email, nombre);

insert into auth.identities (
  id, user_id, provider_id, identity_data, provider,
  last_sign_in_at, created_at, updated_at
)
select
  gen_random_uuid(), u.id, u.id::text,
  jsonb_build_object('sub', u.id::text, 'email', u.email, 'email_verified', true),
  'email', now(), now(), now()
from auth.users u
where u.email like '%@deltamotors.test';

insert into public.perfiles (id, taller_id, nombre_completo, telefono, rol) values
  (:u_admin,     :taller_id, 'Marisol Peñaranda',  '+58 414 555 0101', 'admin_taller'),
  (:u_asesor,    :taller_id, 'Gustavo Alcántara',  '+58 414 555 0102', 'asesor_servicio'),
  (:u_tecnico,   :taller_id, 'Reinaldo Chirinos',  '+58 414 555 0103', 'tecnico'),
  (:u_repuestos, :taller_id, 'Yelitza Bermúdez',   '+58 414 555 0104', 'encargado_repuestos');

-- -----------------------------------------------------------------------------
-- Clientes y vehículos
-- -----------------------------------------------------------------------------

insert into public.clientes (id, taller_id, tipo, nombre, documento, telefono, email, direccion) values
  ('c1000000-0000-4000-8000-000000000001', :taller_id, 'persona', 'Andrés Villamizar',   'V-12345678',  '+58 412 555 0201', 'andres.villamizar@correo.test', 'Urb. El Marqués, Caracas'),
  ('c1000000-0000-4000-8000-000000000002', :taller_id, 'persona', 'Carmen Odreman',      'V-9876543',   '+58 424 555 0202', 'carmen.odreman@correo.test',    'La Urbina, Caracas'),
  ('c1000000-0000-4000-8000-000000000003', :taller_id, 'empresa', 'Distribuidora Sanabria C.A.', 'J-30987654-1', '+58 212 555 0203', 'flota@sanabria.test',  'Zona Industrial La Yaguara'),
  ('c1000000-0000-4000-8000-000000000004', :taller_id, 'persona', 'Luis Betancourt',     'V-15558899',  '+58 416 555 0204', 'luis.betancourt@correo.test',   'Santa Mónica, Caracas'),
  ('c1000000-0000-4000-8000-000000000005', :taller_id, 'persona', 'Neida Colmenares',    'V-8877665',   '+58 414 555 0205', null,                             'El Cafetal, Caracas');

insert into public.vehiculos (id, taller_id, cliente_id, placa, vin, marca, modelo, anio, color, tipo_combustible, transmision, kilometraje_ultimo) values
  ('d1000000-0000-4000-8000-000000000001', :taller_id, 'c1000000-0000-4000-8000-000000000001', 'AB123CD', '9BWZZZ377VT004251', 'Toyota',     'Corolla',   2018, 'Plata',  'Gasolina', 'Automática', 87400),
  ('d1000000-0000-4000-8000-000000000002', :taller_id, 'c1000000-0000-4000-8000-000000000002', 'XY456ZW', '1HGCM82633A004352', 'Chevrolet',  'Aveo',      2014, 'Rojo',   'Gasolina', 'Manual',     142800),
  ('d1000000-0000-4000-8000-000000000003', :taller_id, 'c1000000-0000-4000-8000-000000000003', 'FL001AA', 'JN1AZ4EH8DM430120', 'Ford',       'Cargo 815', 2019, 'Blanco', 'Diésel',   'Manual',     215600),
  ('d1000000-0000-4000-8000-000000000004', :taller_id, 'c1000000-0000-4000-8000-000000000003', 'FL002AA', 'JN1AZ4EH8DM430121', 'Ford',       'Cargo 815', 2019, 'Blanco', 'Diésel',   'Manual',     198300),
  ('d1000000-0000-4000-8000-000000000005', :taller_id, 'c1000000-0000-4000-8000-000000000004', 'MN789OP', 'KMHDU46D48U402931', 'Hyundai',    'Elantra',   2016, 'Negro',  'Gasolina', 'Automática', 96500),
  ('d1000000-0000-4000-8000-000000000006', :taller_id, 'c1000000-0000-4000-8000-000000000005', 'QR321ST', 'JTDBT923771050398', 'Toyota',     'Yaris',     2012, 'Azul',   'Gasolina', 'Manual',     176900),
  ('d1000000-0000-4000-8000-000000000007', :taller_id, 'c1000000-0000-4000-8000-000000000001', 'UV654WX', '3N1CN7AP4FL872234', 'Nissan',     'Versa',     2020, 'Gris',   'Gasolina', 'Automática', 41200),
  ('d1000000-0000-4000-8000-000000000008', :taller_id, 'c1000000-0000-4000-8000-000000000002', 'GH987IJ', 'WVWZZZ1JZ3W123456', 'Volkswagen', 'Gol',       2015, 'Blanco', 'Gasolina', 'Manual',     124700);

-- -----------------------------------------------------------------------------
-- Catálogo de repuestos
-- -----------------------------------------------------------------------------

insert into public.repuestos (taller_id, sku, nombre, descripcion, categoria, unidad, costo, precio_venta, stock, stock_minimo, proveedor) values
  (:taller_id, 'FRE-PAS-001', 'Juego de pastillas de freno delanteras', 'Cerámicas, compatibles con sedanes compactos', 'Frenos',       'juego',  22.00,  38.00, 14, 4,  'Repuestos Andina'),
  (:taller_id, 'FRE-DIS-002', 'Disco de freno ventilado 256mm',         null,                                          'Frenos',       'unidad', 31.50,  52.00,  8, 2,  'Repuestos Andina'),
  (:taller_id, 'MOT-ACE-010', 'Aceite sintético 5W-30',                 'Envase de 4 litros',                          'Lubricantes',  'envase', 24.00,  39.00, 26, 8,  'Lubricentro Miranda'),
  (:taller_id, 'MOT-FIL-011', 'Filtro de aceite',                       null,                                          'Lubricantes',  'unidad',  4.20,   9.50, 40, 12, 'Lubricentro Miranda'),
  (:taller_id, 'MOT-FIL-012', 'Filtro de aire de motor',                null,                                          'Motor',        'unidad',  6.80,  14.00, 22, 6,  'Lubricentro Miranda'),
  (:taller_id, 'SUS-AMO-020', 'Amortiguador delantero',                 'Bitubo, presión de gas',                      'Suspensión',   'unidad', 48.00,  79.00,  6, 2,  'Suspensiones del Este'),
  (:taller_id, 'SUS-ROT-021', 'Rótula de suspensión inferior',          null,                                          'Suspensión',   'unidad', 17.50,  31.00, 10, 4,  'Suspensiones del Este'),
  (:taller_id, 'ELE-BAT-030', 'Batería 12V 65Ah',                       'Libre de mantenimiento',                      'Eléctrico',    'unidad', 62.00,  98.00,  5, 2,  'Baterías Centro'),
  (:taller_id, 'ELE-BUJ-031', 'Bujía de iridio',                        null,                                          'Eléctrico',    'unidad',  8.90,  16.50, 32, 8,  'Baterías Centro'),
  (:taller_id, 'ENF-TER-040', 'Termostato de refrigeración',            null,                                          'Enfriamiento', 'unidad', 11.00,  22.00,  9, 3,  'Repuestos Andina');

-- -----------------------------------------------------------------------------
-- Plantilla de control de calidad
-- -----------------------------------------------------------------------------

insert into public.checklist_plantillas (id, taller_id, nombre, descripcion) values
  ('e1000000-0000-4000-8000-000000000001', :taller_id, 'Revisión previa a entrega',
   'Puntos que se verifican en todo vehículo antes de devolverlo al cliente.');

insert into public.checklist_plantilla_items (taller_id, plantilla_id, categoria, descripcion, obligatorio, orden_visual) values
  (:taller_id, 'e1000000-0000-4000-8000-000000000001', 'Seguridad',  'La falla reportada por el cliente ya no se reproduce', true,  1),
  (:taller_id, 'e1000000-0000-4000-8000-000000000001', 'Seguridad',  'No hay testigos encendidos en el tablero',            true,  2),
  (:taller_id, 'e1000000-0000-4000-8000-000000000001', 'Seguridad',  'Prueba de ruta sin ruidos ni vibraciones anómalas',   true,  3),
  (:taller_id, 'e1000000-0000-4000-8000-000000000001', 'Mecánica',   'Niveles de fluidos completos',                        true,  4),
  (:taller_id, 'e1000000-0000-4000-8000-000000000001', 'Mecánica',   'Torque de tuercas de rueda verificado',               true,  5),
  (:taller_id, 'e1000000-0000-4000-8000-000000000001', 'Mecánica',   'Sin fugas visibles en el área intervenida',           true,  6),
  (:taller_id, 'e1000000-0000-4000-8000-000000000001', 'Entrega',    'Interior limpio y sin herramientas olvidadas',        true,  7),
  (:taller_id, 'e1000000-0000-4000-8000-000000000001', 'Entrega',    'Repuestos sustituidos disponibles para el cliente',   false, 8),
  (:taller_id, 'e1000000-0000-4000-8000-000000000001', 'Entrega',    'Presión de neumáticos ajustada',                      false, 9);

-- -----------------------------------------------------------------------------
-- Órdenes de servicio
--
-- Cada bloque avanza la orden por transiciones legales. Un salto inválido haría
-- fallar el seed, que es justo lo que se quiere: si alguien rompe la máquina de
-- estados, `supabase db reset` lo delata.
-- -----------------------------------------------------------------------------

insert into public.ordenes_servicio (
  id, taller_id, cliente_id, vehiculo_id, asesor_id, tecnico_id,
  motivo_ingreso, kilometraje_ingreso, nivel_combustible, fecha_ingreso, fecha_promesa, creado_por
) values
  ('f1000000-0000-4000-8000-000000000001', :taller_id, 'c1000000-0000-4000-8000-000000000001', 'd1000000-0000-4000-8000-000000000001', :u_asesor, null,
   'Chillido metálico al frenar en bajada', 87400, 45, now() - interval '2 hours', now() + interval '2 days', :u_asesor),
  ('f1000000-0000-4000-8000-000000000002', :taller_id, 'c1000000-0000-4000-8000-000000000005', 'd1000000-0000-4000-8000-000000000006', :u_asesor, null,
   'Mantenimiento de 180.000 km', 176900, 70, now() - interval '5 hours', now() + interval '1 day', :u_asesor),
  ('f1000000-0000-4000-8000-000000000003', :taller_id, 'c1000000-0000-4000-8000-000000000002', 'd1000000-0000-4000-8000-000000000002', :u_asesor, :u_tecnico,
   'Se recalienta en tráfico lento', 142800, 30, now() - interval '1 day', now() + interval '2 days', :u_asesor),
  ('f1000000-0000-4000-8000-000000000004', :taller_id, 'c1000000-0000-4000-8000-000000000004', 'd1000000-0000-4000-8000-000000000005', :u_asesor, :u_tecnico,
   'Golpeteo en suspensión delantera sobre irregularidades', 96500, 55, now() - interval '2 days', now() + interval '3 days', :u_asesor),
  ('f1000000-0000-4000-8000-000000000005', :taller_id, 'c1000000-0000-4000-8000-000000000003', 'd1000000-0000-4000-8000-000000000003', :u_asesor, :u_tecnico,
   'Servicio preventivo de flota, unidad 01', 215600, 80, now() - interval '3 days', now() + interval '1 day', :u_asesor),
  ('f1000000-0000-4000-8000-000000000006', :taller_id, 'c1000000-0000-4000-8000-000000000001', 'd1000000-0000-4000-8000-000000000007', :u_asesor, :u_tecnico,
   'No enciende en frío', 41200, 25, now() - interval '4 days', now() - interval '1 day', :u_asesor),
  ('f1000000-0000-4000-8000-000000000007', :taller_id, 'c1000000-0000-4000-8000-000000000002', 'd1000000-0000-4000-8000-000000000008', :u_asesor, :u_tecnico,
   'Cambio de aceite y revisión general', 124700, 60, now() - interval '12 days', now() - interval '10 days', :u_asesor),
  ('f1000000-0000-4000-8000-000000000008', :taller_id, 'c1000000-0000-4000-8000-000000000003', 'd1000000-0000-4000-8000-000000000004', :u_asesor, :u_tecnico,
   'Frenos de flota, unidad 02', 198300, 40, now() - interval '20 days', now() - interval '17 days', :u_asesor),
  ('f1000000-0000-4000-8000-000000000009', :taller_id, 'c1000000-0000-4000-8000-000000000004', 'd1000000-0000-4000-8000-000000000005', :u_asesor, null,
   'Revisión de aire acondicionado', 96900, 50, now() - interval '6 days', null, :u_asesor);

-- Orden 3 · en diagnóstico
update public.ordenes_servicio set estado = 'en_diagnostico'
  where id = 'f1000000-0000-4000-8000-000000000003';

insert into public.diagnosticos (id, taller_id, orden_id, tecnico_id, resumen, horas_estimadas) values
  ('11000000-0000-4000-8000-000000000003', :taller_id, 'f1000000-0000-4000-8000-000000000003', :u_tecnico,
   'Termostato trabado en posición cerrada. Radiador con obstrucción parcial.', 3.5);

insert into public.diagnostico_hallazgos (taller_id, diagnostico_id, sistema, descripcion, severidad, requiere_repuesto, orden_visual) values
  (:taller_id, '11000000-0000-4000-8000-000000000003', 'Enfriamiento', 'Termostato no abre a temperatura de operación', 'critica',  true,  1),
  (:taller_id, '11000000-0000-4000-8000-000000000003', 'Enfriamiento', 'Panal del radiador obstruido por suciedad',      'moderada', false, 2);

-- Orden 4 · presupuesto pendiente de aprobación
update public.ordenes_servicio set estado = 'en_diagnostico'
  where id = 'f1000000-0000-4000-8000-000000000004';

insert into public.diagnosticos (id, taller_id, orden_id, tecnico_id, resumen, horas_estimadas) values
  ('11000000-0000-4000-8000-000000000004', :taller_id, 'f1000000-0000-4000-8000-000000000004', :u_tecnico,
   'Amortiguadores delanteros vencidos y rótula inferior derecha con juego.', 4.0);

insert into public.diagnostico_hallazgos (taller_id, diagnostico_id, sistema, descripcion, severidad, requiere_repuesto, orden_visual) values
  (:taller_id, '11000000-0000-4000-8000-000000000004', 'Suspensión', 'Amortiguadores delanteros sin capacidad de amortiguación', 'moderada', true, 1),
  (:taller_id, '11000000-0000-4000-8000-000000000004', 'Suspensión', 'Rótula inferior derecha con juego perceptible',            'critica',  true, 2);

insert into public.orden_mano_obra (taller_id, orden_id, descripcion, horas, tarifa_hora, tecnico_id) values
  (:taller_id, 'f1000000-0000-4000-8000-000000000004', 'Sustitución de amortiguadores delanteros', 2.5, 18.00, :u_tecnico),
  (:taller_id, 'f1000000-0000-4000-8000-000000000004', 'Sustitución de rótula inferior y alineación', 1.5, 18.00, :u_tecnico);

insert into public.orden_repuestos (taller_id, orden_id, repuesto_id, descripcion, cantidad, precio_unitario, estado, solicitado_por)
select :taller_id, 'f1000000-0000-4000-8000-000000000004', r.id, r.nombre, v.cantidad, r.precio_venta, 'cotizado', :u_tecnico
from (values ('SUS-AMO-020', 2::numeric), ('SUS-ROT-021', 1::numeric)) as v(sku, cantidad)
join public.repuestos r on r.taller_id = :taller_id and r.sku = v.sku;

update public.ordenes_servicio set estado = 'presupuesto_pendiente'
  where id = 'f1000000-0000-4000-8000-000000000004';

insert into public.presupuestos (id, taller_id, orden_id, subtotal_mano_obra, subtotal_repuestos, creado_por)
select '21000000-0000-4000-8000-000000000004', :taller_id, o.id, o.total_mano_obra, o.total_repuestos, :u_asesor
from public.ordenes_servicio o where o.id = 'f1000000-0000-4000-8000-000000000004';

insert into public.presupuesto_items (taller_id, presupuesto_id, tipo, descripcion, cantidad, precio_unitario, orden_visual)
select :taller_id, '21000000-0000-4000-8000-000000000004', 'mano_obra', m.descripcion, m.horas, m.tarifa_hora, row_number() over (order by m.creado_en)
from public.orden_mano_obra m where m.orden_id = 'f1000000-0000-4000-8000-000000000004';

insert into public.presupuesto_items (taller_id, presupuesto_id, tipo, descripcion, cantidad, precio_unitario, orden_visual)
select :taller_id, '21000000-0000-4000-8000-000000000004', 'repuesto', p.descripcion, p.cantidad, p.precio_unitario, 10 + row_number() over (order by p.creado_en)
from public.orden_repuestos p where p.orden_id = 'f1000000-0000-4000-8000-000000000004';

update public.presupuestos set estado = 'enviado'
  where id = '21000000-0000-4000-8000-000000000004';

-- Orden 5 · aprobada, esperando entrar a taller
update public.ordenes_servicio set estado = 'en_diagnostico'        where id = 'f1000000-0000-4000-8000-000000000005';
update public.ordenes_servicio set estado = 'presupuesto_pendiente' where id = 'f1000000-0000-4000-8000-000000000005';

insert into public.orden_mano_obra (taller_id, orden_id, descripcion, horas, tarifa_hora, tecnico_id) values
  (:taller_id, 'f1000000-0000-4000-8000-000000000005', 'Servicio preventivo completo de flota', 3.0, 18.00, :u_tecnico);

insert into public.orden_repuestos (taller_id, orden_id, repuesto_id, descripcion, cantidad, precio_unitario, estado, solicitado_por)
select :taller_id, 'f1000000-0000-4000-8000-000000000005', r.id, r.nombre, v.cantidad, r.precio_venta, 'aprobado', :u_repuestos
from (values ('MOT-ACE-010', 2::numeric), ('MOT-FIL-011', 1::numeric), ('MOT-FIL-012', 1::numeric)) as v(sku, cantidad)
join public.repuestos r on r.taller_id = :taller_id and r.sku = v.sku;

insert into public.presupuestos (id, taller_id, orden_id, subtotal_mano_obra, subtotal_repuestos, creado_por)
select '21000000-0000-4000-8000-000000000005', :taller_id, o.id, o.total_mano_obra, o.total_repuestos, :u_asesor
from public.ordenes_servicio o where o.id = 'f1000000-0000-4000-8000-000000000005';

update public.presupuestos set estado = 'enviado'  where id = '21000000-0000-4000-8000-000000000005';
update public.presupuestos set estado = 'aprobado', comentario_cliente = 'Conforme, proceder.'
  where id = '21000000-0000-4000-8000-000000000005';
update public.ordenes_servicio set estado = 'aprobado' where id = 'f1000000-0000-4000-8000-000000000005';

-- Orden 6 · en reparación
update public.ordenes_servicio set estado = 'en_diagnostico'        where id = 'f1000000-0000-4000-8000-000000000006';
update public.ordenes_servicio set estado = 'presupuesto_pendiente' where id = 'f1000000-0000-4000-8000-000000000006';
update public.ordenes_servicio set estado = 'aprobado'              where id = 'f1000000-0000-4000-8000-000000000006';
update public.ordenes_servicio set estado = 'en_reparacion'         where id = 'f1000000-0000-4000-8000-000000000006';

insert into public.orden_mano_obra (taller_id, orden_id, descripcion, horas, tarifa_hora, tecnico_id) values
  (:taller_id, 'f1000000-0000-4000-8000-000000000006', 'Diagnóstico eléctrico y sustitución de batería', 1.5, 18.00, :u_tecnico);

insert into public.orden_repuestos (taller_id, orden_id, repuesto_id, descripcion, cantidad, precio_unitario, estado, solicitado_por)
select :taller_id, 'f1000000-0000-4000-8000-000000000006', r.id, r.nombre, 1, r.precio_venta, 'instalado', :u_tecnico
from public.repuestos r where r.taller_id = :taller_id and r.sku = 'ELE-BAT-030';

-- Orden 7 · lista para entregar, con control de calidad aprobado
update public.ordenes_servicio set estado = 'en_diagnostico'        where id = 'f1000000-0000-4000-8000-000000000007';
update public.ordenes_servicio set estado = 'presupuesto_pendiente' where id = 'f1000000-0000-4000-8000-000000000007';
update public.ordenes_servicio set estado = 'aprobado'              where id = 'f1000000-0000-4000-8000-000000000007';
update public.ordenes_servicio set estado = 'en_reparacion'         where id = 'f1000000-0000-4000-8000-000000000007';

insert into public.orden_mano_obra (taller_id, orden_id, descripcion, horas, tarifa_hora, tecnico_id) values
  (:taller_id, 'f1000000-0000-4000-8000-000000000007', 'Cambio de aceite y filtros', 1.0, 18.00, :u_tecnico);

insert into public.orden_repuestos (taller_id, orden_id, repuesto_id, descripcion, cantidad, precio_unitario, estado, solicitado_por)
select :taller_id, 'f1000000-0000-4000-8000-000000000007', r.id, r.nombre, 1, r.precio_venta, 'instalado', :u_repuestos
from (values ('MOT-ACE-010'), ('MOT-FIL-011')) as v(sku)
join public.repuestos r on r.taller_id = :taller_id and r.sku = v.sku;

update public.ordenes_servicio set estado = 'control_calidad' where id = 'f1000000-0000-4000-8000-000000000007';

insert into public.controles_calidad (id, taller_id, orden_id, plantilla_id, inspector_id) values
  ('31000000-0000-4000-8000-000000000007', :taller_id, 'f1000000-0000-4000-8000-000000000007',
   'e1000000-0000-4000-8000-000000000001', :u_tecnico);

insert into public.control_calidad_respuestas (taller_id, control_id, item_id, descripcion, resultado, orden_visual)
select :taller_id, '31000000-0000-4000-8000-000000000007', i.id, i.descripcion, 'ok', i.orden_visual
from public.checklist_plantilla_items i
where i.plantilla_id = 'e1000000-0000-4000-8000-000000000001';

update public.controles_calidad set resultado = 'aprobado', observaciones = 'Sin observaciones.'
  where id = '31000000-0000-4000-8000-000000000007';

update public.ordenes_servicio set estado = 'listo_para_entrega' where id = 'f1000000-0000-4000-8000-000000000007';

-- Orden 8 · entregada, con encuesta respondida
update public.ordenes_servicio set estado = 'en_diagnostico'        where id = 'f1000000-0000-4000-8000-000000000008';
update public.ordenes_servicio set estado = 'presupuesto_pendiente' where id = 'f1000000-0000-4000-8000-000000000008';
update public.ordenes_servicio set estado = 'aprobado'              where id = 'f1000000-0000-4000-8000-000000000008';
update public.ordenes_servicio set estado = 'en_reparacion'         where id = 'f1000000-0000-4000-8000-000000000008';

insert into public.orden_mano_obra (taller_id, orden_id, descripcion, horas, tarifa_hora, tecnico_id) values
  (:taller_id, 'f1000000-0000-4000-8000-000000000008', 'Rectificado de discos y cambio de pastillas', 2.0, 18.00, :u_tecnico);

insert into public.orden_repuestos (taller_id, orden_id, repuesto_id, descripcion, cantidad, precio_unitario, estado, solicitado_por)
select :taller_id, 'f1000000-0000-4000-8000-000000000008', r.id, r.nombre, v.cantidad, r.precio_venta, 'instalado', :u_repuestos
from (values ('FRE-PAS-001', 1::numeric), ('FRE-DIS-002', 2::numeric)) as v(sku, cantidad)
join public.repuestos r on r.taller_id = :taller_id and r.sku = v.sku;

update public.ordenes_servicio set estado = 'control_calidad'    where id = 'f1000000-0000-4000-8000-000000000008';
update public.ordenes_servicio set estado = 'listo_para_entrega' where id = 'f1000000-0000-4000-8000-000000000008';
update public.ordenes_servicio set estado = 'entregado'          where id = 'f1000000-0000-4000-8000-000000000008';

insert into public.encuestas (taller_id, orden_id, enviada_en, puntaje_atencion, puntaje_tiempo, puntaje_calidad, recomendaria, comentario)
values (:taller_id, 'f1000000-0000-4000-8000-000000000008', now() - interval '16 days',
        5, 4, 5, 9, 'Entregaron cuando dijeron y explicaron bien el trabajo.');

-- Orden 9 · cancelada
update public.ordenes_servicio
   set estado = 'cancelado',
       motivo_cancelacion = 'El cliente decidió atenderlo con el concesionario por garantía.'
 where id = 'f1000000-0000-4000-8000-000000000009';

-- -----------------------------------------------------------------------------
-- Fechas realistas en la bitácora
--
-- Los eventos se escribieron todos con now(). Se reparten a lo largo de la vida
-- real de cada orden para que las métricas de tiempo del dashboard tengan algo
-- coherente que mostrar desde el primer arranque.
-- -----------------------------------------------------------------------------

update public.ordenes_servicio
   set fecha_entrega = fecha_ingreso + interval '3 days'
 where estado = 'entregado';

with numerados as (
  select e.id,
         e.orden_id,
         row_number() over (partition by e.orden_id order by e.creado_en, e.id) as pos,
         count(*)    over (partition by e.orden_id) as total
    from public.orden_eventos e
)
update public.orden_eventos e
   set creado_en = o.fecha_ingreso
                 + (coalesce(o.fecha_entrega, now()) - o.fecha_ingreso)
                   * (n.pos - 1) / greatest(n.total - 1, 1)
  from numerados n
  join public.ordenes_servicio o on o.id = n.orden_id
 where e.id = n.id;

-- -----------------------------------------------------------------------------
-- Resumen
-- -----------------------------------------------------------------------------

do $$
declare
  v_ordenes int;
  v_eventos int;
begin
  select count(*) into v_ordenes from public.ordenes_servicio;
  select count(*) into v_eventos from public.orden_eventos;
  raise notice 'Mechanified · seed listo: taller Delta Motors, % ordenes, % eventos de bitacora.',
    v_ordenes, v_eventos;
end;
$$;
