from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, Huesped, Reserva, Propiedad
from forms import HuespedForm
from datetime import datetime

huespedes_bp = Blueprint('huespedes', __name__, url_prefix='/huespedes')

@huespedes_bp.route('/reserva/<int:reserva_id>')
@login_required
def index(reserva_id):
    """Listado de huéspedes de una reserva"""
    reserva = Reserva.query.get_or_404(reserva_id)
    propiedad = Propiedad.query.get(reserva.propiedad_id)
    
    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('reservas.index'))
    
    return render_template('huespedes/index.html', reserva=reserva)

@huespedes_bp.route('/nuevo/<int:reserva_id>', methods=['GET', 'POST'])
@login_required
def nuevo(reserva_id):
    """Añadir un nuevo huésped a una reserva"""
    reserva = Reserva.query.get_or_404(reserva_id)
    propiedad = Propiedad.query.get(reserva.propiedad_id)
    
    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('reservas.index'))
    
    # Verificar que no se exceda el número de huéspedes
    if reserva.huespedes.count() >= reserva.num_huespedes:
        flash(f'Ya has registrado el máximo de {reserva.num_huespedes} huéspedes', 'warning')
        return redirect(url_for('huespedes.index', reserva_id=reserva_id))
    
    form = HuespedForm()
    
    # Configurar choices para nacionalidad (misma lista que en reserva)
    form.nacionalidad.choices = [
        ('', '-- Selecciona --'),
        ('ES', 'España'),
        ('FR', 'Francia'),
        ('IT', 'Italia'),
        ('DE', 'Alemania'),
        ('UK', 'Reino Unido'),
        ('US', 'Estados Unidos'),
        ('PT', 'Portugal'),
        ('OTRO', 'Otro')
    ]
    
    if form.validate_on_submit():
        # Si es el primer huésped, usar sus datos como referencia
        if reserva.huespedes.count() == 0:
            # Opcional: actualizar campos de la reserva con los datos del titular
            pass
        
        huesped = Huesped(
            reserva_id=reserva_id,
            nombre=form.nombre.data,
            apellidos=form.apellidos.data,
            sexo=form.sexo.data,
            fecha_nacimiento=form.fecha_nacimiento.data,
            nacionalidad=form.nacionalidad.data,
            tipo_documento=form.tipo_documento.data,
            numero_documento=form.numero_documento.data,
            numero_soporte=form.numero_soporte.data
        )
        
        # Domicilio (si no es el mismo)
        if form.mismo_domicilio.data:
            # Usar datos del primer huésped o dejarlos en blanco
            pass
        else:
            huesped.domicilio = form.domicilio.data
            huesped.ciudad = form.ciudad.data
            huesped.codigo_postal = form.codigo_postal.data
            huesped.pais = form.pais.data
        
        huesped.telefono = form.telefono.data
        huesped.email = form.email.data
        
        db.session.add(huesped)
        db.session.commit()
        
        flash('Huésped añadido correctamente', 'success')
        return redirect(url_for('huespedes.index', reserva_id=reserva_id))
    
    return render_template('huespedes/nuevo.html', form=form, reserva=reserva)

@huespedes_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Editar un huésped existente"""
    huesped = Huesped.query.get_or_404(id)
    reserva = Reserva.query.get(huesped.reserva_id)
    propiedad = Propiedad.query.get(reserva.propiedad_id)
    
    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('reservas.index'))
    
    form = HuespedForm(obj=huesped)
    
    # Configurar choices
    form.nacionalidad.choices = [
        ('', '-- Selecciona --'),
        ('ES', 'España'),
        ('FR', 'Francia'),
        ('IT', 'Italia'),
        ('DE', 'Alemania'),
        ('UK', 'Reino Unido'),
        ('US', 'Estados Unidos'),
        ('PT', 'Portugal'),
        ('OTRO', 'Otro')
    ]
    
    if form.validate_on_submit():
        form.populate_obj(huesped)
        db.session.commit()
        flash('Huésped actualizado correctamente', 'success')
        return redirect(url_for('huespedes.index', reserva_id=reserva.id))
    
    return render_template('huespedes/editar.html', form=form, huesped=huesped, reserva=reserva)

@huespedes_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    """Eliminar un huésped"""
    huesped = Huesped.query.get_or_404(id)
    reserva = Reserva.query.get(huesped.reserva_id)
    propiedad = Propiedad.query.get(reserva.propiedad_id)
    
    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('reservas.index'))
    
    # No permitir eliminar si es el único huésped
    if reserva.huespedes.count() <= 1:
        flash('No puedes eliminar el último huésped. Elimina la reserva si es necesario.', 'danger')
        return redirect(url_for('huespedes.index', reserva_id=reserva.id))
    
    db.session.delete(huesped)
    db.session.commit()
    flash('Huésped eliminado correctamente', 'success')
    return redirect(url_for('huespedes.index', reserva_id=reserva.id))