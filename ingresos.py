from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, Ingreso, Propiedad, Reserva
from forms import IngresoForm
from datetime import datetime

ingresos_bp = Blueprint('ingresos', __name__, url_prefix='/ingresos')

@ingresos_bp.route('/')
@login_required
def index():
    # Obtener propiedades del usuario
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    propiedad_ids = [p.id for p in propiedades]
    
    # Si no hay propiedades, mostrar vacío
    if not propiedad_ids:
        return render_template('ingresos/index.html', 
                               ingresos=[],
                               propiedades=[],
                               total_filtro=0,
                               total_general=0)
    
    # Consulta base: ingresos de propiedades del usuario
    query = Ingreso.query.filter(Ingreso.propiedad_id.in_(propiedad_ids))
    
    # Aplicar filtros desde request.args
    propiedad_filtro = request.args.get('propiedad', type=int)
    if propiedad_filtro:
        query = query.filter_by(propiedad_id=propiedad_filtro)
    
    metodo_pago = request.args.get('metodo_pago')
    if metodo_pago:
        query = query.filter_by(metodo_pago=metodo_pago)
    
    fecha_desde = request.args.get('fecha_desde')
    if fecha_desde:
        query = query.filter(Ingreso.fecha >= datetime.strptime(fecha_desde, '%Y-%m-%d').date())
    
    fecha_hasta = request.args.get('fecha_hasta')
    if fecha_hasta:
        query = query.filter(Ingreso.fecha <= datetime.strptime(fecha_hasta, '%Y-%m-%d').date())
    
    ingresos = query.order_by(Ingreso.fecha.desc()).all()
    
    # Calcular totales usando 'cantidad' en lugar de 'monto'
    total_filtro = sum(i.cantidad for i in ingresos) if ingresos else 0
    total_general = db.session.query(db.func.sum(Ingreso.cantidad)).filter(Ingreso.propiedad_id.in_(propiedad_ids)).scalar() or 0
    
    return render_template('ingresos/index.html', 
                           ingresos=ingresos,
                           propiedades=propiedades,
                           total_filtro=total_filtro,
                           total_general=total_general)


@ingresos_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    form = IngresoForm()
    
    # Poblar selects
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    form.propiedad_id.choices = [(0, 'Ninguna')] + [(p.id, p.nombre) for p in propiedades]
    
    # Reservas de esas propiedades
    propiedad_ids = [p.id for p in propiedades]
    reservas = Reserva.query.filter(Reserva.propiedad_id.in_(propiedad_ids)).order_by(Reserva.fecha_entrada.desc()).all()
    form.reserva_id.choices = [(0, 'Ninguna')] + [(r.id, f"{r.huesped_nombre} ({r.fecha_entrada} - {r.fecha_salida})") for r in reservas]
    
    if form.validate_on_submit():
        ingreso = Ingreso(
            propiedad_id=form.propiedad_id.data if form.propiedad_id.data != 0 else None,
            reserva_id=form.reserva_id.data if form.reserva_id.data != 0 else None,
            fecha=form.fecha.data,
            concepto=form.concepto.data,
            cantidad=form.cantidad.data,  # <-- CAMBIO
            moneda=form.moneda.data,
            metodo_pago=form.metodo_pago.data,
            observaciones=form.observaciones.data
        )
        db.session.add(ingreso)
        db.session.commit()
        flash('Ingreso registrado correctamente', 'success')
        return redirect(url_for('ingresos.index'))
    
    return render_template('ingresos/nuevo.html', form=form)


@ingresos_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    ingreso = Ingreso.query.get_or_404(id)
    
    # Verificar permisos
    if ingreso.propiedad and ingreso.propiedad.usuario_id != current_user.id:
        flash('No tienes permiso para editar este ingreso', 'danger')
        return redirect(url_for('ingresos.index'))
    
    form = IngresoForm(obj=ingreso)
    
    # Poblar selects
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    form.propiedad_id.choices = [(0, 'Ninguna')] + [(p.id, p.nombre) for p in propiedades]
    
    propiedad_ids = [p.id for p in propiedades]
    reservas = Reserva.query.filter(Reserva.propiedad_id.in_(propiedad_ids)).order_by(Reserva.fecha_entrada.desc()).all()
    form.reserva_id.choices = [(0, 'Ninguna')] + [(r.id, f"{r.huesped_nombre} ({r.fecha_entrada} - {r.fecha_salida})") for r in reservas]
    
    if form.validate_on_submit():
        ingreso.propiedad_id = form.propiedad_id.data if form.propiedad_id.data != 0 else None
        ingreso.reserva_id = form.reserva_id.data if form.reserva_id.data != 0 else None
        ingreso.fecha = form.fecha.data
        ingreso.concepto = form.concepto.data
        ingreso.cantidad = form.cantidad.data  # <-- CAMBIO
        ingreso.moneda = form.moneda.data
        ingreso.metodo_pago = form.metodo_pago.data
        ingreso.observaciones = form.observaciones.data
        db.session.commit()
        flash('Ingreso actualizado', 'success')
        return redirect(url_for('ingresos.index'))
    
    return render_template('ingresos/editar.html', form=form, ingreso=ingreso)


@ingresos_bp.route('/ver/<int:id>')
@login_required
def ver(id):
    ingreso = Ingreso.query.get_or_404(id)
    
    # Verificar permisos
    if ingreso.propiedad and ingreso.propiedad.usuario_id != current_user.id:
        flash('No tienes permiso para ver este ingreso', 'danger')
        return redirect(url_for('ingresos.index'))
    
    return render_template('ingresos/ver.html', ingreso=ingreso)


@ingresos_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    ingreso = Ingreso.query.get_or_404(id)
    
    # Verificar permisos
    if ingreso.propiedad and ingreso.propiedad.usuario_id != current_user.id:
        flash('No tienes permiso para eliminar este ingreso', 'danger')
        return redirect(url_for('ingresos.index'))
    
    db.session.delete(ingreso)
    db.session.commit()
    flash('Ingreso eliminado', 'success')
    return redirect(url_for('ingresos.index'))