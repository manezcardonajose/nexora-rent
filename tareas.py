from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, Tarea, Propiedad
from forms import TareaForm
from datetime import datetime

tareas_bp = Blueprint('tareas', __name__, url_prefix='/tareas')

@tareas_bp.route('/')
@login_required
def index():
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    propiedad_ids = [p.id for p in propiedades]
    tareas = Tarea.query.filter(Tarea.propiedad_id.in_(propiedad_ids)).order_by(Tarea.fecha_asignada.desc()).all()
    return render_template('tareas/index.html', tareas=tareas)

@tareas_bp.route('/nueva', methods=['GET', 'POST'])
@login_required
def nueva():
    form = TareaForm()
    
    # Choices para propiedad
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    form.propiedad_id.choices = [(p.id, p.nombre) for p in propiedades]
    
    # Choices para reserva (solo reservas futuras de esas propiedades)
    from models import Reserva
    propiedades_ids = [p.id for p in propiedades]
    
    # Obtener reservas con fechas futuras
    reservas = Reserva.query.filter(
        Reserva.propiedad_id.in_(propiedades_ids),
        Reserva.fecha_salida >= datetime.today().date()
    ).all()
    
    # 🔴 CORREGIDO: Usar el primer huésped en lugar de huesped_nombre
    choices_reservas = [(0, 'Ninguna')]
    for r in reservas:
        # Obtener el primer huésped para el nombre
        primer_huesped = r.huespedes.first()
        if primer_huesped:
            nombre = f"{primer_huesped.nombre} {primer_huesped.apellidos}"
        else:
            nombre = "Huésped no registrado"
        
        choices_reservas.append((
            r.id, 
            f"{nombre} ({r.fecha_entrada} a {r.fecha_salida})"
        ))
    
    form.reserva_id.choices = choices_reservas
    
    # Choices para asignado a (usuarios)
    from models import User
    usuarios = User.query.filter_by(activo=True).all()
    form.asignado_a_id.choices = [(u.id, u.nombre or u.username) for u in usuarios]
    
    if form.validate_on_submit():
        tarea = Tarea(
            propiedad_id=form.propiedad_id.data,
            reserva_id=form.reserva_id.data if form.reserva_id.data != 0 else None,
            tipo=form.tipo.data,
            descripcion=form.descripcion.data,
            fecha_asignada=form.fecha_asignada.data,
            fecha_limite=form.fecha_limite.data,
            asignado_a_id=form.asignado_a_id.data,
            notas=form.notas.data,
            completada=form.completada.data
        )
        db.session.add(tarea)
        db.session.commit()
        flash('Tarea creada correctamente', 'success')
        return redirect(url_for('tareas.index'))
    
    return render_template('tareas/nueva.html', form=form)

@tareas_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    tarea = Tarea.query.get_or_404(id)
    propiedad = Propiedad.query.get(tarea.propiedad_id)
    if propiedad.usuario_id != current_user.id:
        flash('No tienes permiso para editar esta tarea', 'danger')
        return redirect(url_for('tareas.index'))
    
    form = TareaForm(obj=tarea)
    
    # Choices para propiedad
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    form.propiedad_id.choices = [(p.id, p.nombre) for p in propiedades]
    
    # Choices para reserva (con nombre corregido)
    from models import Reserva
    propiedades_ids = [p.id for p in propiedades]
    reservas = Reserva.query.filter(Reserva.propiedad_id.in_(propiedades_ids)).all()
    
    choices_reservas = [(0, 'Ninguna')]
    for r in reservas:
        primer_huesped = r.huespedes.first()
        if primer_huesped:
            nombre = f"{primer_huesped.nombre} {primer_huesped.apellidos}"
        else:
            nombre = "Huésped no registrado"
        
        choices_reservas.append((
            r.id, 
            f"{nombre} ({r.fecha_entrada} a {r.fecha_salida})"
        ))
    
    form.reserva_id.choices = choices_reservas
    
    # Choices para asignado a
    from models import User
    usuarios = User.query.filter_by(activo=True).all()
    form.asignado_a_id.choices = [(u.id, u.nombre or u.username) for u in usuarios]
    
    if form.validate_on_submit():
        form.populate_obj(tarea)
        if form.reserva_id.data == 0:
            tarea.reserva_id = None
        db.session.commit()
        flash('Tarea actualizada', 'success')
        return redirect(url_for('tareas.index'))
    
    return render_template('tareas/editar.html', form=form, tarea=tarea)

@tareas_bp.route('/completar/<int:id>', methods=['POST'])
@login_required
def completar(id):
    tarea = Tarea.query.get_or_404(id)
    propiedad = Propiedad.query.get(tarea.propiedad_id)
    if propiedad.usuario_id != current_user.id:
        flash('No tienes permiso', 'danger')
        return redirect(url_for('tareas.index'))
    tarea.completada = True
    tarea.fecha_completada = datetime.utcnow()
    db.session.commit()
    flash('Tarea marcada como completada', 'success')
    return redirect(url_for('tareas.index'))