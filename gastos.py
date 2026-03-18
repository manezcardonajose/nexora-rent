from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, Gasto, Propiedad
from forms import GastoForm
from datetime import datetime

gastos_bp = Blueprint('gastos', __name__, url_prefix='/gastos')

@gastos_bp.route('/')
@login_required
def index():
    # Obtener propiedades del usuario
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    propiedad_ids = [p.id for p in propiedades]
    
    # Si no hay propiedades, mostrar vacío
    if not propiedad_ids:
        return render_template('gastos/index.html', 
                               gastos=[],
                               propiedades=[],
                               total_filtro=0,
                               total_general=0)
    
    # Consulta base
    query = Gasto.query.filter(Gasto.propiedad_id.in_(propiedad_ids))
    
    # Filtros
    propiedad_filtro = request.args.get('propiedad', type=int)
    if propiedad_filtro:
        query = query.filter_by(propiedad_id=propiedad_filtro)
    
    categoria = request.args.get('categoria')
    if categoria:
        query = query.filter_by(categoria=categoria)
    
    fecha_desde = request.args.get('fecha_desde')
    if fecha_desde:
        query = query.filter(Gasto.fecha >= datetime.strptime(fecha_desde, '%Y-%m-%d').date())
    
    fecha_hasta = request.args.get('fecha_hasta')
    if fecha_hasta:
        query = query.filter(Gasto.fecha <= datetime.strptime(fecha_hasta, '%Y-%m-%d').date())
    
    gastos = query.order_by(Gasto.fecha.desc()).all()
    
    # Calcular totales usando 'cantidad'
    total_filtro = sum(g.cantidad for g in gastos) if gastos else 0
    total_general = db.session.query(db.func.sum(Gasto.cantidad)).filter(Gasto.propiedad_id.in_(propiedad_ids)).scalar() or 0
    
    return render_template('gastos/index.html', 
                           gastos=gastos,
                           propiedades=propiedades,
                           total_filtro=total_filtro,
                           total_general=total_general)


@gastos_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    form = GastoForm()
    
    # Poblar selects
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    form.propiedad_id.choices = [(0, 'Ninguna')] + [(p.id, p.nombre) for p in propiedades]
    
    if form.validate_on_submit():
        gasto = Gasto(
            propiedad_id=form.propiedad_id.data if form.propiedad_id.data != 0 else None,
            fecha=form.fecha.data,
            concepto=form.concepto.data,
            categoria=form.categoria.data,
            cantidad=form.cantidad.data,  # <-- CAMBIO
            moneda=form.moneda.data,
            proveedor=form.proveedor.data,
            metodo_pago=form.metodo_pago.data,
            observaciones=form.observaciones.data
        )
        db.session.add(gasto)
        db.session.commit()
        flash('Gasto registrado correctamente', 'success')
        return redirect(url_for('gastos.index'))
    
    return render_template('gastos/nuevo.html', form=form)


@gastos_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    gasto = Gasto.query.get_or_404(id)
    
    # Verificar permisos
    if gasto.propiedad and gasto.propiedad.usuario_id != current_user.id:
        flash('No tienes permiso para editar este gasto', 'danger')
        return redirect(url_for('gastos.index'))
    
    form = GastoForm(obj=gasto)
    
    # Poblar selects
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    form.propiedad_id.choices = [(0, 'Ninguna')] + [(p.id, p.nombre) for p in propiedades]
    
    if form.validate_on_submit():
        gasto.propiedad_id = form.propiedad_id.data if form.propiedad_id.data != 0 else None
        gasto.fecha = form.fecha.data
        gasto.concepto = form.concepto.data
        gasto.categoria = form.categoria.data
        gasto.cantidad = form.cantidad.data  # <-- CAMBIO
        gasto.moneda = form.moneda.data
        gasto.proveedor = form.proveedor.data
        gasto.metodo_pago = form.metodo_pago.data
        gasto.observaciones = form.observaciones.data
        db.session.commit()
        flash('Gasto actualizado', 'success')
        return redirect(url_for('gastos.index'))
    
    return render_template('gastos/editar.html', form=form, gasto=gasto)


@gastos_bp.route('/ver/<int:id>')
@login_required
def ver(id):
    gasto = Gasto.query.get_or_404(id)
    
    # Verificar permisos
    if gasto.propiedad and gasto.propiedad.usuario_id != current_user.id:
        flash('No tienes permiso para ver este gasto', 'danger')
        return redirect(url_for('gastos.index'))
    
    return render_template('gastos/ver.html', gasto=gasto)


@gastos_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    gasto = Gasto.query.get_or_404(id)
    
    # Verificar permisos
    if gasto.propiedad and gasto.propiedad.usuario_id != current_user.id:
        flash('No tienes permiso para eliminar este gasto', 'danger')
        return redirect(url_for('gastos.index'))
    
    db.session.delete(gasto)
    db.session.commit()
    flash('Gasto eliminado', 'success')
    return redirect(url_for('gastos.index'))