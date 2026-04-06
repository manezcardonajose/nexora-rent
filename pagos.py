from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, PagoReserva, Reserva, Ingreso, Propiedad
from forms import PagoReservaForm
from datetime import datetime

pagos_bp = Blueprint('pagos', __name__, url_prefix='/pagos')


def _nombre_huesped_reserva(reserva):
    primer_huesped = reserva.huespedes.first()
    if not primer_huesped:
        return "Sin huésped"
    nombre = primer_huesped.nombre or ""
    apellidos = primer_huesped.apellidos or ""
    return f"{nombre} {apellidos}".strip()


@pagos_bp.route('/reserva/<int:reserva_id>')
@login_required
def index(reserva_id):
    """Ver todos los pagos de una reserva"""
    reserva = Reserva.query.get_or_404(reserva_id)
    propiedad = Propiedad.query.get(reserva.propiedad_id)

    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('reservas.index'))

    pagos = PagoReserva.query.filter_by(reserva_id=reserva_id).order_by(
        PagoReserva.fecha_pago.desc(),
        PagoReserva.id.desc()
    ).all()

    total_pagado = sum((p.monto or 0) for p in pagos)
    pendiente = max((reserva.precio_total or 0) - total_pagado, 0)

    return render_template(
        'pagos/index.html',
        reserva=reserva,
        pagos=pagos,
        total_pagado=total_pagado,
        pendiente=pendiente,
        nombre_huesped=_nombre_huesped_reserva(reserva)
    )


@pagos_bp.route('/nuevo/<int:reserva_id>', methods=['GET', 'POST'])
@login_required
def nuevo(reserva_id):
    """Registrar un nuevo pago para una reserva"""
    reserva = Reserva.query.get_or_404(reserva_id)
    propiedad = Propiedad.query.get(reserva.propiedad_id)

    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('reservas.index'))

    form = PagoReservaForm()

    if form.validate_on_submit():
        monto = form.monto.data or 0
        saldo_actual = float(reserva.saldo_pendiente or 0)

        if monto <= 0:
            flash('El importe del pago debe ser mayor que cero.', 'warning')
            return render_template(
                'pagos/nuevo.html',
                form=form,
                reserva=reserva,
                nombre_huesped=_nombre_huesped_reserva(reserva)
            )

        if monto > saldo_actual and saldo_actual > 0:
            flash(f'El pago no puede ser mayor que el saldo pendiente ({saldo_actual:.2f} €).', 'danger')
            return render_template(
                'pagos/nuevo.html',
                form=form,
                reserva=reserva,
                nombre_huesped=_nombre_huesped_reserva(reserva)
            )

        if form.concepto.data == 'otro' and form.concepto_personalizado.data:
            concepto_final = form.concepto_personalizado.data.strip()
        else:
            concepto_final = dict(form.concepto.choices).get(form.concepto.data, 'Pago')

        ingreso = Ingreso(
            propiedad_id=reserva.propiedad_id,
            reserva_id=reserva.id,
            fecha=form.fecha_pago.data,
            concepto=f"Pago reserva #{reserva.id} - {concepto_final}",
            cantidad=monto,
            moneda='EUR',
            metodo_pago=form.metodo_pago.data,
            observaciones=f"Referencia: {form.referencia.data or 'N/A'}"
        )
        db.session.add(ingreso)
        db.session.flush()  # importante para obtener ingreso.id

        pago = PagoReserva(
            reserva_id=reserva_id,
            fecha_pago=form.fecha_pago.data,
            monto=monto,
            metodo_pago=form.metodo_pago.data,
            concepto=concepto_final,
            referencia=form.referencia.data,
            observaciones=form.observaciones.data,
            ingreso_id=ingreso.id
        )
        db.session.add(pago)

        reserva.deposito_pagado = float(reserva.deposito_pagado or 0) + float(monto)
        reserva.saldo_pendiente = float(reserva.precio_total or 0) - float(reserva.deposito_pagado or 0)

        if reserva.saldo_pendiente <= 0:
            reserva.saldo_pendiente = 0
            reserva.fecha_pago_total = datetime.today().date()

        db.session.commit()

        flash(f'Pago de {monto:.2f} € registrado correctamente', 'success')
        return redirect(url_for('pagos.index', reserva_id=reserva_id))

    return render_template(
        'pagos/nuevo.html',
        form=form,
        reserva=reserva,
        nombre_huesped=_nombre_huesped_reserva(reserva)
    )


@pagos_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    """Eliminar un pago"""
    pago = PagoReserva.query.get_or_404(id)
    reserva = pago.reserva
    propiedad = Propiedad.query.get(reserva.propiedad_id)

    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('reservas.index'))

    monto = float(pago.monto or 0)
    reserva_id = reserva.id

    reserva.deposito_pagado = max(float(reserva.deposito_pagado or 0) - monto, 0)
    reserva.saldo_pendiente = max(float(reserva.precio_total or 0) - float(reserva.deposito_pagado or 0), 0)

    if pago.ingreso_id:
        ingreso = Ingreso.query.get(pago.ingreso_id)
        if ingreso:
            db.session.delete(ingreso)

    db.session.delete(pago)
    db.session.commit()

    flash(f'Pago de {monto:.2f} € eliminado. Saldo pendiente: {reserva.saldo_pendiente:.2f} €', 'warning')
    return redirect(url_for('pagos.index', reserva_id=reserva_id))