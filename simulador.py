from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime, date

from models import db, Propiedad, Reserva, Ingreso, Contrato
from licencias_utils import puede_usar_modulo

simulador_bp = Blueprint('simulador', __name__, url_prefix='/simulador')


def _ids_propiedades_usuario():
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    return [p.id for p in propiedades]


def hay_contrato_solapado(propiedad_id, inicio, fin, contrato_id_excluir=None):
    q = Contrato.query.filter(
        Contrato.propiedad_id == propiedad_id,
        Contrato.estado == 'activo',
        Contrato.fecha_inicio <= fin,
        db.or_(
            Contrato.fecha_fin.is_(None),
            Contrato.fecha_fin >= inicio
        )
    )

    if contrato_id_excluir:
        q = q.filter(Contrato.id != contrato_id_excluir)

    return q.first() is not None


def hay_conflicto(propiedad_id, habitacion_id, inicio, fin):
    reservas = Reserva.query.filter(
        Reserva.propiedad_id == propiedad_id,
        Reserva.estado != 'cancelada'
    ).all()

    for r in reservas:
        reserva_inicio = getattr(r, 'fecha_inicio', None) or getattr(r, 'fecha_entrada', None)
        reserva_fin = getattr(r, 'fecha_fin', None) or getattr(r, 'fecha_salida', None)

        if not reserva_inicio or not reserva_fin:
            continue

        if habitacion_id and getattr(r, 'habitacion_id', None) != habitacion_id:
            continue

        if not (fin <= reserva_inicio or inicio >= reserva_fin):
            return True

    return False


def obtener_resumen_simulacion():
    ids_propiedades = _ids_propiedades_usuario()

    if not ids_propiedades:
        return {
            'total_reservas_demo': 0,
            'total_ingresos_demo': 0.0,
            'total_completas_demo': 0,
            'total_habitaciones_demo': 0,
        }

    reservas_demo = Reserva.query.filter(
        Reserva.propiedad_id.in_(ids_propiedades),
        Reserva.origen == 'simulador'
    ).all()

    total_ingresos_demo = (
        db.session.query(db.func.sum(Ingreso.cantidad))
        .join(Reserva, Ingreso.reserva_id == Reserva.id)
        .filter(
            Reserva.propiedad_id.in_(ids_propiedades),
            Reserva.origen == 'simulador'
        )
        .scalar()
    ) or 0

    total_completas_demo = 0
    total_habitaciones_demo = 0

    for r in reservas_demo:
        if getattr(r, 'habitacion_id', None):
            total_habitaciones_demo += 1
        else:
            total_completas_demo += 1

    return {
        'total_reservas_demo': len(reservas_demo),
        'total_ingresos_demo': round(float(total_ingresos_demo or 0), 2),
        'total_completas_demo': total_completas_demo,
        'total_habitaciones_demo': total_habitaciones_demo,
    }


@simulador_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if not puede_usar_modulo(current_user, "simulador"):
        flash("Tu plan no permite usar el simulador.", "warning")
        return redirect(url_for("main.dashboard"))

    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).order_by(Propiedad.nombre.asc()).all()
    canales = ['airbnb', 'booking', 'directo', 'vrbo']

    if request.method == 'POST':
        propiedad_id_raw = request.form.get('propiedad_id')
        fecha_inicio_raw = request.form.get('fecha_inicio')
        fecha_fin_raw = request.form.get('fecha_fin')
        precio_total_raw = request.form.get('precio_total')
        pagado_raw = request.form.get('pagado')
        habitacion_id_raw = request.form.get('habitacion_id')

        if not propiedad_id_raw or not fecha_inicio_raw or not fecha_fin_raw or not precio_total_raw:
            flash("Faltan datos obligatorios para crear la reserva de simulación.", "danger")
            resumen = obtener_resumen_simulacion()
            return render_template(
                "simulador/index.html",
                propiedades=propiedades,
                resumen=resumen,
                canales=canales
            )

        try:
            propiedad_id = int(propiedad_id_raw)
            habitacion_id = int(habitacion_id_raw) if habitacion_id_raw else None
            fecha_inicio = datetime.strptime(fecha_inicio_raw, '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(fecha_fin_raw, '%Y-%m-%d').date()
            precio_total = float(precio_total_raw)
            pagado = float(pagado_raw or 0)
        except (ValueError, TypeError):
            flash("Alguno de los datos introducidos no es válido.", "danger")
            return redirect(url_for('simulador.index'))

        noches = (fecha_fin - fecha_inicio).days

        if noches <= 0:
            flash("Fechas incorrectas.", "danger")
            return redirect(url_for('simulador.index'))

        propiedad = Propiedad.query.filter_by(id=propiedad_id, usuario_id=current_user.id).first()
        if not propiedad:
            flash("La propiedad seleccionada no es válida.", "danger")
            return redirect(url_for('simulador.index'))

        if hay_contrato_solapado(propiedad_id, fecha_inicio, fecha_fin):
            flash("La propiedad tiene un contrato de alquiler activo en esas fechas y no puede simularse en vacacional.", "danger")
            return redirect(url_for('simulador.index'))

        if hay_conflicto(propiedad_id, habitacion_id, fecha_inicio, fecha_fin):
            flash("Ya existe una reserva en esas fechas.", "danger")
            return redirect(url_for('simulador.index'))

        reserva_kwargs = {
            'propiedad_id': propiedad_id,
            'habitacion_id': habitacion_id,
            'precio_total': precio_total,
            'estado': 'confirmada',
            'origen': 'simulador'
        }

        # Compatibilidad con distintos nombres de fecha en tu modelo
        if hasattr(Reserva, 'fecha_inicio') and hasattr(Reserva, 'fecha_fin'):
            reserva_kwargs['fecha_inicio'] = fecha_inicio
            reserva_kwargs['fecha_fin'] = fecha_fin
        else:
            reserva_kwargs['fecha_entrada'] = fecha_inicio
            reserva_kwargs['fecha_salida'] = fecha_fin

        reserva = Reserva(**reserva_kwargs)

        db.session.add(reserva)
        db.session.commit()

        if pagado > 0:
            ingreso = Ingreso(
                propiedad_id=propiedad_id,
                reserva_id=reserva.id,
                fecha=date.today(),
                concepto=f"SIMULADOR reserva {reserva.id}",
                cantidad=pagado,
                moneda='EUR',
                metodo_pago='simulado'
            )
            db.session.add(ingreso)
            db.session.commit()

        flash(f"Reserva creada ({noches} noches).", "success")
        return redirect(url_for('simulador.index'))

    resumen = obtener_resumen_simulacion()

    return render_template(
        "simulador/index.html",
        propiedades=propiedades,
        resumen=resumen,
        canales=canales
    )


@simulador_bp.route('/limpiar', methods=['POST'])
@login_required
def limpiar():
    ids_propiedades = _ids_propiedades_usuario()

    if not ids_propiedades:
        flash("No hay simulaciones para limpiar.", "info")
        return redirect(url_for('simulador.index'))

    reservas = Reserva.query.filter(
        Reserva.propiedad_id.in_(ids_propiedades),
        Reserva.origen == 'simulador'
    ).all()

    for r in reservas:
        Ingreso.query.filter_by(reserva_id=r.id).delete()
        db.session.delete(r)

    db.session.commit()

    flash("Simulación eliminada correctamente.", "success")
    return redirect(url_for('simulador.index'))