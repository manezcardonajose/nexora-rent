from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, PagoReserva, Reserva, Ingreso, Propiedad
from forms import PagoReservaForm
from datetime import datetime

pagos_bp = Blueprint('pagos', __name__, url_prefix='/pagos')

@pagos_bp.route('/reserva/<int:reserva_id>')
@login_required
def index(reserva_id):
    """Ver todos los pagos de una reserva"""
    reserva = Reserva.query.get_or_404(reserva_id)
    propiedad = Propiedad.query.get(reserva.propiedad_id)
    
    # Verificar permisos
    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('reservas.index'))
    
    pagos = PagoReserva.query.filter_by(reserva_id=reserva_id).order_by(PagoReserva.fecha_pago.desc()).all()
    total_pagado = sum(p.monto for p in pagos)
    
    return render_template('pagos/index.html', 
                          reserva=reserva, 
                          pagos=pagos, 
                          total_pagado=total_pagado)

@pagos_bp.route('/nuevo/<int:reserva_id>', methods=['GET', 'POST'])
@login_required
def nuevo(reserva_id):
    """Registrar un nuevo pago para una reserva"""
    reserva = Reserva.query.get_or_404(reserva_id)
    propiedad = Propiedad.query.get(reserva.propiedad_id)
    
    # Verificar permisos
    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('reservas.index'))
    
    form = PagoReservaForm()
    
    if form.validate_on_submit():
        # Determinar el concepto final
        if form.concepto.data == 'otro' and form.concepto_personalizado.data:
            concepto_final = form.concepto_personalizado.data
        else:
            concepto_final = dict(form.concepto.choices).get(form.concepto.data)
        
        # Crear el pago
        pago = PagoReserva(
            reserva_id=reserva_id,
            fecha_pago=form.fecha_pago.data,
            monto=form.monto.data,
            metodo_pago=form.metodo_pago.data,
            concepto=concepto_final,
            referencia=form.referencia.data,
            observaciones=form.observaciones.data
        )
        db.session.add(pago)
        
        # Actualizar el saldo de la reserva
        reserva.deposito_pagado += form.monto.data
        reserva.saldo_pendiente = reserva.precio_total - reserva.deposito_pagado
        
        # Si el saldo es 0, marcar como pagado completamente
        if reserva.saldo_pendiente <= 0:
            reserva.fecha_pago_total = datetime.today().date()
        
        # Crear un ingreso asociado (opcional)
        ingreso = Ingreso(
            propiedad_id=reserva.propiedad_id,
            reserva_id=reserva.id,
            fecha=form.fecha_pago.data,
            concepto=f"Pago reserva #{reserva.id} - {concepto_final}",
            cantidad=form.monto.data,
            moneda='EUR',
            metodo_pago=form.metodo_pago.data,
            observaciones=f"Referencia: {form.referencia.data or 'N/A'}"
        )
        db.session.add(ingreso)
        
        # Vincular el pago con el ingreso
        pago.ingreso_id = ingreso.id
        
        db.session.commit()
        
        flash(f'Pago de {form.monto.data}€ registrado correctamente', 'success')
        return redirect(url_for('pagos.index', reserva_id=reserva_id))
    
    return render_template('pagos/nuevo.html', form=form, reserva=reserva)

@pagos_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    """Eliminar un pago (con precaución)"""
    pago = PagoReserva.query.get_or_404(id)
    reserva = pago.reserva
    propiedad = Propiedad.query.get(reserva.propiedad_id)
    
    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('reservas.index'))
    
    # Guardar datos para mensaje
    monto = pago.monto
    reserva_id = reserva.id
    
    # Actualizar saldo de la reserva
    reserva.deposito_pagado -= pago.monto
    reserva.saldo_pendiente = reserva.precio_total - reserva.deposito_pagado
    
    # Si había ingreso asociado, eliminarlo también
    if pago.ingreso_id:
        ingreso = Ingreso.query.get(pago.ingreso_id)
        if ingreso:
            db.session.delete(ingreso)
    
    # Eliminar el pago
    db.session.delete(pago)
    db.session.commit()
    
    flash(f'Pago de {monto}€ eliminado. Nuevo saldo pendiente: {reserva.saldo_pendiente}€', 'warning')
    return redirect(url_for('pagos.index', reserva_id=reserva_id))