from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from models import db, Reserva, Propiedad, Habitacion, ReservaHabitacion
from forms import ReservaForm
from utils import check_disponibilidad_habitaciones, generar_tareas_limpieza, generar_pdf_reserva
from datetime import datetime
from io import BytesIO

# 🔴 PRIMERO: Crear el blueprint
reservas_bp = Blueprint('reservas', __name__, url_prefix='/reservas')

# ============================================
# RUTA: LISTADO DE RESERVAS
# ============================================
@reservas_bp.route('/')
@login_required
def index():
    """Listado de reservas del usuario"""
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    propiedad_ids = [p.id for p in propiedades]
    reservas = Reserva.query.filter(Reserva.propiedad_id.in_(propiedad_ids)).order_by(Reserva.fecha_entrada.desc()).all()
    return render_template('reservas/index.html', reservas=reservas)


# ============================================
# RUTA: NUEVA RESERVA
# ============================================
@reservas_bp.route('/nueva', methods=['GET', 'POST'])
@login_required
def nueva():
    """Crear una nueva reserva (sin datos de huésped, se añadirán después)"""
    form = ReservaForm()
    
    # Cargar propiedades del usuario en el select
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    form.propiedad_id.choices = [(0, '-- Selecciona una propiedad --')] + [(p.id, p.nombre) for p in propiedades]
    
    if form.validate_on_submit():
        # Validar que se seleccionó una propiedad
        if form.propiedad_id.data == 0:
            flash('Debes seleccionar una propiedad', 'danger')
            return render_template('reservas/nueva.html', form=form)
        
        # Obtener habitaciones seleccionadas
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
        
        # Crear reserva SOLO con datos básicos
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
            external_id=form.external_id.data,
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
        
        flash('Reserva creada correctamente. Ahora registra los datos de los huéspedes.', 'success')
        return redirect(url_for('huespedes.index', reserva_id=reserva.id))
    
    return render_template('reservas/nueva.html', form=form)


# ============================================
# RUTA: EDITAR RESERVA
# ============================================
@reservas_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Editar una reserva existente"""
    reserva = Reserva.query.get_or_404(id)  # <-- Obtienes la reserva existente
    propiedad = Propiedad.query.get(reserva.propiedad_id)
    
    # Verificar permisos
    if propiedad.usuario_id != current_user.id:
        flash('No tienes permiso para editar esta reserva', 'danger')
        return redirect(url_for('reservas.index'))
    
    form = ReservaForm(obj=reserva)
    
    # Cargar propiedades en el select
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    form.propiedad_id.choices = [(0, '-- Selecciona una propiedad --')] + [(p.id, p.nombre) for p in propiedades]
    
    # Obtener IDs de habitaciones actualmente asignadas
    habitaciones_asignadas = [rh.habitacion_id for rh in reserva.habitaciones_asignadas]
    
    if form.validate_on_submit():
        # Obtener nuevas habitaciones seleccionadas
        habitaciones_ids_str = request.form.getlist('habitaciones')
        nuevas_habitaciones = [int(id) for id in habitaciones_ids_str] if habitaciones_ids_str else []
        
        if not nuevas_habitaciones:
            flash('Debes seleccionar al menos una habitación', 'danger')
            return render_template('reservas/editar.html', form=form, reserva=reserva, habitaciones_asignadas=habitaciones_asignadas)
        
        # Verificar disponibilidad de las nuevas habitaciones (excluyendo esta reserva)
        disponible, conflictivas = check_disponibilidad_habitaciones(
            form.propiedad_id.data,
            form.fecha_entrada.data,
            form.fecha_salida.data,
            nuevas_habitaciones,
            reserva.id  # Excluir esta reserva
        )
        
        if not disponible:
            habitaciones_conflictivas = Habitacion.query.filter(Habitacion.id.in_(conflictivas)).all()
            nombres = ", ".join([h.nombre for h in habitaciones_conflictivas])
            flash(f'Las siguientes habitaciones no están disponibles: {nombres}', 'danger')
            return render_template('reservas/editar.html', form=form, reserva=reserva, habitaciones_asignadas=habitaciones_asignadas)
        
        # Actualizar campos básicos
        reserva.propiedad_id = form.propiedad_id.data
        reserva.num_huespedes = form.num_huespedes.data
        reserva.num_menores = form.num_menores.data or 0
        reserva.relacion_parentesco = form.relacion_parentesco.data
        reserva.fecha_entrada = form.fecha_entrada.data
        reserva.fecha_salida = form.fecha_salida.data
        reserva.estado = form.estado.data
        reserva.notas = form.notas.data
        reserva.origen = form.origen.data
        
        # Manejar external_id (convertir '' a None)
        if form.external_id.data:
            reserva.external_id = form.external_id.data
        else:
            reserva.external_id = None
        
        # Actualizar habitaciones: eliminar las antiguas y añadir las nuevas
        # Eliminar asignaciones antiguas
        ReservaHabitacion.query.filter_by(reserva_id=reserva.id).delete()
        
        # Añadir nuevas asignaciones
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
        
        # Recalcular totales
        reserva.subtotal_habitaciones = subtotal
        reserva.calcular_totales()
        
        db.session.commit()
        flash('Reserva actualizada correctamente', 'success')
        return redirect(url_for('reservas.index'))
    
    return render_template('reservas/editar.html', 
                          form=form, 
                          reserva=reserva,  # <-- Solo pasas la variable
                          habitaciones_asignadas=habitaciones_asignadas)

# ============================================
# RUTA: ELIMINAR RESERVA
# ============================================
@reservas_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    """Eliminar una reserva"""
    reserva = Reserva.query.get_or_404(id)
    propiedad = Propiedad.query.get(reserva.propiedad_id)
    
    # Verificar permisos
    if propiedad.usuario_id != current_user.id:
        flash('No tienes permiso para eliminar esta reserva', 'danger')
        return redirect(url_for('reservas.index'))
    
    db.session.delete(reserva)
    db.session.commit()
    flash('Reserva eliminada correctamente', 'success')
    return redirect(url_for('reservas.index'))


# ============================================
# RUTA: VER DETALLE DE RESERVA
# ============================================
@reservas_bp.route('/<int:id>')
@login_required
def ver(id):
    """Ver detalle de una reserva"""
    reserva = Reserva.query.get_or_404(id)
    propiedad = Propiedad.query.get(reserva.propiedad_id)
    
    # Verificar permisos
    if propiedad.usuario_id != current_user.id:
        flash('No tienes permiso para ver esta reserva', 'danger')
        return redirect(url_for('reservas.index'))
    
    # Calcular noches
    noches = (reserva.fecha_salida - reserva.fecha_entrada).days
    
    return render_template('reservas/ver.html', reserva=reserva, noches=noches)


# ============================================
# RUTA: GENERAR PDF DE RESERVA
# ============================================
@reservas_bp.route('/pdf/<int:id>')
@login_required
def pdf_reserva(id):
    """Generar PDF de la reserva"""
    import traceback
    from io import BytesIO
    
    try:
        print(f"🟢 [PDF] Ruta pdf_reserva llamada para ID: {id}")
        
        reserva = Reserva.query.get_or_404(id)
        propiedad = Propiedad.query.get(reserva.propiedad_id)
        
        # Verificar permisos
        if propiedad.usuario_id != current_user.id:
            flash('No tienes permiso', 'danger')
            return redirect(url_for('reservas.index'))
        
        print(f"🟢 [PDF] Permisos OK, usuario: {current_user.id}")
        
        pdf = generar_pdf_reserva(id)
        
        if not pdf:
            print(f"🔴 [PDF] generar_pdf_reserva devolvió None")
            flash('⚠️ No se pudo generar el PDF. Revisa la consola para más detalles.', 'warning')
            return redirect(url_for('reservas.ver', id=id))
        
        buffer = BytesIO(pdf)
        buffer.seek(0)
        print(f"🟢 [PDF] Enviando PDF, tamaño: {len(pdf)} bytes")
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"reserva_{id}.pdf",
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"🔴 [PDF] Error en ruta pdf_reserva: {e}")
        print(traceback.format_exc())
        flash('❌ Error inesperado al generar el PDF', 'danger')
        return redirect(url_for('reservas.ver', id=id))
   
# ============================================
# RUTA: ENVIAR POR WHATSAPP
# ============================================
@reservas_bp.route('/whatsapp/<int:id>')
@login_required
def whatsapp_reserva(id):
    """Enviar reserva por WhatsApp con formato enriquecido (versión recuadro)"""
    from urllib.parse import quote
    
    reserva = Reserva.query.get_or_404(id)
    propiedad = Propiedad.query.get(reserva.propiedad_id)
    
    # Verificar permisos
    if propiedad.usuario_id != current_user.id:
        flash('No tienes permiso', 'danger')
        return redirect(url_for('reservas.index'))
    
    noches = (reserva.fecha_salida - reserva.fecha_entrada).days
    
    # Obtener primer huésped
    primer_huesped = reserva.huespedes.first()
    if primer_huesped:
        nombre_huesped = f"{primer_huesped.nombre} {primer_huesped.apellidos}"
    else:
        nombre_huesped = "Cliente"
    
    # 📦 FORMATO CON RECUADRO (VERSIÓN 3)
    texto = f"""╔══════════════════════════╗
║    *RESERVA CONFIRMADA*    ║
╚══════════════════════════╝

🏠 *PROPIEDAD:* {reserva.propiedad.nombre}
👤 *HUÉSPED:* {nombre_huesped}
📅 *FECHAS:* {reserva.fecha_entrada.strftime('%d/%m/%Y')} al {reserva.fecha_salida.strftime('%d/%m/%Y')}
🌙 *NOCHES:* {noches}
💰 *TOTAL:* {reserva.precio_total:.2f}€
💳 *PAGADO:* {reserva.deposito_pagado:.2f}€
⏳ *PENDIENTE:* {reserva.saldo_pendiente:.2f}€

📍 *DIRECCIÓN:* {reserva.propiedad.direccion or 'No especificada'}

─────────────────────────
🔖 *Reserva #{reserva.id}*"""
    
    # Codificar para URL
    texto_codificado = quote(texto)
    
    # Opcional: Si tienes el teléfono del huésped, enviar directamente
    telefono = None
    if primer_huesped and primer_huesped.telefono:
        # Limpiar teléfono (quitar espacios y símbolos)
        telefono = ''.join(filter(str.isdigit, primer_huesped.telefono))
    
    if telefono:
        whatsapp_url = f"https://wa.me/{telefono}?text={texto_codificado}"
    else:
        whatsapp_url = f"https://wa.me/?text={texto_codificado}"
    
    return redirect(whatsapp_url)