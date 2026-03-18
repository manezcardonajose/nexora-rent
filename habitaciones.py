from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, Habitacion, Propiedad
from forms import HabitacionForm

habitaciones_bp = Blueprint('habitaciones', __name__, url_prefix='/habitaciones')

@habitaciones_bp.route('/<int:propiedad_id>')
@login_required
def index(propiedad_id):
    """Listado de habitaciones de una propiedad"""
    propiedad = Propiedad.query.get_or_404(propiedad_id)
    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('propiedades.index'))
    
    habitaciones = Habitacion.query.filter_by(propiedad_id=propiedad_id).order_by(Habitacion.orden).all()
    return render_template('habitaciones/index.html', habitaciones=habitaciones, propiedad=propiedad)

@habitaciones_bp.route('/nueva/<int:propiedad_id>', methods=['GET', 'POST'])
@login_required
def nueva(propiedad_id):
    """Crear una nueva habitación"""
    propiedad = Propiedad.query.get_or_404(propiedad_id)
    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('propiedades.index'))
    
    form = HabitacionForm()
    if form.validate_on_submit():
        habitacion = Habitacion(
            propiedad_id=propiedad_id,
            nombre=form.nombre.data,
            tipo=form.tipo.data,
            capacidad=form.capacidad.data,
            tiene_bano_suite=form.tiene_bano_suite.data,
            camas=form.camas.data,
            precio_base=form.precio_base.data,
            activa=form.activa.data,
            orden=form.orden.data,
            observaciones=form.observaciones.data
        )
        db.session.add(habitacion)
        db.session.commit()
        flash('Habitación creada correctamente', 'success')
        return redirect(url_for('habitaciones.index', propiedad_id=propiedad_id))
    
    return render_template('habitaciones/nueva.html', form=form, propiedad=propiedad)

# 🔴 RUTA DE EDICIÓN - LA QUE FALTA
@habitaciones_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Editar una habitación existente"""
    habitacion = Habitacion.query.get_or_404(id)
    propiedad = Propiedad.query.get(habitacion.propiedad_id)
    
    # Verificar permisos
    if propiedad.usuario_id != current_user.id:
        flash('No tienes permiso para editar esta habitación', 'danger')
        return redirect(url_for('propiedades.index'))
    
    form = HabitacionForm(obj=habitacion)
    if form.validate_on_submit():
        form.populate_obj(habitacion)
        db.session.commit()
        flash('Habitación actualizada correctamente', 'success')
        return redirect(url_for('habitaciones.index', propiedad_id=habitacion.propiedad_id))
    
    return render_template('habitaciones/editar.html', form=form, habitacion=habitacion)

# 🔴 RUTA DE ELIMINACIÓN
@habitaciones_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    """Eliminar una habitación"""
    habitacion = Habitacion.query.get_or_404(id)
    propiedad = Propiedad.query.get(habitacion.propiedad_id)
    propiedad_id = habitacion.propiedad_id
    
    # Verificar permisos
    if propiedad.usuario_id != current_user.id:
        flash('No tienes permiso para eliminar esta habitación', 'danger')
        return redirect(url_for('propiedades.index'))
    
    db.session.delete(habitacion)
    db.session.commit()
    flash('Habitación eliminada correctamente', 'success')
    return redirect(url_for('habitaciones.index', propiedad_id=propiedad_id))

# 🔴 RUTA PARA VER DETALLE DE UNA HABITACIÓN (opcional)
@habitaciones_bp.route('/ver/<int:id>')
@login_required
def ver(id):
    """Ver detalle de una habitación"""
    habitacion = Habitacion.query.get_or_404(id)
    propiedad = Propiedad.query.get(habitacion.propiedad_id)
    
    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('propiedades.index'))
    
    return render_template('habitaciones/ver.html', habitacion=habitacion, propiedad=propiedad)