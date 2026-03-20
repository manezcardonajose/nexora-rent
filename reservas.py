from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from models import db, Reserva, Propiedad, Habitacion, ReservaHabitacion
from forms import ReservaForm
from utils import check_disponibilidad_habitaciones, generar_tareas_limpieza, generar_pdf_reserva
from datetime import datetime
from io import BytesIO

# 🔴 PRIMERO: Crear el blueprint
reservas_bp = Blueprint('reservas', __name__, url_prefix='/reservas')

# 🔴 DESPUÉS: Definir las rutas
@reservas_bp.route('/')
@login_required
def index():
    """Listado de reservas"""
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    propiedad_ids = [p.id for p in propiedades]
    reservas = Reserva.query.filter(Reserva.propiedad_id.in_(propiedad_ids)).order_by(Reserva.fecha_entrada.desc()).all()
    return render_template('reservas/index.html', reservas=reservas)

@reservas_bp.route('/nueva', methods=['GET', 'POST'])
@login_required
def nueva():
    """Crear nueva reserva"""
    form = ReservaForm()
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    form.propiedad_id.choices = [(0, '-- Selecciona una propiedad --')] + [(p.id, p.nombre) for p in propiedades]
    
    if form.validate_on_submit():
        # Validaciones
        if form.propiedad_id.data == 0:
            flash('Debes seleccionar una propiedad', 'danger')
            return render_template('reservas/nueva.html', form=form)
        
        habitaciones_ids = request.form.getlist('habitaciones')
        if not habitaciones_ids:
            flash('Debes seleccionar al menos una habitación', 'danger')
            return render_template('reservas/nueva.html', form=form)
        
        # Verificar disponibilidad
        disponible, conflictivas = check_disponibilidad_habitaciones(
            form.propiedad_id.data,
            form.fecha_entrada.data,
            form.fecha_salida.data,
            [int(id) for id in habitaciones_ids],
            None
        )
        
        if not disponible:
            habitaciones_conflictivas = Habitacion.query.filter(Habitacion.id.in_(conflictivas)).all()
            nombres = ", ".join([h.nombre for h in habitaciones_conflictivas])
            flash(f'Las siguientes habitaciones no están disponibles: {nombres}', 'danger')
            return render_template('reservas/nueva.html', form=form)
        
        # Crear reserva
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
        
        # Asignar habitaciones
        noches = (form.fecha_salida.data - form.fecha_entrada.data).days
        subtotal = 0
        
        for hab_id in habitaciones_ids:
            habitacion = Habitacion.query.get(int(hab_id))
            if habitacion and habitacion.activa:
                rh = ReservaHabitacion(
                    reserva_id=reserva.id,
                    habitacion_id=int(hab_id),
                    precio_aplicado=habitacion.precio_base
                )
                db.session.add(rh)
                subtotal += habitacion.precio_base * noches
        
        reserva.subtotal_habitaciones = subtotal
        reserva.calcular_totales()
        db.session.commit()
        
        generar_tareas_limpieza(reserva.id)
        
        flash('Reserva creada correctamente', 'success')
        return redirect(url_for('reservas.index'))
    
    return render_template('reservas/nueva.html', form=form)

@reservas_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Editar una reserva existente"""
    reserva = Reserva.query.get_or_404(id)
    propiedad = Propiedad.query.get(reserva.propiedad_id)
    
    if propiedad.usuario_id != current_user.id:
        flash('No tienes permiso', 'danger')
        return redirect(url_for('reservas.index'))
    
    form = ReservaForm(obj=reserva)
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    form.propiedad_id.choices = [(0, '-- Selecciona --')] + [(p.id, p.nombre) for p in propiedades]
    
    habitaciones_asignadas = [rh.habitacion_id for rh in reserva.habitaciones_asignadas]
    
    if form.validate_on_submit():
        habitaciones_ids_str = request.form.getlist('habitaciones')
        nuevas_habitaciones = [int(id) for id in habitaciones_ids_str] if habitaciones_ids_str else []
        
        if not nuevas_habitaciones:
            flash('Debes seleccionar al menos una habitación', 'danger')
            return render_template('reservas/editar.html', form=form, reserva=reserva, habitaciones_asignadas=habitaciones_asignadas)
        
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
            flash(f'Habitaciones no disponibles: {nombres}', 'danger')
            return render_template('reservas/editar.html', form=form, reserva=reserva, habitaciones_asignadas=habitaciones_asignadas)
        
        # Actualizar campos
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
        
        # Actualizar habitaciones
        ReservaHabitacion.query.filter_by(reserva_id=reserva.id).delete()
        
        noches = (form.fecha_salida.data - form.fecha_entrada.data).days
        subtotal = 0
        
        for hab_id in nuevas_habitaciones:
            habitacion = Habitacion.query.get(hab_id)
            if habitacion:
                rh = ReservaHabitacion(
                    reserva_id=reserva.id,
                    habitacion_id=hab_id,
                    precio_aplicado=habitacion.precio_base
                )
                db.session.add(rh)
                subtotal += habitacion.precio_base * noches
        
        reserva.subtotal_habitaciones = subtotal
        reserva.calcular_totales()
        db.session.commit()
        
        flash('Reserva actualizada', 'success')
        return redirect(url_for('reservas.index'))
    
    return render_template('reservas/editar.html', form=form, reserva=reserva, habitaciones_asignadas=habitaciones_asignadas)

@reservas_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    """Eliminar una reserva"""
    reserva = Reserva.query.get_or_404(id)
    propiedad = Propiedad.query.get(reserva.propiedad_id)
    
    if propiedad.usuario_id != current_user.id:
        flash('No tienes permiso', 'danger')
        return redirect(url_for('reservas.index'))
    
    db.session.delete(reserva)
    db.session.commit()
    flash('Reserva eliminada', 'success')
    return redirect(url_for('reservas.index'))

@reservas_bp.route('/<int:id>')
@login_required
def ver(id):
    """Ver detalle de reserva"""
    reserva = Reserva.query.get_or_404(id)
    propiedad = Propiedad.query.get(reserva.propiedad_id)
    
    if propiedad.usuario_id != current_user.id:
        flash('No tienes permiso', 'danger')
        return redirect(url_for('reservas.index'))
    
    noches = (reserva.fecha_salida - reserva.fecha_entrada).days
    return render_template('reservas/ver.html', reserva=reserva, noches=noches)

@reservas_bp.route('/pdf/<int:id>')
@login_required
def pdf_reserva(id):
    """Generar PDF"""
    reserva = Reserva.query.get_or_404(id)
    propiedad = Propiedad.query.get(reserva.propiedad_id)
    
    if propiedad.usuario_id != current_user.id:
        flash('No tienes permiso', 'danger')
        return redirect(url_for('reservas.index'))
    
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
    
    reserva = Reserva.query.get_or_404(id)
    propiedad = Propiedad.query.get(reserva.propiedad_id)
    
    if propiedad.usuario_id != current_user.id:
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
    """Generar PDF con el registro de viajeros (SES.Hospedajes)"""
    import pdfkit
    from io import BytesIO
    from datetime import datetime
    
    reserva = Reserva.query.get_or_404(id)
    propiedad = Propiedad.query.get(reserva.propiedad_id)
    
    if propiedad.usuario_id != current_user.id:
        flash('No tienes permiso', 'danger')
        return redirect(url_for('reservas.ver', id=id))
    
    # Renderizar HTML para el PDF
    html = render_template(
        'documentos/registro_viajeros.html',
        reserva=reserva,
        now=datetime.now,
        current_user=current_user
    )
    
    # Configurar pdfkit
    options = {
        'page-size': 'A4',
        'margin-top': '0.75in',
        'margin-right': '0.75in',
        'margin-bottom': '0.75in',
        'margin-left': '0.75in',
        'encoding': "UTF-8",
        'enable-local-file-access': None
    }
    
    # Ruta a wkhtmltopdf (ajusta según tu instalación)
    path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
    config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
    
    try:
        pdf = pdfkit.from_string(html, False, options=options, configuration=config)
        buffer = BytesIO(pdf)
        buffer.seek(0)
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"registro_viajeros_{reserva.id}.pdf",
            mimetype='application/pdf'
        )
    except Exception as e:
        print(f"Error generando PDF: {e}")
        flash('Error al generar el PDF. Intenta más tarde.', 'danger')
        return redirect(url_for('reservas.ver', id=id))

@reservas_bp.route('/enviar-email/<int:id>', methods=['POST'])
@login_required
def enviar_email(id):
    """Enviar PDF de la reserva por email"""
    from flask_mail import Message
    from app import mail
    
    reserva = Reserva.query.get_or_404(id)
    propiedad = Propiedad.query.get(reserva.propiedad_id)
    
    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('reservas.ver', id=id))
    
    primer_huesped = reserva.huespedes.first()
    if not primer_huesped or not primer_huesped.email:
        flash('El huésped no tiene email registrado', 'warning')
        return redirect(url_for('reservas.ver', id=id))
    
    # Generar PDF
    pdf = generar_pdf_reserva(id)
    if not pdf:
        flash('Error al generar el PDF', 'danger')
        return redirect(url_for('reservas.ver', id=id))
    
    msg = Message(
        subject=f"Confirmación de reserva #{reserva.id}",
        recipients=[primer_huesped.email],
        body=f"""Hola {primer_huesped.nombre},
        
Adjuntamos la confirmación de tu reserva en {reserva.propiedad.nombre}.

Fechas: {reserva.fecha_entrada} al {reserva.fecha_salida}
Total: {reserva.precio_total}€

¡Gracias por confiar en nosotros!

--
Gestor de Alquiler Vacacional"""
    )
    
    msg.attach(f"reserva_{reserva.id}.pdf", "application/pdf", pdf)
    
    try:
        mail.send(msg)
        flash(f'PDF enviado correctamente a {primer_huesped.email}', 'success')
    except Exception as e:
        flash(f'Error al enviar email: {e}', 'danger')
    
    return redirect(url_for('reservas.ver', id=id))

