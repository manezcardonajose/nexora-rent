from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import Reserva, Propiedad
from permisos import propiedades_visibles_query, tareas_visibles_query, usuario_tiene_permiso
from datetime import datetime

main_bp = Blueprint('main', __name__)


def _dashboard_ia_context(propiedades, propiedad_ids):
    """Carga la IA del dashboard sin romper nada si el módulo IA no está disponible."""
    contexto = {
        'disponible': False,
        'resumen': {},
        'alertas': {},
        'ranking': {},
        'prevision': {},
        'precios': {},
        'recomendaciones': [],
        'observaciones': [],
        'error': None,
    }

    if not propiedad_ids:
        return contexto

    try:
        from ia import (
            _resumen_general,
            _alertas_operativas,
            _ranking_financiero,
            _ocupacion_prevision,
            _precio_historico_propiedad,
            _recomendaciones_ia,
            _observaciones_ia,
        )

        resumen = _resumen_general(propiedad_ids)
        alertas = _alertas_operativas(propiedad_ids)
        ranking = _ranking_financiero(propiedad_ids)
        prevision = _ocupacion_prevision(propiedades, dias=30)

        precios = {}
        for propiedad in propiedades:
            try:
                precios[propiedad.id] = _precio_historico_propiedad(propiedad.id)
            except Exception:
                precios[propiedad.id] = {}

        recomendaciones = _recomendaciones_ia(resumen, alertas, prevision, precios, ranking)
        observaciones = _observaciones_ia(resumen, alertas, ranking, prevision, precios)

        contexto.update({
            'disponible': True,
            'resumen': resumen or {},
            'alertas': alertas or {},
            'ranking': ranking or {},
            'prevision': prevision or {},
            'precios': precios or {},
            'recomendaciones': recomendaciones or [],
            'observaciones': observaciones or [],
        })
        return contexto
    except Exception as exc:
        contexto['error'] = str(exc)
        return contexto


@main_bp.route('/')
def index():
    return render_template('index.html')


@main_bp.route('/dashboard')
@login_required
def dashboard():
    propiedades = propiedades_visibles_query().all()
    propiedad_ids = [p.id for p in propiedades]

    num_propiedades = len(propiedades)
    hoy = datetime.today().date()

    tareas_pendientes = tareas_visibles_query().filter_by(completada=False).count()

    reservas_hoy = 0
    proximas_reservas = []

    if propiedad_ids and (
        current_user.es_admin()
        or current_user.es_principal
        or usuario_tiene_permiso('puede_gestionar_reservas')
        or usuario_tiene_permiso('puede_ver_informes')
    ):
        reservas_hoy = Reserva.query.filter(
            Reserva.propiedad_id.in_(propiedad_ids),
            Reserva.fecha_entrada <= hoy,
            Reserva.fecha_salida >= hoy,
            Reserva.estado != 'cancelada'
        ).count()

        proximas_reservas = Reserva.query.filter(
            Reserva.propiedad_id.in_(propiedad_ids),
            Reserva.fecha_entrada >= hoy,
            Reserva.estado != 'cancelada'
        ).order_by(Reserva.fecha_entrada).limit(5).all()

    ia_dashboard = _dashboard_ia_context(propiedades, propiedad_ids)

    return render_template(
        'dashboard.html',
        num_propiedades=num_propiedades,
        reservas_hoy=reservas_hoy,
        tareas_pendientes=tareas_pendientes,
        proximas_reservas=proximas_reservas,
        ia_dashboard=ia_dashboard
    )


@main_bp.route('/ayuda')
def ayuda():
    return render_template('ayuda/index.html')


@main_bp.route('/politica-privacidad')
def politica_privacidad():
    return render_template('legal/politica.html')
