from flask import Blueprint, render_template, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import func

from models import db, Ingreso, Gasto, Propiedad, Reserva, Contrato
from licencias_utils import puede_usar_modulo
from permisos import propiedades_visibles_query, usuario_tiene_permiso

finanzas_bp = Blueprint('finanzas', __name__, url_prefix='/finanzas')


def _propiedades_usuario():
    return propiedades_visibles_query().order_by(Propiedad.nombre.asc()).all()


def calcular_rentabilidad_reserva(reserva):
    """
    Calcula la rentabilidad de una reserva vacacional sin romper la lógica actual.

    Criterios que mantiene:
    - ingresos directos imputados a la reserva
    - gastos directos imputados a la reserva
    - gastos generales de propiedad sin reserva imputados por prorrateo
    - exclusión lógica de propiedades en larga duración cuando exista contrato activo

    Mejora añadida:
    - unifica el criterio para dashboard e informes
    - usa prorrateo por noches como criterio principal
    - incorpora fallback por número de reservas para no dejar el coste estimado en 0
      cuando no hay noches acumuladas válidas, pero sí reservas históricas
    - protege frente a None y fechas incompletas
    """
    if not reserva:
        return None

    contrato_activo = Contrato.query.filter_by(
        propiedad_id=reserva.propiedad_id,
        estado='activo'
    ).first()

    ingresos_reserva = db.session.query(func.sum(Ingreso.cantidad)).filter(
        Ingreso.reserva_id == reserva.id
    ).scalar() or 0

    gastos_directos_reserva = db.session.query(func.sum(Gasto.cantidad)).filter(
        Gasto.reserva_id == reserva.id
    ).scalar() or 0

    total_comisiones = db.session.query(func.sum(Gasto.cantidad)).filter(
        Gasto.reserva_id == reserva.id,
        func.lower(func.trim(Gasto.categoria)) == 'comisiones'
    ).scalar() or 0

    noches = 0
    if reserva.fecha_entrada and reserva.fecha_salida:
        noches = max((reserva.fecha_salida - reserva.fecha_entrada).days, 0)

    gastos_propiedad_no_imputados = db.session.query(func.sum(Gasto.cantidad)).filter(
        Gasto.propiedad_id == reserva.propiedad_id,
        Gasto.reserva_id.is_(None)
    ).scalar() or 0

    total_noches_propiedad = db.session.query(
        func.sum(func.julianday(Reserva.fecha_salida) - func.julianday(Reserva.fecha_entrada))
    ).filter(
        Reserva.propiedad_id == reserva.propiedad_id,
        Reserva.fecha_entrada.isnot(None),
        Reserva.fecha_salida.isnot(None),
        Reserva.estado != 'cancelada'
    ).scalar() or 0

    total_reservas_propiedad = Reserva.query.filter(
        Reserva.propiedad_id == reserva.propiedad_id,
        Reserva.estado != 'cancelada'
    ).count()

    gasto_prorrateado = 0.0
    criterio_prorrateo = 'sin_prorrateo'

    if float(gastos_propiedad_no_imputados or 0) > 0:
        if float(total_noches_propiedad or 0) > 0 and noches > 0:
            coste_medio_noche = float(gastos_propiedad_no_imputados) / float(total_noches_propiedad)
            gasto_prorrateado = float(noches) * float(coste_medio_noche)
            criterio_prorrateo = 'noches'
        elif total_reservas_propiedad > 0:
            gasto_prorrateado = float(gastos_propiedad_no_imputados) / float(total_reservas_propiedad)
            criterio_prorrateo = 'reservas'

    gasto_total = float(gastos_directos_reserva or 0) + float(gasto_prorrateado or 0)
    beneficio_reserva = float(ingresos_reserva or 0) - float(gasto_total or 0)

    primer_huesped = reserva.huespedes.first()
    if primer_huesped:
        nombre_huesped = f"{primer_huesped.nombre or ''} {primer_huesped.apellidos or ''}".strip()
    else:
        nombre_huesped = 'Sin huésped'

    return {
        'reserva': reserva,
        'propiedad': reserva.propiedad,
        'huesped': nombre_huesped,
        'canal': getattr(reserva, 'canal', None) or getattr(reserva, 'origen', None) or '',
        'noches': noches,
        'ingresos': float(ingresos_reserva or 0),
        'gastos_directos': float(gastos_directos_reserva or 0),
        'gastos_reserva': float(gastos_directos_reserva or 0),
        'comisiones': float(total_comisiones or 0),
        'gastos_propiedad': float(gastos_propiedad_no_imputados or 0),
        'gasto_prorrateado': float(gasto_prorrateado or 0),
        'gasto_propiedad_imputado': float(gasto_prorrateado or 0),
        'gasto_total': float(gasto_total or 0),
        'gasto_estimado': float(gasto_total or 0),
        'beneficio': float(beneficio_reserva or 0),
        'beneficio_estimado': float(beneficio_reserva or 0),
        'criterio_prorrateo': criterio_prorrateo,
        'es_larga_duracion': bool(contrato_activo),
    }


def _recomendacion_propiedad(propiedad_id):
    """
    Comparación simple entre explotación vacacional y larga duración.
    No sustituye a los informes detallados, pero sirve como orientación visual.
    """

    ingresos_vv = db.session.query(func.sum(Ingreso.cantidad)).join(
        Reserva, Ingreso.reserva_id == Reserva.id
    ).filter(
        Reserva.propiedad_id == propiedad_id
    ).scalar() or 0

    renta_ld = db.session.query(func.sum(Contrato.renta_mensual)).filter(
        Contrato.propiedad_id == propiedad_id,
        Contrato.estado == 'activo'
    ).scalar() or 0

    gastos = db.session.query(func.sum(Gasto.cantidad)).filter(
        Gasto.propiedad_id == propiedad_id
    ).scalar() or 0

    beneficio_vv = float(ingresos_vv or 0) - float(gastos or 0)
    beneficio_ld = float(renta_ld or 0) - float(gastos or 0)

    if beneficio_vv > beneficio_ld:
        return "VACACIONAL"
    elif beneficio_ld > beneficio_vv:
        return "LARGA DURACIÓN"
    return "INDIFERENTE"


@finanzas_bp.route('/')
@login_required
def dashboard():
    if not puede_usar_modulo(current_user, "informes"):
        flash("Tu plan no permite acceder al panel financiero.", "warning")
        return redirect(url_for("main.dashboard"))

    if not usuario_tiene_permiso('puede_gestionar_finanzas'):
        flash("No tienes permisos para acceder al panel financiero.", "danger")
        return redirect(url_for("main.dashboard"))

    propiedades = _propiedades_usuario()
    propiedad_ids = [p.id for p in propiedades]

    if not propiedad_ids:
        return render_template(
            'finanzas/dashboard.html',
            propiedades_resumen=[],
            resumen_mensual=[],
            chart_labels=[],
            chart_ingresos=[],
            chart_gastos=[],
            chart_beneficio=[],
            ultimos_ingresos=[],
            ultimos_gastos=[],
            rentabilidad_reservas=[],
            total_ingresos=0,
            total_gastos=0,
            beneficio_neto=0,
            total_beneficio=0
        )

    total_ingresos = db.session.query(func.sum(Ingreso.cantidad)).filter(
        Ingreso.propiedad_id.in_(propiedad_ids)
    ).scalar() or 0

    total_gastos = db.session.query(func.sum(Gasto.cantidad)).filter(
        Gasto.propiedad_id.in_(propiedad_ids)
    ).scalar() or 0

    beneficio_neto = float(total_ingresos or 0) - float(total_gastos or 0)

    # =========================
    # RESULTADO POR PROPIEDAD
    # =========================
    propiedades_resumen = []
    for p in propiedades:
        ingresos_prop = db.session.query(func.sum(Ingreso.cantidad)).filter(
            Ingreso.propiedad_id == p.id
        ).scalar() or 0

        gastos_prop = db.session.query(func.sum(Gasto.cantidad)).filter(
            Gasto.propiedad_id == p.id
        ).scalar() or 0

        propiedades_resumen.append({
            'propiedad': p,
            'ingresos': float(ingresos_prop or 0),
            'gastos': float(gastos_prop or 0),
            'beneficio': float(ingresos_prop or 0) - float(gastos_prop or 0),
            'recomendacion': _recomendacion_propiedad(p.id)
        })

    propiedades_resumen.sort(key=lambda x: x['beneficio'], reverse=True)

    # =========================
    # RESUMEN MENSUAL
    # =========================
    ingresos_mes = db.session.query(
        func.strftime('%Y-%m', Ingreso.fecha).label('mes'),
        func.sum(Ingreso.cantidad).label('total_ingresos')
    ).filter(
        Ingreso.propiedad_id.in_(propiedad_ids)
    ).group_by('mes').all()

    gastos_mes = db.session.query(
        func.strftime('%Y-%m', Gasto.fecha).label('mes'),
        func.sum(Gasto.cantidad).label('total_gastos')
    ).filter(
        Gasto.propiedad_id.in_(propiedad_ids)
    ).group_by('mes').all()

    mapa_meses = {}

    for fila in ingresos_mes:
        mapa_meses[fila.mes] = {
            'mes': fila.mes,
            'ingresos': float(fila.total_ingresos or 0),
            'gastos': 0.0
        }

    for fila in gastos_mes:
        if fila.mes not in mapa_meses:
            mapa_meses[fila.mes] = {
                'mes': fila.mes,
                'ingresos': 0.0,
                'gastos': float(fila.total_gastos or 0)
            }
        else:
            mapa_meses[fila.mes]['gastos'] = float(fila.total_gastos or 0)

    resumen_mensual = []
    for mes in sorted(mapa_meses.keys()):
        item = mapa_meses[mes]
        item['beneficio'] = float(item['ingresos']) - float(item['gastos'])
        resumen_mensual.append(item)

    chart_labels = [item['mes'] for item in resumen_mensual]
    chart_ingresos = [item['ingresos'] for item in resumen_mensual]
    chart_gastos = [item['gastos'] for item in resumen_mensual]
    chart_beneficio = [item['beneficio'] for item in resumen_mensual]

    # =========================
    # ÚLTIMOS MOVIMIENTOS
    # =========================
    ultimos_ingresos = Ingreso.query.filter(
        Ingreso.propiedad_id.in_(propiedad_ids)
    ).order_by(Ingreso.fecha.desc(), Ingreso.id.desc()).limit(5).all()

    ultimos_gastos = Gasto.query.filter(
        Gasto.propiedad_id.in_(propiedad_ids)
    ).order_by(Gasto.fecha.desc(), Gasto.id.desc()).limit(5).all()

    # =========================
    # RENTABILIDAD POR RESERVA
    # =========================
    rentabilidad_reservas = []

    reservas = Reserva.query.filter(
        Reserva.propiedad_id.in_(propiedad_ids)
    ).order_by(Reserva.fecha_entrada.desc()).all()

    for reserva in reservas:
        calculo = calcular_rentabilidad_reserva(reserva)
        if not calculo or calculo['es_larga_duracion']:
            continue

        if (
            calculo['ingresos'] > 0
            or calculo['gastos_directos'] > 0
            or calculo['gasto_prorrateado'] > 0
        ):
            rentabilidad_reservas.append(calculo)

    rentabilidad_reservas.sort(key=lambda x: x['beneficio_estimado'], reverse=True)
    rentabilidad_reservas = rentabilidad_reservas[:8]

    return render_template(
        'finanzas/dashboard.html',
        propiedades_resumen=propiedades_resumen,
        resumen_mensual=list(reversed(resumen_mensual)),
        chart_labels=chart_labels,
        chart_ingresos=chart_ingresos,
        chart_gastos=chart_gastos,
        chart_beneficio=chart_beneficio,
        ultimos_ingresos=ultimos_ingresos,
        ultimos_gastos=ultimos_gastos,
        rentabilidad_reservas=rentabilidad_reservas,
        total_ingresos=float(total_ingresos or 0),
        total_gastos=float(total_gastos or 0),
        beneficio_neto=float(beneficio_neto or 0),
        total_beneficio=float(beneficio_neto or 0)
    )
