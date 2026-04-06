from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, Ingreso, Propiedad, Reserva
from forms import IngresoForm
from datetime import datetime
from utils import log_audit
from permisos import propiedades_visibles_query, propiedad_es_visible, usuario_tiene_permiso

ingresos_bp = Blueprint('ingresos', __name__, url_prefix='/ingresos')


def _propiedades_usuario():
    return propiedades_visibles_query().order_by(Propiedad.nombre.asc()).all()


def _ids_propiedades_usuario():
    return [p.id for p in _propiedades_usuario()]


def _reserva_visible(reserva):
    if not reserva or not reserva.propiedad:
        return False
    return propiedad_es_visible(reserva.propiedad)


@ingresos_bp.route('/')
@login_required
def index():
    if not usuario_tiene_permiso('puede_gestionar_finanzas'):
        flash('No tienes permisos para acceder a ingresos.', 'danger')
        return redirect(url_for('main.dashboard'))

    propiedades = _propiedades_usuario()
    propiedad_ids = [p.id for p in propiedades]

    if not propiedad_ids:
        return render_template(
            'ingresos/index.html',
            ingresos=[],
            propiedades=[],
            total_filtro=0,
            total_general=0
        )

    query = Ingreso.query.filter(Ingreso.propiedad_id.in_(propiedad_ids))

    propiedad_filtro = request.args.get('propiedad', type=int)
    if propiedad_filtro and propiedad_filtro in propiedad_ids:
        query = query.filter_by(propiedad_id=propiedad_filtro)

    metodo_pago = request.args.get('metodo_pago')
    if metodo_pago:
        query = query.filter_by(metodo_pago=metodo_pago)

    fecha_desde = request.args.get('fecha_desde')
    if fecha_desde:
        try:
            query = query.filter(Ingreso.fecha >= datetime.strptime(fecha_desde, '%Y-%m-%d').date())
        except ValueError:
            flash('La fecha desde no es válida.', 'warning')

    fecha_hasta = request.args.get('fecha_hasta')
    if fecha_hasta:
        try:
            query = query.filter(Ingreso.fecha <= datetime.strptime(fecha_hasta, '%Y-%m-%d').date())
        except ValueError:
            flash('La fecha hasta no es válida.', 'warning')

    ingresos = query.order_by(Ingreso.fecha.desc(), Ingreso.id.desc()).all()

    total_filtro = sum((i.cantidad or 0) for i in ingresos) if ingresos else 0
    total_general = db.session.query(db.func.sum(Ingreso.cantidad)).filter(
        Ingreso.propiedad_id.in_(propiedad_ids)
    ).scalar() or 0

    return render_template(
        'ingresos/index.html',
        ingresos=ingresos,
        propiedades=propiedades,
        total_filtro=total_filtro,
        total_general=total_general
    )


@ingresos_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if not usuario_tiene_permiso('puede_gestionar_finanzas'):
        flash('No tienes permisos para crear ingresos.', 'danger')
        return redirect(url_for('main.dashboard'))

    form = IngresoForm()
    propiedades = _propiedades_usuario()
    propiedad_ids = [p.id for p in propiedades]

    form.propiedad_id.choices = [(0, 'Ninguna')] + [(p.id, p.nombre) for p in propiedades]

    reservas = Reserva.query.filter(
        Reserva.propiedad_id.in_(propiedad_ids)
    ).order_by(Reserva.fecha_entrada.desc()).all() if propiedad_ids else []

    form.reserva_id.choices = [
        (0, 'Ninguna')
    ] + [
        (
            r.id,
            f"{r.huespedes.first().nombre if r.huespedes.first() else 'Sin huésped'} ({r.fecha_entrada} - {r.fecha_salida})"
        )
        for r in reservas
    ]

    if form.validate_on_submit():
        propiedad_id = form.propiedad_id.data if form.propiedad_id.data != 0 else None
        reserva_id = form.reserva_id.data if form.reserva_id.data != 0 else None

        if propiedad_id and propiedad_id not in propiedad_ids:
            flash('No tienes permiso para usar esa propiedad.', 'danger')
            return render_template('ingresos/nuevo.html', form=form)

        reserva = Reserva.query.get(reserva_id) if reserva_id else None
        if reserva_id and not _reserva_visible(reserva):
            flash('No tienes permiso para usar esa reserva.', 'danger')
            return render_template('ingresos/nuevo.html', form=form)

        ingreso = Ingreso(
            propiedad_id=propiedad_id,
            reserva_id=reserva_id,
            fecha=form.fecha.data,
            concepto=form.concepto.data,
            cantidad=form.cantidad.data,
            moneda=form.moneda.data,
            metodo_pago=form.metodo_pago.data,
            observaciones=form.observaciones.data
        )
        db.session.add(ingreso)
        db.session.commit()

        log_audit(
            current_user.id,
            'crear',
            'ingreso',
            ingreso.id,
            None,
            {
                'concepto': ingreso.concepto,
                'cantidad': ingreso.cantidad,
                'propiedad_id': ingreso.propiedad_id,
                'reserva_id': ingreso.reserva_id
            }
        )

        flash('Ingreso registrado correctamente', 'success')
        return redirect(url_for('ingresos.index'))

    return render_template('ingresos/nuevo.html', form=form)


@ingresos_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    if not usuario_tiene_permiso('puede_gestionar_finanzas'):
        flash('No tienes permisos para editar ingresos.', 'danger')
        return redirect(url_for('main.dashboard'))

    ingreso = Ingreso.query.get_or_404(id)

    if ingreso.propiedad and not propiedad_es_visible(ingreso.propiedad):
        flash('No tienes permiso para editar este ingreso', 'danger')
        return redirect(url_for('ingresos.index'))

    form = IngresoForm(obj=ingreso)
    propiedades = _propiedades_usuario()
    propiedad_ids = [p.id for p in propiedades]

    form.propiedad_id.choices = [(0, 'Ninguna')] + [(p.id, p.nombre) for p in propiedades]

    reservas = Reserva.query.filter(
        Reserva.propiedad_id.in_(propiedad_ids)
    ).order_by(Reserva.fecha_entrada.desc()).all() if propiedad_ids else []

    form.reserva_id.choices = [
        (0, 'Ninguna')
    ] + [
        (
            r.id,
            f"{r.huespedes.first().nombre if r.huespedes.first() else 'Sin huésped'} ({r.fecha_entrada} - {r.fecha_salida})"
        )
        for r in reservas
    ]

    if form.validate_on_submit():
        propiedad_id = form.propiedad_id.data if form.propiedad_id.data != 0 else None
        reserva_id = form.reserva_id.data if form.reserva_id.data != 0 else None

        if propiedad_id and propiedad_id not in propiedad_ids:
            flash('No tienes permiso para usar esa propiedad.', 'danger')
            return render_template('ingresos/editar.html', form=form, ingreso=ingreso)

        reserva = Reserva.query.get(reserva_id) if reserva_id else None
        if reserva_id and not _reserva_visible(reserva):
            flash('No tienes permiso para usar esa reserva.', 'danger')
            return render_template('ingresos/editar.html', form=form, ingreso=ingreso)

        form.populate_obj(ingreso)
        ingreso.propiedad_id = propiedad_id
        ingreso.reserva_id = reserva_id
        db.session.commit()

        log_audit(
            current_user.id,
            'editar',
            'ingreso',
            ingreso.id,
            None,
            {
                'concepto': ingreso.concepto,
                'cantidad': ingreso.cantidad,
                'propiedad_id': ingreso.propiedad_id,
                'reserva_id': ingreso.reserva_id
            }
        )

        flash('Ingreso actualizado', 'success')
        return redirect(url_for('ingresos.index'))

    return render_template('ingresos/editar.html', form=form, ingreso=ingreso)


@ingresos_bp.route('/ver/<int:id>')
@login_required
def ver(id):
    if not usuario_tiene_permiso('puede_gestionar_finanzas'):
        flash('No tienes permisos para ver ingresos.', 'danger')
        return redirect(url_for('main.dashboard'))

    ingreso = Ingreso.query.get_or_404(id)

    if ingreso.propiedad and not propiedad_es_visible(ingreso.propiedad):
        flash('No tienes permiso para ver este ingreso', 'danger')
        return redirect(url_for('ingresos.index'))

    return render_template('ingresos/ver.html', ingreso=ingreso)


@ingresos_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    if not usuario_tiene_permiso('puede_gestionar_finanzas'):
        flash('No tienes permisos para eliminar ingresos.', 'danger')
        return redirect(url_for('main.dashboard'))

    ingreso = Ingreso.query.get_or_404(id)

    if ingreso.propiedad and not propiedad_es_visible(ingreso.propiedad):
        flash('No tienes permiso para eliminar este ingreso', 'danger')
        return redirect(url_for('ingresos.index'))

    datos_eliminados = {
        'id': ingreso.id,
        'concepto': ingreso.concepto,
        'cantidad': ingreso.cantidad,
        'propiedad_id': ingreso.propiedad_id,
        'reserva_id': ingreso.reserva_id
    }

    db.session.delete(ingreso)
    db.session.commit()

    log_audit(current_user.id, 'eliminar', 'ingreso', ingreso.id, datos_eliminados, None)

    flash('Ingreso eliminado', 'success')
    return redirect(url_for('ingresos.index'))