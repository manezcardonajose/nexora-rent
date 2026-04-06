from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from models import db, Reserva, Propiedad, Habitacion, ReservaHabitacion, Contrato
from forms import ReservaForm
from utils import check_disponibilidad_habitaciones, generar_tareas_limpieza, generar_pdf_reserva
from email_config import send_email_for_user
from datetime import datetime
from io import BytesIO
from utils import log_audit
from permisos import propiedades_visibles_query, propiedad_es_visible, usuario_tiene_permiso

reservas_bp = Blueprint('reservas', __name__, url_prefix='/reservas')


def _puede_gestionar_reservas():
    return usuario_tiene_permiso('puede_gestionar_reservas')


def _propiedades_usuario():
    return propiedades_visibles_query().order_by(Propiedad.nombre.asc()).all()


def _propiedad_permitida(propiedad):
    return propiedad is not None and propiedad_es_visible(propiedad)


def _reserva_permitida(reserva):
    if not reserva or not reserva.propiedad:
        return False
    return _propiedad_permitida(reserva.propiedad)


def hay_contrato_solapado(propiedad_id, inicio, fin, contrato_id_excluir=None):
    q = Contrato.query.filter(
        Contrato.propiedad_id == propiedad_id,
        Contrato.estado == 'activo',
        Contrato.fecha_inicio <= fin,
        db.or_(
            Contrato.fecha_fin.is_(None),
            Contrato.fecha_fin >= inicio
        )
    )

    if contrato_id_excluir:
        q = q.filter(Contrato.id != contrato_id_excluir)

    return q.first() is not None


def _habitaciones_propiedad(propiedad_id):
    if not propiedad_id:
        return []

    propiedad = Propiedad.query.get(propiedad_id)
    if not _propiedad_permitida(propiedad):
        return []

    return Habitacion.query.filter_by(
        propiedad_id=propiedad_id,
        activa=True
    ).order_by(Habitacion.nombre.asc()).all()


def habitaciones_disponibles(propiedad_id, fecha_entrada, fecha_salida, reserva_id_excluir=None):
    """
    Devuelve solo habitaciones disponibles para esa propiedad y rango de fechas.
    Si se edita una reserva, se puede excluir su propio id.
    """
    if not propiedad_id or not fecha_entrada or not fecha_salida:
        return []

    habitaciones = _habitaciones_propiedad(propiedad_id)
    disponibles = []

    for h in habitaciones:
        ocupada = False

        for rh in h.reservas:
            r = rh.reserva
            if not r:
                continue

            if reserva_id_excluir and r.id == reserva_id_excluir:
                continue

            if r.estado != 'cancelada':
                if fecha_entrada < r.fecha_salida and fecha_salida > r.fecha_entrada:
                    ocupada = True
                    break

        if not ocupada:
            disponibles.append(h)

    return disponibles


@reservas_bp.route('/')
@login_required
def index():
    """Listado de reservas con filtros y ordenación"""
    if not _puede_gestionar_reservas():
        flash('No tienes permisos para acceder a reservas.', 'danger')
        return redirect(url_for('main.dashboard'))

    propiedades = _propiedades_usuario()
    propiedad_ids = [p.id for p in propiedades]

    filtros = {
        'propiedad_id': request.args.get('propiedad_id', type=int) or 0,
        'estado': (request.args.get('estado') or '').strip(),
        'origen': (request.args.get('origen') or '').strip(),
        'fecha_desde': (request.args.get('fecha_desde') or '').strip(),
        'fecha_hasta': (request.args.get('fecha_hasta') or '').strip(),
        'q': (request.args.get('q') or '').strip(),
        'orden': (request.args.get('orden') or 'entrada_desc').strip(),
    }

    ordenes_disponibles = {
        'entrada_desc': Reserva.fecha_entrada.desc(),
        'entrada_asc': Reserva.fecha_entrada.asc(),
        'salida_desc': Reserva.fecha_salida.desc(),
        'salida_asc': Reserva.fecha_salida.asc(),
        'creacion_desc': Reserva.fecha_creacion.desc(),
        'creacion_asc': Reserva.fecha_creacion.asc(),
        'total_desc': Reserva.precio_total.desc(),
        'total_asc': Reserva.precio_total.asc(),
        'id_desc': Reserva.id.desc(),
        'id_asc': Reserva.id.asc(),
    }
    if filtros['orden'] not in ordenes_disponibles:
        filtros['orden'] = 'entrada_desc'

    estados_disponibles = ['pendiente', 'confirmada', 'cancelada']
    origenes_disponibles = []
    reservas = []

    if propiedad_ids:
        query_origenes = db.session.query(Reserva.origen).filter(
            Reserva.propiedad_id.in_(propiedad_ids),
            Reserva.origen.isnot(None),
            Reserva.origen != ''
        ).distinct().order_by(Reserva.origen.asc())
        origenes_disponibles = [fila[0] for fila in query_origenes.all() if fila[0]]

        query = Reserva.query.filter(Reserva.propiedad_id.in_(propiedad_ids))

        if filtros['propiedad_id']:
            if filtros['propiedad_id'] in propiedad_ids:
                query = query.filter(Reserva.propiedad_id == filtros['propiedad_id'])
            else:
                flash('La propiedad seleccionada no está disponible para tu usuario.', 'warning')
                return redirect(url_for('reservas.index'))

        if filtros['estado']:
            query = query.filter(Reserva.estado == filtros['estado'])

        if filtros['origen']:
            query = query.filter(Reserva.origen == filtros['origen'])

        if filtros['fecha_desde']:
            try:
                fecha_desde = datetime.strptime(filtros['fecha_desde'], '%Y-%m-%d').date()
                query = query.filter(Reserva.fecha_entrada >= fecha_desde)
            except ValueError:
                flash('La fecha desde no tiene un formato válido.', 'warning')

        if filtros['fecha_hasta']:
            try:
                fecha_hasta = datetime.strptime(filtros['fecha_hasta'], '%Y-%m-%d').date()
                query = query.filter(Reserva.fecha_salida <= fecha_hasta)
            except ValueError:
                flash('La fecha hasta no tiene un formato válido.', 'warning')

        if filtros['q']:
            termino = filtros['q']
            like = f"%{termino}%"
            query = query.join(Propiedad).filter(
                db.or_(
                    Propiedad.nombre.ilike(like),
                    Reserva.origen.ilike(like),
                    Reserva.estado.ilike(like),
                    Reserva.external_id.ilike(like),
                    db.cast(Reserva.id, db.String).ilike(like)
                )
            )

        reservas = query.order_by(ordenes_disponibles[filtros['orden']]).all()

    return render_template(
        'reservas/index.html',
        reservas=reservas,
        propiedades=propiedades,
        filtros=filtros,
        estados_disponibles=estados_disponibles,
        origenes_disponibles=origenes_disponibles,
        total_reservas=len(reservas),
    )


@reservas_bp.route('/nueva', methods=['GET', 'POST'])
@login_required
def nueva():
    """Crear nueva reserva"""
    if not _puede_gestionar_reservas():
        flash('No tienes permisos para crear reservas.', 'danger')
        return redirect(url_for('main.dashboard'))

    form = ReservaForm()
    propiedades = _propiedades_usuario()
    form.propiedad_id.choices = [(0, '-- Selecciona una propiedad --')] + [(p.id, p.nombre) for p in propiedades]

    habitaciones = []

    propiedad_id_request = request.form.get('propiedad_id', type=int) if request.method == 'POST' else request.args.get('propiedad_id', type=int)

    fecha_entrada_request = None
    fecha_salida_request = None

    if request.method == 'POST':
        try:
            if request.form.get('fecha_entrada'):
                fecha_entrada_request = datetime.strptime(request.form.get('fecha_entrada'), '%Y-%m-%d').date()
            if request.form.get('fecha_salida'):
                fecha_salida_request = datetime.strptime(request.form.get('fecha_salida'), '%Y-%m-%d').date()
        except Exception:
            fecha_entrada_request = None
            fecha_salida_request = None

    if propiedad_id_request and fecha_entrada_request and fecha_salida_request:
        propiedad = Propiedad.query.get(propiedad_id_request)
        if _propiedad_permitida(propiedad):
            habitaciones = habitaciones_disponibles(propiedad_id_request, fecha_entrada_request, fecha_salida_request)

    if form.validate_on_submit():
        if not current_user.puede_crear_reserva():
            flash('Has alcanzado el límite de reservas de tu plan.', 'warning')
            return redirect(url_for('reservas.index'))

        if form.propiedad_id.data == 0:
            flash('Debes seleccionar una propiedad', 'danger')
            return render_template('reservas/nueva.html', form=form, habitaciones=habitaciones)

        propiedad = Propiedad.query.get(form.propiedad_id.data)
        if not _propiedad_permitida(propiedad):
            flash('No tienes permiso sobre la propiedad seleccionada.', 'danger')
            return redirect(url_for('reservas.index'))

        if hay_contrato_solapado(form.propiedad_id.data, form.fecha_entrada.data, form.fecha_salida.data):
            flash('La propiedad tiene un contrato de alquiler activo en esas fechas y no puede reservarse en vacacional.', 'danger')
            habitaciones = habitaciones_disponibles(
                form.propiedad_id.data,
                form.fecha_entrada.data,
                form.fecha_salida.data
            )
            return render_template('reservas/nueva.html', form=form, habitaciones=habitaciones)

        habitaciones_ids = request.form.getlist('habitaciones')
        if not habitaciones_ids:
            flash('Debes seleccionar al menos una habitación', 'danger')
            habitaciones = habitaciones_disponibles(
                form.propiedad_id.data,
                form.fecha_entrada.data,
                form.fecha_salida.data
            )
            return render_template('reservas/nueva.html', form=form, habitaciones=habitaciones)

        disponible, conflictivas = check_disponibilidad_habitaciones(
            form.propiedad_id.data,
            form.fecha_entrada.data,
            form.fecha_salida.data,
            [int(hid) for hid in habitaciones_ids],
            None
        )

        if not disponible:
            habitaciones_conflictivas = Habitacion.query.filter(Habitacion.id.in_(conflictivas)).all()
            nombres = ", ".join([h.nombre for h in habitaciones_conflictivas])
            flash(f'Las siguientes habitaciones no están disponibles: {nombres}', 'danger')

            habitaciones = habitaciones_disponibles(
                form.propiedad_id.data,
                form.fecha_entrada.data,
                form.fecha_salida.data
            )
            return render_template('reservas/nueva.html', form=form, habitaciones=habitaciones)

        external_id = form.external_id.data if form.external_id.data else None

        reserva = Reserva(
            propiedad_id=form.propiedad_id.data,
            num_huespedes=form.num_huespedes.data,
            num_menores=form.num_menores.data or 0,
            relacion_parentesco=form.relacion_parentesco.data,
            fecha_entrada=form.fecha_entrada.data,
            fecha_salida=form.fecha_salida.data,
            estado=form.estado.data,
            notas=form.notas.data,
            origen=form.origen.data,
            external_id=external_id,
            deposito_pagado=0,
            subtotal_habitaciones=0,
            precio_total=0,
            saldo_pendiente=0
        )

        db.session.add(reserva)
        db.session.flush()

        noches = (form.fecha_salida.data - form.fecha_entrada.data).days
        subtotal = 0

        for hab_id in habitaciones_ids:
            habitacion = Habitacion.query.get(int(hab_id))
            if habitacion and habitacion.activa and habitacion.propiedad_id == form.propiedad_id.data:
                rh = ReservaHabitacion(
                    reserva_id=reserva.id,
                    habitacion_id=int(hab_id),
                    precio_aplicado=habitacion.precio_base
                )
                db.session.add(rh)
                subtotal += (habitacion.precio_base or 0) * noches

        reserva.subtotal_habitaciones = subtotal
        reserva.calcular_totales()
        db.session.commit()

        log_audit(current_user.id, 'crear', 'reserva', reserva.id, None, {
            'propiedad_id': reserva.propiedad_id,
            'fecha_entrada': str(reserva.fecha_entrada),
            'fecha_salida': str(reserva.fecha_salida),
            'num_huespedes': reserva.num_huespedes
        })

        try:
            generar_tareas_limpieza(reserva.id)
        except Exception:
            pass

        flash('Reserva creada correctamente', 'success')
        return redirect(url_for('huespedes.index', reserva_id=reserva.id))

    return render_template('reservas/nueva.html', form=form, habitaciones=habitaciones)


@reservas_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Editar una reserva existente"""
    if not _puede_gestionar_reservas():
        flash('No tienes permisos para editar reservas.', 'danger')
        return redirect(url_for('main.dashboard'))

    reserva = Reserva.query.get_or_404(id)
    propiedad = Propiedad.query.get(reserva.propiedad_id)

    if not _propiedad_permitida(propiedad):
        flash('No tienes permiso para editar esta reserva', 'danger')
        return redirect(url_for('reservas.index'))

    form = ReservaForm(obj=reserva)

    propiedades = _propiedades_usuario()
    form.propiedad_id.choices = [(0, '-- Selecciona una propiedad --')] + [(p.id, p.nombre) for p in propiedades]

    habitaciones_asignadas = [rh.habitacion_id for rh in reserva.habitaciones_asignadas]

    habitaciones = []
    propiedad_id_actual = request.form.get('propiedad_id', type=int) if request.method == 'POST' else reserva.propiedad_id
    fecha_entrada_actual = form.fecha_entrada.data if form.fecha_entrada.data else reserva.fecha_entrada
    fecha_salida_actual = form.fecha_salida.data if form.fecha_salida.data else reserva.fecha_salida

    propiedad_actual = Propiedad.query.get(propiedad_id_actual) if propiedad_id_actual else None
    if propiedad_actual and _propiedad_permitida(propiedad_actual) and fecha_entrada_actual and fecha_salida_actual:
        habitaciones = habitaciones_disponibles(
            propiedad_id_actual,
            fecha_entrada_actual,
            fecha_salida_actual,
            reserva.id
        )

        habitaciones_ids_disponibles = {h.id for h in habitaciones}
        habitaciones_actuales = Habitacion.query.filter(Habitacion.id.in_(habitaciones_asignadas)).all() if habitaciones_asignadas else []
        for h in habitaciones_actuales:
            if h.id not in habitaciones_ids_disponibles:
                habitaciones.append(h)

        habitaciones.sort(key=lambda x: (x.nombre or '').lower())

    if form.validate_on_submit():
        nueva_propiedad = Propiedad.query.get(form.propiedad_id.data)
        if not _propiedad_permitida(nueva_propiedad):
            flash('No tienes permiso sobre la propiedad seleccionada.', 'danger')
            return redirect(url_for('reservas.index'))

        if hay_contrato_solapado(form.propiedad_id.data, form.fecha_entrada.data, form.fecha_salida.data):
            flash('La propiedad tiene un contrato de alquiler activo en esas fechas y no puede reservarse en vacacional.', 'danger')
            return render_template(
                'reservas/editar.html',
                form=form,
                reserva=reserva,
                habitaciones_asignadas=habitaciones_asignadas,
                habitaciones=habitaciones
            )

        nuevas_habitaciones = [int(hid) for hid in request.form.getlist('habitaciones')] if request.form.getlist('habitaciones') else []

        if not nuevas_habitaciones:
            flash('Debes seleccionar al menos una habitación', 'danger')
            return render_template(
                'reservas/editar.html',
                form=form,
                reserva=reserva,
                habitaciones_asignadas=habitaciones_asignadas,
                habitaciones=habitaciones
            )

        disponible, conflictivas = check_disponibilidad_habitaciones(
            form.propiedad_id.data,
            form.fecha_entrada.data,
            form.fecha_salida.data,
            nuevas_habitaciones,
            reserva.id
        )

        if not disponible:
            habitaciones_conflictivas = Habitacion.query.filter(Habitacion.id.in_(conflictivas)).all()
            nombres = ", ".join([h.nombre for h in habitaciones_conflictivas])
            flash(f'Las siguientes habitaciones no están disponibles: {nombres}', 'danger')
            return render_template(
                'reservas/editar.html',
                form=form,
                reserva=reserva,
                habitaciones_asignadas=habitaciones_asignadas,
                habitaciones=habitaciones
            )

        reserva.propiedad_id = form.propiedad_id.data
        reserva.num_huespedes = form.num_huespedes.data
        reserva.num_menores = form.num_menores.data or 0
        reserva.relacion_parentesco = form.relacion_parentesco.data
        reserva.fecha_entrada = form.fecha_entrada.data
        reserva.fecha_salida = form.fecha_salida.data
        reserva.estado = form.estado.data
        reserva.notas = form.notas.data
        reserva.origen = form.origen.data
        reserva.external_id = form.external_id.data if form.external_id.data else None

        ReservaHabitacion.query.filter_by(reserva_id=reserva.id).delete()

        noches = (form.fecha_salida.data - form.fecha_entrada.data).days
        subtotal = 0

        for hab_id in nuevas_habitaciones:
            habitacion = Habitacion.query.get(hab_id)
            if habitacion and habitacion.propiedad_id == form.propiedad_id.data:
                rh = ReservaHabitacion(
                    reserva_id=reserva.id,
                    habitacion_id=hab_id,
                    precio_aplicado=habitacion.precio_base
                )
                db.session.add(rh)
                subtotal += (habitacion.precio_base or 0) * noches

        reserva.subtotal_habitaciones = subtotal
        reserva.calcular_totales()

        db.session.commit()

        log_audit(current_user.id, 'editar', 'reserva', reserva.id, None, {'estado': reserva.estado})

        flash('Reserva actualizada correctamente', 'success')
        return redirect(url_for('reservas.index'))

    return render_template(
        'reservas/editar.html',
        form=form,
        reserva=reserva,
        habitaciones_asignadas=habitaciones_asignadas,
        habitaciones=habitaciones
    )


@reservas_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    """Eliminar una reserva"""
    if not _puede_gestionar_reservas():
        flash('No tienes permisos para eliminar reservas.', 'danger')
        return redirect(url_for('main.dashboard'))

    reserva = Reserva.query.get_or_404(id)

    if not _reserva_permitida(reserva):
        flash('No tienes permiso', 'danger')
        return redirect(url_for('reservas.index'))

    datos_eliminados = {
        'id': reserva.id,
        'propiedad_id': reserva.propiedad_id,
        'fecha_entrada': str(reserva.fecha_entrada),
        'fecha_salida': str(reserva.fecha_salida)
    }

    db.session.delete(reserva)
    db.session.commit()

    log_audit(current_user.id, 'eliminar', 'reserva', reserva.id, datos_eliminados, None)

    flash('Reserva eliminada', 'success')
    return redirect(url_for('reservas.index'))


@reservas_bp.route('/<int:id>')
@login_required
def ver(id):
    """Ver detalle de reserva"""
    if not _puede_gestionar_reservas():
        flash('No tienes permisos para ver reservas.', 'danger')
        return redirect(url_for('main.dashboard'))

    reserva = Reserva.query.get_or_404(id)

    if not _reserva_permitida(reserva):
        flash('No tienes permiso', 'danger')
        return redirect(url_for('reservas.index'))

    noches = (reserva.fecha_salida - reserva.fecha_entrada).days
    return render_template('reservas/ver.html', reserva=reserva, noches=noches)


@reservas_bp.route('/pdf/<int:id>')
@login_required
def pdf_reserva(id):
    """Generar PDF"""
    if not _puede_gestionar_reservas():
        flash('No tienes permisos para acceder a esta acción.', 'danger')
        return redirect(url_for('main.dashboard'))

    reserva = Reserva.query.get_or_404(id)

    if not _reserva_permitida(reserva):
        flash('No tienes permiso', 'danger')
        return redirect(url_for('reservas.ver', id=id))

    pdf = generar_pdf_reserva(id)
    if not pdf:
        flash('Error al generar PDF', 'danger')
        return redirect(url_for('reservas.ver', id=id))

    buffer = BytesIO(pdf)
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"reserva_{id}.pdf",
        mimetype='application/pdf'
    )


@reservas_bp.route('/whatsapp/<int:id>')
@login_required
def whatsapp_reserva(id):
    """Compartir por WhatsApp"""
    from urllib.parse import quote

    if not _puede_gestionar_reservas():
        flash('No tienes permisos para acceder a esta acción.', 'danger')
        return redirect(url_for('main.dashboard'))

    reserva = Reserva.query.get_or_404(id)

    if not _reserva_permitida(reserva):
        flash('No tienes permiso', 'danger')
        return redirect(url_for('reservas.index'))

    noches = (reserva.fecha_salida - reserva.fecha_entrada).days
    primer_huesped = reserva.huespedes.first()
    nombre = f"{primer_huesped.nombre} {primer_huesped.apellidos}" if primer_huesped else "Cliente"

    texto = f"""🏨 *RESERVA CONFIRMADA*

📍 *Propiedad:* {reserva.propiedad.nombre}
👤 *Huésped:* {nombre}
📅 *Fechas:* {reserva.fecha_entrada} al {reserva.fecha_salida} ({noches} noches)
💰 *Total:* {reserva.precio_total:.2f}€
💳 *Pagado:* {reserva.deposito_pagado:.2f}€
⏳ *Pendiente:* {reserva.saldo_pendiente:.2f}€
📍 *Dirección:* {reserva.propiedad.direccion or ''}
"""

    return redirect(f"https://wa.me/?text={quote(texto)}")


@reservas_bp.route('/registro-viajeros/<int:id>')
@login_required
def registro_viajeros(id):
    """Generar PDF con el registro de viajeros (compatible con Render)"""
    import pdfkit
    import os

    if not _puede_gestionar_reservas():
        flash('No tienes permisos para acceder a esta acción.', 'danger')
        return redirect(url_for('main.dashboard'))

    reserva = Reserva.query.get_or_404(id)

    if not _reserva_permitida(reserva):
        flash('No tienes permiso', 'danger')
        return redirect(url_for('reservas.ver', id=id))

    html = render_template(
        'documentos/registro_viajeros.html',
        reserva=reserva,
        now=datetime.now,
        current_user=current_user
    )

    options = {
        'page-size': 'A4',
        'encoding': "UTF-8",
        'enable-local-file-access': None
    }

    try:
        if os.name == 'nt':
            config = pdfkit.configuration(
                wkhtmltopdf=r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
            )
            pdf = pdfkit.from_string(html, False, options=options, configuration=config)
        else:
            pdf = pdfkit.from_string(html, False, options=options)

        buffer = BytesIO(pdf)
        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"registro_viajeros_{reserva.id}.pdf",
            mimetype='application/pdf'
        )

    except Exception as e:
        print(f"Error PDF: {e}")
        flash('Error al generar PDF. En producción puede requerir configuración adicional.', 'danger')
        return redirect(url_for('reservas.ver', id=id))


@reservas_bp.route('/enviar-email/<int:id>', methods=['POST'])
@login_required
def enviar_email(id):
    """Enviar PDF de la reserva por email"""
    if not _puede_gestionar_reservas():
        flash('No tienes permisos para acceder a esta acción.', 'danger')
        return redirect(url_for('main.dashboard'))

    reserva = Reserva.query.get_or_404(id)

    if not _reserva_permitida(reserva):
        flash('No autorizado', 'danger')
        return redirect(url_for('reservas.ver', id=id))

    primer_huesped = reserva.huespedes.first()
    if not primer_huesped or not primer_huesped.email:
        flash('El huésped no tiene email registrado', 'warning')
        return redirect(url_for('reservas.ver', id=id))

    pdf = generar_pdf_reserva(id)
    if not pdf:
        flash('Error al generar el PDF', 'danger')
        return redirect(url_for('reservas.ver', id=id))

    try:
        send_email_for_user(
            current_user,
            subject=f"Confirmación de reserva #{reserva.id}",
            recipients=[primer_huesped.email],
            body=f"""Hola {primer_huesped.nombre},

Adjuntamos la confirmación de tu reserva en {reserva.propiedad.nombre}.

Fechas: {reserva.fecha_entrada} al {reserva.fecha_salida}
Total: {reserva.precio_total}€

¡Gracias por confiar en nosotros!

--
Gestor de Alquiler Vacacional""",
            attachments=[{
                'filename': f"reserva_{reserva.id}.pdf",
                'mime_type': 'application/pdf',
                'data': pdf
            }]
        )
        flash(f'PDF enviado correctamente a {primer_huesped.email}', 'success')
    except Exception as e:
        flash(f'Error al enviar email: {e}', 'danger')

    return redirect(url_for('reservas.ver', id=id))