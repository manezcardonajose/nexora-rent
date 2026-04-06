from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
import random

from models import (
    db,
    Propiedad,
    Habitacion,
    Reserva,
    ReservaHabitacion,
    Ingreso,
    BloqueoPropiedad,
    Huesped,
    Tarea,
)
from licencias_utils import puede_usar_modulo
from utils import generar_tareas_limpieza

simulador_bp = Blueprint('simulador', __name__, url_prefix='/simulador')


NOMBRES = [
    'Carlos', 'Marta', 'Lucía', 'Javier', 'Ana', 'Pablo', 'Sofía', 'Diego',
    'Laura', 'David', 'Elena', 'Miguel', 'Carmen', 'Raúl', 'Paula', 'Irene'
]
APELLIDOS = [
    'García', 'Martínez', 'López', 'Sánchez', 'Pérez', 'Gómez', 'Ruiz', 'Díaz',
    'Hernández', 'Moreno', 'Muñoz', 'Álvarez', 'Romero', 'Navarro', 'Torres', 'Vargas'
]
NACIONALIDADES = ['España', 'Francia', 'Italia', 'Alemania', 'Portugal', 'Reino Unido']
CIUDADES = ['Madrid', 'Barcelona', 'Valencia', 'Sevilla', 'Bilbao', 'Málaga']
PAISES = ['España', 'Francia', 'Italia', 'Alemania', 'Portugal']


DEMO_PROPIEDAD_NOMBRE = 'Demo Nexora Rent - Villa Atlántico'


def _ids_propiedades_usuario():
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    return [p.id for p in propiedades]



def _propiedades_usuario():
    return (
        Propiedad.query
        .filter_by(usuario_id=current_user.id)
        .order_by(Propiedad.nombre.asc())
        .all()
    )



def _reservas_solapadas_propiedad(propiedad_id, inicio, fin):
    return Reserva.query.filter(
        Reserva.propiedad_id == propiedad_id,
        Reserva.estado != 'cancelada',
        Reserva.fecha_entrada < fin,
        Reserva.fecha_salida > inicio,
    ).all()



def _bloqueos_solapados(propiedad_id, inicio, fin, habitacion_id=None):
    q = BloqueoPropiedad.query.filter(
        BloqueoPropiedad.propiedad_id == propiedad_id,
        BloqueoPropiedad.activo.is_(True),
        BloqueoPropiedad.fecha_inicio < fin,
        BloqueoPropiedad.fecha_fin > inicio,
    )
    if habitacion_id is None:
        return q.all()
    return q.filter(
        db.or_(
            BloqueoPropiedad.habitacion_id.is_(None),
            BloqueoPropiedad.habitacion_id == habitacion_id,
        )
    ).all()



def hay_conflicto_completa(propiedad, inicio, fin):
    if _bloqueos_solapados(propiedad.id, inicio, fin, habitacion_id=None):
        return True

    reservas = _reservas_solapadas_propiedad(propiedad.id, inicio, fin)
    return len(reservas) > 0



def hay_conflicto_habitacion(propiedad, habitacion, inicio, fin):
    if _bloqueos_solapados(propiedad.id, inicio, fin, habitacion_id=habitacion.id):
        return True

    reservas = _reservas_solapadas_propiedad(propiedad.id, inicio, fin)
    for reserva in reservas:
        asignadas = [rh.habitacion_id for rh in reserva.habitaciones_asignadas.all()]

        if not asignadas:
            return True

        if habitacion.id in asignadas:
            return True

    return False



def obtener_resumen_simulacion():
    ids_propiedades = _ids_propiedades_usuario()

    if not ids_propiedades:
        return {
            'total_reservas_demo': 0,
            'total_ingresos_demo': 0.0,
            'total_completas_demo': 0,
            'total_habitaciones_demo': 0,
            'total_tareas_demo': 0,
            'total_huespedes_demo': 0,
        }

    reservas_demo = Reserva.query.filter(
        Reserva.propiedad_id.in_(ids_propiedades),
        Reserva.origen == 'simulador'
    ).all()

    total_ingresos_demo = (
        db.session.query(db.func.sum(Ingreso.cantidad))
        .join(Reserva, Ingreso.reserva_id == Reserva.id)
        .filter(
            Reserva.propiedad_id.in_(ids_propiedades),
            Reserva.origen == 'simulador'
        )
        .scalar()
    ) or 0

    total_completas_demo = 0
    total_habitaciones_demo = 0
    reserva_ids_demo = [r.id for r in reservas_demo]

    if reserva_ids_demo:
        total_tareas_demo = Tarea.query.filter(Tarea.reserva_id.in_(reserva_ids_demo)).count()
        total_huespedes_demo = Huesped.query.filter(Huesped.reserva_id.in_(reserva_ids_demo)).count()
    else:
        total_tareas_demo = 0
        total_huespedes_demo = 0

    for r in reservas_demo:
        if r.habitaciones_asignadas.count() == 1:
            total_habitaciones_demo += 1
        else:
            total_completas_demo += 1

    return {
        'total_reservas_demo': len(reservas_demo),
        'total_ingresos_demo': round(float(total_ingresos_demo or 0), 2),
        'total_completas_demo': total_completas_demo,
        'total_habitaciones_demo': total_habitaciones_demo,
        'total_tareas_demo': total_tareas_demo,
        'total_huespedes_demo': total_huespedes_demo,
    }



def _valor_bool_form(nombre):
    return request.form.get(nombre) in ('1', 'true', 'on', 'yes')


def _crear_propiedad_demo_base():
    existente = Propiedad.query.filter_by(usuario_id=current_user.id, nombre=DEMO_PROPIEDAD_NOMBRE).first()
    if existente:
        return existente, False

    propiedad = Propiedad(
        usuario_id=current_user.id,
        nombre=DEMO_PROPIEDAD_NOMBRE,
        descripcion='Propiedad demo creada automáticamente para mostrar la ERP en funcionamiento.',
        direccion='Calle Demo 12',
        ciudad='San Bartolomé',
        municipio='San Bartolomé',
        codigo_postal='35550',
        pais='España',
        referencia_catastral='DEMO-ATLANTICO-001',
        tipo_inmueble='villa',
        num_habitaciones=3,
        num_banos=2,
        capacidad_max=6,
        precio_noche=145.0,
        moneda='EUR',
        activa=True,
        tipo_impuesto='IVA',
        porcentaje_impuesto=7.0,
        gastos_individuales_texto='Luz, agua y limpieza extraordinaria.',
        suministros_incluidos_texto='Wifi, ropa de cama y amenities.',
        caracteristicas_tecnicas_texto='Piscina, wifi, smart TV y cerradura electrónica.',
        contacto_administracion_texto='Contacto demo Nexora Rent',
        concepto_transferencia='Reserva demo',
    )
    db.session.add(propiedad)
    db.session.flush()

    habitaciones = [
        {'nombre': 'Suite Atlántico', 'tipo': 'suite', 'capacidad': 2, 'camas': '1 cama doble', 'precio_base': 70.0, 'orden': 1},
        {'nombre': 'Habitación Volcán', 'tipo': 'doble', 'capacidad': 2, 'camas': '2 camas individuales', 'precio_base': 45.0, 'orden': 2},
        {'nombre': 'Habitación Jardín', 'tipo': 'doble', 'capacidad': 2, 'camas': '1 cama doble', 'precio_base': 30.0, 'orden': 3},
    ]

    for data in habitaciones:
        db.session.add(Habitacion(propiedad_id=propiedad.id, activa=True, tiene_bano_suite=(data['tipo'] == 'suite'), **data))

    db.session.commit()
    return propiedad, True



def _calcular_importe_pagado(tipo_pago, total):
    total = float(total or 0)
    if total <= 0:
        return 0.0

    if tipo_pago == 'completo':
        return total
    if tipo_pago == 'parcial':
        return round(total * 0.5, 2)
    if tipo_pago == 'pendiente':
        return 0.0

    opcion = random.choice(['completo', 'parcial', 'pendiente'])
    if opcion == 'completo':
        return total
    if opcion == 'parcial':
        return round(total * random.uniform(0.3, 0.7), 2)
    return 0.0



def _crear_huespedes_simulados(reserva):
    total_huespedes = max(1, int(reserva.num_huespedes or 1))
    apellido_principal = random.choice(APELLIDOS)

    for i in range(total_huespedes):
        nombre = random.choice(NOMBRES)
        apellidos = f"{apellido_principal} {random.choice(APELLIDOS)}"
        sexo = random.choice(['M', 'F'])
        anio = random.randint(1965, 2004)
        mes = random.randint(1, 12)
        dia = random.randint(1, 28)
        fecha_nacimiento = date(anio, mes, dia)
        nacionalidad = random.choice(NACIONALIDADES)
        tipo_documento = random.choice(['DNI', 'PASAPORTE'])
        numero_documento = f"SIM{reserva.id}{i}{random.randint(10000, 99999)}"
        numero_soporte = f"SUP{random.randint(100000, 999999)}"
        ciudad = random.choice(CIUDADES)
        pais = random.choice(PAISES)

        huesped = Huesped(
            reserva_id=reserva.id,
            nombre=nombre,
            apellidos=apellidos,
            sexo=sexo,
            fecha_nacimiento=fecha_nacimiento,
            nacionalidad=nacionalidad,
            tipo_documento=tipo_documento,
            numero_documento=numero_documento,
            numero_soporte=numero_soporte,
            domicilio=f"Calle Simulada {random.randint(1, 200)}",
            ciudad=ciudad,
            codigo_postal=f"{random.randint(10000, 52999)}",
            pais=pais,
            telefono=f"6{random.randint(10000000, 99999999)}",
            email=f"simulador{reserva.id}_{i}@nexora.local",
        )
        db.session.add(huesped)



def _crear_reserva_completa(propiedad, fecha_inicio, fecha_fin, canal, estado_reserva):
    habitaciones_activas = propiedad.habitaciones.filter_by(activa=True).order_by(Habitacion.orden.asc(), Habitacion.id.asc()).all()
    noches = (fecha_fin - fecha_inicio).days

    if noches <= 0:
        return None, 'fechas'

    if not propiedad.precio_noche or propiedad.precio_noche <= 0:
        return None, 'sin_precio_propiedad'

    if hay_conflicto_completa(propiedad, fecha_inicio, fecha_fin):
        return None, 'conflicto'

    reserva = Reserva(
        propiedad_id=propiedad.id,
        num_huespedes=max(1, min(propiedad.capacidad_max or 1, random.randint(1, max(propiedad.capacidad_max or 1, 1)))),
        fecha_entrada=fecha_inicio,
        fecha_salida=fecha_fin,
        estado=estado_reserva,
        notas='[SIMULADOR] Reserva de vivienda completa',
        origen='simulador',
        external_id=f"SIM-{propiedad.id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{random.randint(1000,9999)}",
    )
    db.session.add(reserva)
    db.session.flush()

    if habitaciones_activas:
        suma_bases = sum(float(h.precio_base or 0) for h in habitaciones_activas)

        if suma_bases > 0:
            importes = []
            acumulado = 0.0
            for idx, hab in enumerate(habitaciones_activas, start=1):
                if idx < len(habitaciones_activas):
                    precio_aplicado = round((propiedad.precio_noche * float(hab.precio_base or 0)) / suma_bases, 2)
                    acumulado += precio_aplicado
                else:
                    precio_aplicado = round(float(propiedad.precio_noche) - acumulado, 2)
                importes.append((hab, max(precio_aplicado, 0)))
        else:
            precio_unitario = round(float(propiedad.precio_noche) / len(habitaciones_activas), 2)
            importes = []
            acumulado = 0.0
            for idx, hab in enumerate(habitaciones_activas, start=1):
                if idx < len(habitaciones_activas):
                    precio_aplicado = precio_unitario
                    acumulado += precio_aplicado
                else:
                    precio_aplicado = round(float(propiedad.precio_noche) - acumulado, 2)
                importes.append((hab, max(precio_aplicado, 0)))

        for hab, precio_aplicado in importes:
            db.session.add(ReservaHabitacion(
                reserva_id=reserva.id,
                habitacion_id=hab.id,
                precio_aplicado=precio_aplicado,
            ))
    else:
        reserva.subtotal_habitaciones = round(float(propiedad.precio_noche) * noches, 2)
        reserva.total_impuestos = round(reserva.subtotal_habitaciones * ((propiedad.porcentaje_impuesto or 0) / 100), 2)
        if propiedad.aplicar_retencion:
            reserva.retencion_total = round(reserva.subtotal_habitaciones * ((propiedad.porcentaje_retencion or 0) / 100), 2)
        else:
            reserva.retencion_total = 0.0
        reserva.precio_total = round(reserva.subtotal_habitaciones + reserva.total_impuestos - reserva.retencion_total, 2)
        reserva.saldo_pendiente = reserva.precio_total
        return reserva, None

    reserva.calcular_totales()
    return reserva, None



def _crear_reserva_habitacion(propiedad, fecha_inicio, fecha_fin, canal, estado_reserva):
    habitaciones_activas = propiedad.habitaciones.filter_by(activa=True).order_by(Habitacion.orden.asc(), Habitacion.id.asc()).all()
    noches = (fecha_fin - fecha_inicio).days

    if noches <= 0:
        return None, 'fechas'

    if not habitaciones_activas:
        return None, 'sin_habitaciones'

    candidatas = habitaciones_activas[:]
    random.shuffle(candidatas)

    habitacion = None
    for hab in candidatas:
        if not hab.precio_base or hab.precio_base <= 0:
            continue
        if not hay_conflicto_habitacion(propiedad, hab, fecha_inicio, fecha_fin):
            habitacion = hab
            break

    if not habitacion:
        return None, 'conflicto'

    reserva = Reserva(
        propiedad_id=propiedad.id,
        num_huespedes=max(1, min(habitacion.capacidad or 1, random.randint(1, max(habitacion.capacidad or 1, 1)))),
        fecha_entrada=fecha_inicio,
        fecha_salida=fecha_fin,
        estado=estado_reserva,
        notas=f'[SIMULADOR] Reserva por habitación: {habitacion.nombre}',
        origen='simulador',
        external_id=f"SIM-{propiedad.id}-{habitacion.id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{random.randint(1000,9999)}",
    )
    db.session.add(reserva)
    db.session.flush()

    db.session.add(ReservaHabitacion(
        reserva_id=reserva.id,
        habitacion_id=habitacion.id,
        precio_aplicado=float(habitacion.precio_base),
    ))

    reserva.calcular_totales()
    return reserva, None


@simulador_bp.route('/crear-demo-base', methods=['POST'])
@login_required
def crear_demo_base():
    if not puede_usar_modulo(current_user, 'simulador'):
        flash('Tu plan no permite usar el simulador.', 'warning')
        return redirect(url_for('main.dashboard'))

    try:
        propiedad, creada = _crear_propiedad_demo_base()
        if creada:
            flash(f'Se ha creado la propiedad demo “{propiedad.nombre}” con habitaciones base.', 'success')
        else:
            flash('La propiedad demo base ya existía. Puedes usarla para generar reservas y enseñar la ERP.', 'info')
    except Exception:
        db.session.rollback()
        flash('No se pudo crear la propiedad demo base.', 'danger')

    return redirect(url_for('simulador.index'))


@simulador_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if not puede_usar_modulo(current_user, 'simulador'):
        flash('Tu plan no permite usar el simulador.', 'warning')
        return redirect(url_for('main.dashboard'))

    propiedades = _propiedades_usuario()
    canales_disponibles = ['airbnb', 'booking', 'directo', 'vrbo']

    if request.method == 'POST':
        usar_todas = _valor_bool_form('usar_todas')
        propiedad_id_raw = (request.form.get('propiedad_id') or '').strip()
        cantidad_raw = (request.form.get('cantidad') or '').strip()
        dias_hacia_adelante_raw = (request.form.get('dias_hacia_adelante') or '').strip()
        noches_min_raw = (request.form.get('noches_min') or '').strip()
        noches_max_raw = (request.form.get('noches_max') or '').strip()
        modo_reserva = (request.form.get('modo_reserva') or 'mixto').strip()
        tipo_pago = (request.form.get('tipo_pago') or 'aleatorio').strip()
        porcentaje_canceladas_raw = (request.form.get('porcentaje_canceladas') or '0').strip()
        generar_ingresos = _valor_bool_form('generar_ingresos')
        canales = request.form.getlist('canales')

        if not canales:
            canales = canales_disponibles[:]

        try:
            cantidad = int(cantidad_raw)
            dias_hacia_adelante = int(dias_hacia_adelante_raw)
            noches_min = int(noches_min_raw)
            noches_max = int(noches_max_raw)
            porcentaje_canceladas = int(porcentaje_canceladas_raw or 0)
        except (TypeError, ValueError):
            flash('Alguno de los datos numéricos no es válido.', 'danger')
            return redirect(url_for('simulador.index'))

        if cantidad <= 0:
            flash('La cantidad de reservas debe ser mayor que 0.', 'danger')
            return redirect(url_for('simulador.index'))

        if dias_hacia_adelante <= 0:
            flash('Los días hacia adelante deben ser mayores que 0.', 'danger')
            return redirect(url_for('simulador.index'))

        if noches_min <= 0 or noches_max <= 0 or noches_min > noches_max:
            flash('El rango de noches no es válido.', 'danger')
            return redirect(url_for('simulador.index'))

        if porcentaje_canceladas < 0 or porcentaje_canceladas > 100:
            flash('El porcentaje de canceladas debe estar entre 0 y 100.', 'danger')
            return redirect(url_for('simulador.index'))

        if modo_reserva not in ('completa', 'habitacion', 'mixto'):
            flash('El modo de simulación no es válido.', 'danger')
            return redirect(url_for('simulador.index'))

        if tipo_pago not in ('aleatorio', 'completo', 'parcial', 'pendiente'):
            flash('El tipo de pago no es válido.', 'danger')
            return redirect(url_for('simulador.index'))

        if usar_todas:
            propiedades_objetivo = propiedades[:]
        else:
            if not propiedad_id_raw:
                flash('Debes seleccionar una propiedad o marcar usar todas.', 'danger')
                return redirect(url_for('simulador.index'))
            try:
                propiedad_id = int(propiedad_id_raw)
            except (TypeError, ValueError):
                flash('La propiedad seleccionada no es válida.', 'danger')
                return redirect(url_for('simulador.index'))

            propiedad = Propiedad.query.filter_by(id=propiedad_id, usuario_id=current_user.id).first()
            if not propiedad:
                flash('La propiedad seleccionada no es válida.', 'danger')
                return redirect(url_for('simulador.index'))
            propiedades_objetivo = [propiedad]

        if not propiedades_objetivo:
            flash('No hay propiedades disponibles para simular.', 'warning')
            return redirect(url_for('simulador.index'))

        creadas = 0
        canceladas = 0
        conflictos = 0
        sin_precio = 0
        sin_habitaciones = 0
        errores = 0
        tareas_generadas = 0
        huespedes_generados = 0

        hoy = date.today()
        intentos_maximos = max(cantidad * 12, 30)
        intentos = 0

        while creadas < cantidad and intentos < intentos_maximos:
            intentos += 1
            propiedad = random.choice(propiedades_objetivo)
            canal = random.choice(canales)
            noches = random.randint(noches_min, noches_max)
            offset = random.randint(0, max(dias_hacia_adelante - 1, 0))
            fecha_inicio = hoy + timedelta(days=offset)
            fecha_fin = fecha_inicio + timedelta(days=noches)

            if modo_reserva == 'mixto':
                tiene_habitaciones = propiedad.habitaciones.filter_by(activa=True).count() > 0
                tipo_reserva = random.choice(['completa', 'habitacion']) if tiene_habitaciones else 'completa'
            else:
                tipo_reserva = modo_reserva

            estado_reserva = 'cancelada' if random.randint(1, 100) <= porcentaje_canceladas else 'confirmada'

            try:
                if tipo_reserva == 'completa':
                    reserva, motivo = _crear_reserva_completa(propiedad, fecha_inicio, fecha_fin, canal, estado_reserva)
                else:
                    reserva, motivo = _crear_reserva_habitacion(propiedad, fecha_inicio, fecha_fin, canal, estado_reserva)

                if not reserva:
                    if motivo == 'conflicto':
                        conflictos += 1
                    elif motivo == 'sin_precio_propiedad':
                        sin_precio += 1
                    elif motivo == 'sin_habitaciones':
                        sin_habitaciones += 1
                    else:
                        errores += 1
                    db.session.rollback()
                    continue

                reserva.notas = (reserva.notas or '') + f' | Canal={canal} | Modo={tipo_reserva}'

                pagado = 0.0
                if estado_reserva != 'cancelada':
                    pagado = _calcular_importe_pagado(tipo_pago, reserva.precio_total or 0)

                reserva.deposito_pagado = round(pagado, 2)
                reserva.saldo_pendiente = round(float(reserva.precio_total or 0) - float(reserva.deposito_pagado or 0), 2)
                if reserva.saldo_pendiente < 0:
                    reserva.saldo_pendiente = 0.0
                if reserva.deposito_pagado >= float(reserva.precio_total or 0) and float(reserva.precio_total or 0) > 0:
                    reserva.fecha_pago_total = hoy

                _crear_huespedes_simulados(reserva)
                huespedes_generados += max(1, int(reserva.num_huespedes or 1))

                db.session.flush()

                if generar_ingresos and pagado > 0 and estado_reserva != 'cancelada':
                    ingreso = Ingreso(
                        propiedad_id=propiedad.id,
                        reserva_id=reserva.id,
                        fecha=hoy,
                        concepto=f'Ingreso simulado reserva {reserva.id}',
                        cantidad=pagado,
                        moneda=propiedad.moneda or 'EUR',
                        metodo_pago='simulado',
                        observaciones=f'[SIMULADOR] Canal={canal} Pago={tipo_pago} Modo={tipo_reserva}'
                    )
                    db.session.add(ingreso)

                db.session.commit()

                try:
                    generar_tareas_limpieza(reserva.id)
                    tareas_generadas += 1
                except Exception:
                    db.session.rollback()
                    db.session.commit()

                creadas += 1
                if estado_reserva == 'cancelada':
                    canceladas += 1

            except Exception:
                db.session.rollback()
                errores += 1
                continue

        if creadas == 0:
            flash(
                'No se pudieron crear reservas. Revisa conflictos, precios de propiedad/habitación o disponibilidad.',
                'warning'
            )
        else:
            flash(
                f'Simulación generada: {creadas} reservas ({canceladas} canceladas). '
                f'Conflictos evitados: {conflictos}. '
                f'Propiedades sin precio: {sin_precio}. '
                f'Casos sin habitaciones válidas: {sin_habitaciones}. '
                f'Huéspedes creados: {huespedes_generados}. '
                f'Tareas lanzadas: {tareas_generadas}.',
                'success'
            )

        return redirect(url_for('simulador.index'))

    resumen = obtener_resumen_simulacion()

    return render_template(
        'simulador/index.html',
        propiedades=propiedades,
        resumen=resumen,
        canales=canales_disponibles,
    )


@simulador_bp.route('/limpiar', methods=['POST'])
@login_required
def limpiar():
    ids_propiedades = _ids_propiedades_usuario()

    if not ids_propiedades:
        flash('No hay simulaciones para limpiar.', 'info')
        return redirect(url_for('simulador.index'))

    reservas = Reserva.query.filter(
        Reserva.propiedad_id.in_(ids_propiedades),
        Reserva.origen == 'simulador'
    ).all()

    if not reservas:
        flash('No hay reservas simuladas para limpiar.', 'info')
        return redirect(url_for('simulador.index'))

    reserva_ids = [r.id for r in reservas]

    try:
        Tarea.query.filter(Tarea.reserva_id.in_(reserva_ids)).delete(synchronize_session=False)
        Ingreso.query.filter(Ingreso.reserva_id.in_(reserva_ids)).delete(synchronize_session=False)
        Huesped.query.filter(Huesped.reserva_id.in_(reserva_ids)).delete(synchronize_session=False)
        ReservaHabitacion.query.filter(ReservaHabitacion.reserva_id.in_(reserva_ids)).delete(synchronize_session=False)
        Reserva.query.filter(Reserva.id.in_(reserva_ids)).delete(synchronize_session=False)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('No se pudo limpiar la simulación completa.', 'danger')
        return redirect(url_for('simulador.index'))

    flash('Simulación eliminada correctamente, incluyendo tareas automáticas.', 'success')
    return redirect(url_for('simulador.index'))
