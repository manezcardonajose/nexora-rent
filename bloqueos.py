from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, BloqueoPropiedad, Propiedad, Habitacion
from forms import BloqueoForm
from datetime import datetime

bloqueos_bp = Blueprint('bloqueos', __name__, url_prefix='/bloqueos')

@bloqueos_bp.route('/propiedad/<int:propiedad_id>')
@login_required
def index(propiedad_id):
    """Ver bloqueos de una propiedad"""
    propiedad = Propiedad.query.get_or_404(propiedad_id)
    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('propiedades.index'))
    
    bloqueos = BloqueoPropiedad.query.filter_by(propiedad_id=propiedad_id).order_by(BloqueoPropiedad.fecha_inicio.desc()).all()
    return render_template('bloqueos/index.html', propiedad=propiedad, bloqueos=bloqueos)

@bloqueos_bp.route('/nuevo/<int:propiedad_id>', methods=['GET', 'POST'])
@login_required
def nuevo(propiedad_id):
    """Crear un nuevo bloqueo"""
    propiedad = Propiedad.query.get_or_404(propiedad_id)
    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('propiedades.index'))
    
    form = BloqueoForm()
    
    # ✅ NO NECESITAS form.propiedad_id.data = propiedad_id
    
    # Cargar habitaciones de esta propiedad
    habitaciones = Habitacion.query.filter_by(propiedad_id=propiedad_id, activa=True).all()
    form.habitacion_id.choices = [(0, '-- Toda la propiedad --')] + [(h.id, h.nombre) for h in habitaciones]
    
    if form.validate_on_submit():
        bloqueo = BloqueoPropiedad(
            propiedad_id=propiedad_id,  # Usamos el ID de la URL
            habitacion_id=form.habitacion_id.data if form.habitacion_id.data != 0 else None,
            fecha_inicio=form.fecha_inicio.data,
            fecha_fin=form.fecha_fin.data,
            motivo=form.motivo.data,
            descripcion=form.descripcion.data,
            activo=True,
            creado_por_id=current_user.id
        )
        db.session.add(bloqueo)
        db.session.commit()
        
        flash('Bloqueo creado correctamente', 'success')
        return redirect(url_for('bloqueos.index', propiedad_id=propiedad_id))
    
    return render_template('bloqueos/nuevo.html', form=form, propiedad=propiedad)
@bloqueos_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    """Eliminar (o desactivar) un bloqueo"""
    bloqueo = BloqueoPropiedad.query.get_or_404(id)
    propiedad = Propiedad.query.get(bloqueo.propiedad_id)
    
    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('propiedades.index'))
    
    # Mejor desactivar que eliminar (auditoría)
    bloqueo.activo = False
    db.session.commit()
    
    flash('Bloqueo eliminado/desactivado correctamente', 'success')
    return redirect(url_for('bloqueos.index', propiedad_id=bloqueo.propiedad_id))