from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, Gasto, Propiedad, Reserva
from forms import GastoForm
from datetime import datetime
from utils import log_audit
from permisos import propiedades_visibles_query, propiedad_es_visible, usuario_tiene_permiso

gastos_bp = Blueprint('gastos', __name__, url_prefix='/gastos')


def _propiedades_usuario():
    return propiedades_visibles_query().order_by(Propiedad.nombre.asc()).all()


def _ids_propiedades_usuario():
    return [p.id for p in _propiedades_usuario()]


def _reservas_usuario(propiedad_ids):
    if not propiedad_ids:
        return []
    return Reserva.query.filter(
        Reserva.propiedad_id.in_(propiedad_ids)
    ).order_by(Reserva.fecha_entrada.desc()).all()


def _reserva_visible(reserva):
    if not reserva or not reserva.propiedad:
        return False
    return propiedad_es_visible(reserva.propiedad)


@gastos_bp.route('/')
@login_required
def index():
    if not usuario_tiene_permiso('puede_gestionar_finanzas'):
        flash('No tienes permisos para acceder a gastos.', 'danger')
        return redirect(url_for('main.dashboard'))

    propiedades = _propiedades_usuario()
    propiedad_ids = [p.id for p in propiedades]

    propiedad_filtro = request.args.get('propiedad', type=int)
    categoria_filtro = (request.args.get('categoria') or '').strip()
    fecha_desde = (request.args.get('fecha_desde') or '').strip()
    fecha_hasta = (request.args.get('fecha_hasta') or '').strip()

    if not propiedad_ids:
        return render_template(
            'gastos/index.html',
            gastos=[],
            propiedades=[],
            total_filtro=0,
            total_general=0,
            filtros={
                'propiedad': propiedad_filtro,
                'categoria': categoria_filtro,
                'fecha_desde': fecha_desde,
                'fecha_hasta': fecha_hasta
            }
        )

    query = Gasto.query.filter(Gasto.propiedad_id.in_(propiedad_ids))

    if propiedad_filtro and propiedad_filtro in propiedad_ids:
        query = query.filter_by(propiedad_id=propiedad_filtro)

    if categoria_filtro:
        query = query.filter_by(categoria=categoria_filtro)

    if fecha_desde:
        try:
            fecha_desde_date = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
            query = query.filter(Gasto.fecha >= fecha_desde_date)
        except ValueError:
            flash('La fecha desde no es válida.', 'warning')

    if fecha_hasta:
        try:
            fecha_hasta_date = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
            query = query.filter(Gasto.fecha <= fecha_hasta_date)
        except ValueError:
            flash('La fecha hasta no es válida.', 'warning')

    gastos = query.order_by(Gasto.fecha.desc(), Gasto.id.desc()).all()

    total_filtro = sum((g.cantidad or 0) for g in gastos)
    total_general = db.session.query(db.func.sum(Gasto.cantidad)).filter(
        Gasto.propiedad_id.in_(propiedad_ids)
    ).scalar() or 0

    return render_template(
        'gastos/index.html',
        gastos=gastos,
        propiedades=propiedades,
        total_filtro=total_filtro,
        total_general=total_general,
        filtros={
            'propiedad': propiedad_filtro,
            'categoria': categoria_filtro,
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta
        }
    )


@gastos_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if not usuario_tiene_permiso('puede_gestionar_finanzas'):
        flash('No tienes permisos para crear gastos.', 'danger')
        return redirect(url_for('main.dashboard'))

    form = GastoForm()

    propiedades = _propiedades_usuario()
    propiedad_ids = [p.id for p in propiedades]
    reservas = _reservas_usuario(propiedad_ids)

    form.propiedad_id.choices = [(0, 'Ninguna')] + [(p.id, p.nombre) for p in propiedades]

    if form.validate_on_submit():
        propiedad_id = form.propiedad_id.data if form.propiedad_id.data != 0 else None
        reserva_id = request.form.get('reserva_id', type=int)

        if propiedad_id and propiedad_id not in propiedad_ids:
            flash('No tienes permiso para usar esa propiedad.', 'danger')
            return render_template('gastos/nuevo.html', form=form, reservas=reservas)

        reserva = Reserva.query.get(reserva_id) if reserva_id else None
        if reserva_id and not _reserva_visible(reserva):
            flash('No tienes permiso para usar esa reserva.', 'danger')
            return render_template('gastos/nuevo.html', form=form, reservas=reservas)

        gasto = Gasto(
            propiedad_id=propiedad_id,
            reserva_id=reserva_id if reserva_id and reserva_id != 0 else None,
            fecha=form.fecha.data,
            concepto=form.concepto.data,
            categoria=form.categoria.data,
            cantidad=form.cantidad.data,
            moneda=form.moneda.data,
            proveedor=form.proveedor.data,
            metodo_pago=form.metodo_pago.data,
            observaciones=form.observaciones.data
        )

        db.session.add(gasto)
        db.session.commit()

        log_audit(
            current_user.id,
            'crear',
            'gasto',
            gasto.id,
            None,
            {
                'concepto': gasto.concepto,
                'cantidad': gasto.cantidad,
                'categoria': gasto.categoria,
                'propiedad_id': gasto.propiedad_id,
                'reserva_id': gasto.reserva_id
            }
        )

        flash('Gasto registrado correctamente', 'success')
        return redirect(url_for('gastos.index'))

    return render_template(
        'gastos/nuevo.html',
        form=form,
        reservas=reservas
    )


@gastos_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    if not usuario_tiene_permiso('puede_gestionar_finanzas'):
        flash('No tienes permisos para editar gastos.', 'danger')
        return redirect(url_for('main.dashboard'))

    gasto = Gasto.query.get_or_404(id)

    if gasto.propiedad and not propiedad_es_visible(gasto.propiedad):
        flash('No tienes permiso para editar este gasto', 'danger')
        return redirect(url_for('gastos.index'))

    form = GastoForm(obj=gasto)

    propiedades = _propiedades_usuario()
    propiedad_ids = [p.id for p in propiedades]
    reservas = _reservas_usuario(propiedad_ids)

    form.propiedad_id.choices = [(0, 'Ninguna')] + [(p.id, p.nombre) for p in propiedades]

    if form.validate_on_submit():
        propiedad_id = form.propiedad_id.data if form.propiedad_id.data != 0 else None
        reserva_id = request.form.get('reserva_id', type=int)

        if propiedad_id and propiedad_id not in propiedad_ids:
            flash('No tienes permiso para usar esa propiedad.', 'danger')
            return render_template('gastos/editar.html', form=form, gasto=gasto, reservas=reservas)

        reserva = Reserva.query.get(reserva_id) if reserva_id else None
        if reserva_id and not _reserva_visible(reserva):
            flash('No tienes permiso para usar esa reserva.', 'danger')
            return render_template('gastos/editar.html', form=form, gasto=gasto, reservas=reservas)

        gasto.propiedad_id = propiedad_id
        gasto.reserva_id = reserva_id if reserva_id and reserva_id != 0 else None
        gasto.fecha = form.fecha.data
        gasto.concepto = form.concepto.data
        gasto.categoria = form.categoria.data
        gasto.cantidad = form.cantidad.data
        gasto.moneda = form.moneda.data
        gasto.proveedor = form.proveedor.data
        gasto.metodo_pago = form.metodo_pago.data
        gasto.observaciones = form.observaciones.data

        db.session.commit()

        log_audit(
            current_user.id,
            'editar',
            'gasto',
            gasto.id,
            None,
            {
                'concepto': gasto.concepto,
                'cantidad': gasto.cantidad,
                'categoria': gasto.categoria,
                'propiedad_id': gasto.propiedad_id,
                'reserva_id': gasto.reserva_id
            }
        )

        flash('Gasto actualizado', 'success')
        return redirect(url_for('gastos.index'))

    return render_template(
        'gastos/editar.html',
        form=form,
        gasto=gasto,
        reservas=reservas
    )


@gastos_bp.route('/ver/<int:id>')
@login_required
def ver(id):
    if not usuario_tiene_permiso('puede_gestionar_finanzas'):
        flash('No tienes permisos para ver gastos.', 'danger')
        return redirect(url_for('main.dashboard'))

    gasto = Gasto.query.get_or_404(id)

    if gasto.propiedad and not propiedad_es_visible(gasto.propiedad):
        flash('No tienes permiso para ver este gasto', 'danger')
        return redirect(url_for('gastos.index'))

    return render_template('gastos/ver.html', gasto=gasto)


@gastos_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    if not usuario_tiene_permiso('puede_gestionar_finanzas'):
        flash('No tienes permisos para eliminar gastos.', 'danger')
        return redirect(url_for('main.dashboard'))

    gasto = Gasto.query.get_or_404(id)

    if gasto.propiedad and not propiedad_es_visible(gasto.propiedad):
        flash('No tienes permiso para eliminar este gasto', 'danger')
        return redirect(url_for('gastos.index'))

    datos_eliminados = {
        'id': gasto.id,
        'concepto': gasto.concepto,
        'cantidad': gasto.cantidad,
        'categoria': gasto.categoria,
        'propiedad_id': gasto.propiedad_id,
        'reserva_id': gasto.reserva_id
    }

    db.session.delete(gasto)
    db.session.commit()

    log_audit(current_user.id, 'eliminar', 'gasto', gasto.id, datos_eliminados, None)

    flash('Gasto eliminado', 'success')
    return redirect(url_for('gastos.index'))