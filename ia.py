from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from models import Contrato, Gasto, Ingreso, Propiedad, Reserva, Tarea

try:
    from permisos import propiedades_visibles_query
except Exception:
    propiedades_visibles_query = None


ia_bp = Blueprint('ia', __name__, url_prefix='/ia', template_folder='templates')


# ============================================================
# Utilidades base
# ============================================================

def _safe_float(value, default=0.0):
    try:
        return float(value or 0)
    except Exception:
        return default


def _safe_days(start_date, end_date):
    if not start_date or not end_date:
        return 0
    try:
        return max((end_date - start_date).days, 0)
    except Exception:
        return 0


def _clamp(value, min_value=0.0, max_value=100.0):
    return max(min_value, min(max_value, value))


def _nivel_confianza(total_registros):
    if total_registros >= 20:
        return 'alta'
    if total_registros >= 6:
        return 'media'
    return 'baja'


def _calcular_tendencia(actual, anterior, umbral=0.10):
    actual = _safe_float(actual)
    anterior = _safe_float(anterior)
    if anterior <= 0:
        if actual > 0:
            return 'subiendo'
        return 'estable'
    variacion = (actual - anterior) / anterior
    if variacion > umbral:
        return 'subiendo'
    if variacion < -umbral:
        return 'bajando'
    return 'estable'


def _resumen_tendencia_texto(tendencia):
    mapping = {
        'subiendo': 'en subida',
        'bajando': 'a la baja',
        'estable': 'estable',
    }
    return mapping.get(tendencia, 'estable')


def _query_propiedades_visibles():
    if propiedades_visibles_query is not None:
        try:
            return propiedades_visibles_query()
        except Exception:
            pass

    if not getattr(current_user, 'is_authenticated', False):
        return Propiedad.query.filter(Propiedad.id == 0)

    try:
        if current_user.es_admin() or getattr(current_user, 'es_principal', False):
            return Propiedad.query
    except Exception:
        pass

    if getattr(current_user, 'cuenta_id', None):
        return Propiedad.query.filter(
            (Propiedad.cuenta_id == current_user.cuenta_id) |
            (Propiedad.usuario_id == current_user.id)
        )

    return Propiedad.query.filter_by(usuario_id=current_user.id)


def _ids_propiedades_usuario():
    try:
        return [p.id for p in _query_propiedades_visibles().all()]
    except Exception:
        return []


def _propiedades_usuario():
    try:
        return _query_propiedades_visibles().order_by(Propiedad.nombre.asc()).all()
    except Exception:
        return []


def _es_propiedad_larga_duracion(propiedad_id):
    hoy = date.today()
    contrato = Contrato.query.filter(
        Contrato.propiedad_id == propiedad_id,
        Contrato.estado == 'activo',
        Contrato.fecha_inicio <= hoy,
        ((Contrato.fecha_fin.is_(None)) | (Contrato.fecha_fin >= hoy))
    ).first()
    return contrato is not None


def _reservas_visibles(ids_propiedades):
    if not ids_propiedades:
        return []
    return Reserva.query.filter(Reserva.propiedad_id.in_(ids_propiedades)).all()


# ============================================================
# Cálculo de rentabilidad y métricas de reservas
# ============================================================

def _rentabilidad_reserva(reserva, cache_propiedad=None, cache_reservas_propiedad=None):
    ingresos_directos = sum(_safe_float(i.cantidad) for i in reserva.ingresos.all())

    gastos_directos = Gasto.query.filter_by(reserva_id=reserva.id).all()
    gasto_directo_total = sum(_safe_float(g.cantidad) for g in gastos_directos)

    noches_reserva = _safe_days(reserva.fecha_entrada, reserva.fecha_salida)
    gasto_prorrateado = 0.0

    if reserva.propiedad_id:
        gastos_generales = Gasto.query.filter(
            Gasto.propiedad_id == reserva.propiedad_id,
            Gasto.reserva_id.is_(None)
        ).all()
        total_gastos_generales = sum(_safe_float(g.cantidad) for g in gastos_generales)

        if total_gastos_generales > 0:
            if cache_reservas_propiedad is None:
                reservas_propiedad = Reserva.query.filter_by(propiedad_id=reserva.propiedad_id).all()
            else:
                reservas_propiedad = cache_reservas_propiedad.get(reserva.propiedad_id, [])

            total_noches = sum(_safe_days(r.fecha_entrada, r.fecha_salida) for r in reservas_propiedad)
            total_reservas = len(reservas_propiedad)

            if total_noches > 0 and noches_reserva > 0:
                gasto_prorrateado = total_gastos_generales * (noches_reserva / total_noches)
            elif total_reservas > 0:
                gasto_prorrateado = total_gastos_generales / total_reservas

    gasto_estimado = gasto_directo_total + gasto_prorrateado
    beneficio = ingresos_directos - gasto_estimado
    margen = (beneficio / ingresos_directos * 100) if ingresos_directos > 0 else 0.0

    return {
        'reserva': reserva,
        'reserva_id': reserva.id,
        'propiedad_id': reserva.propiedad_id,
        'propiedad_nombre': getattr(reserva.propiedad, 'nombre', f'Propiedad {reserva.propiedad_id}'),
        'fecha_entrada': reserva.fecha_entrada,
        'fecha_salida': reserva.fecha_salida,
        'noches': noches_reserva,
        'ingresos': round(ingresos_directos, 2),
        'gasto_directo': round(gasto_directo_total, 2),
        'gasto_prorrateado': round(gasto_prorrateado, 2),
        'gasto_estimado': round(gasto_estimado, 2),
        'beneficio': round(beneficio, 2),
        'margen': round(margen, 2),
        'tiene_ingreso': ingresos_directos > 0,
        'tiene_gasto': gasto_estimado > 0,
    }


def _metricas_reservas(ids_propiedades):
    reservas = _reservas_visibles(ids_propiedades)
    cache_reservas_propiedad = defaultdict(list)
    for reserva in reservas:
        cache_reservas_propiedad[reserva.propiedad_id].append(reserva)

    metricas = []
    for reserva in reservas:
        metricas.append(_rentabilidad_reserva(reserva, cache_reservas_propiedad=cache_reservas_propiedad))
    return metricas


# ============================================================
# Resumen general
# ============================================================

def _resumen_general(ids_propiedades):
    hoy = date.today()

    if not ids_propiedades:
        return {
            'propiedades': 0,
            'reservas_activas': 0,
            'entradas_manana': 0,
            'salidas_hoy': 0,
            'tareas_pendientes': 0,
            'ingresos_mes': 0.0,
            'gastos_mes': 0.0,
            'beneficio_mes': 0.0,
        }

    inicio_mes = hoy.replace(day=1)
    if hoy.month == 12:
        fin_mes = date(hoy.year + 1, 1, 1)
    else:
        fin_mes = date(hoy.year, hoy.month + 1, 1)

    reservas_activas = Reserva.query.filter(
        Reserva.propiedad_id.in_(ids_propiedades),
        Reserva.fecha_entrada <= hoy,
        Reserva.fecha_salida >= hoy
    ).count()

    entradas_manana = Reserva.query.filter(
        Reserva.propiedad_id.in_(ids_propiedades),
        Reserva.fecha_entrada == (hoy + timedelta(days=1))
    ).count()

    salidas_hoy = Reserva.query.filter(
        Reserva.propiedad_id.in_(ids_propiedades),
        Reserva.fecha_salida == hoy
    ).count()

    tareas_pendientes = Tarea.query.filter(
        Tarea.propiedad_id.in_(ids_propiedades),
        Tarea.completada.is_(False)
    ).count()

    ingresos_mes = sum(
        _safe_float(i.cantidad)
        for i in Ingreso.query.filter(
            Ingreso.propiedad_id.in_(ids_propiedades),
            Ingreso.fecha >= inicio_mes,
            Ingreso.fecha < fin_mes
        ).all()
    )

    gastos_mes = sum(
        _safe_float(g.cantidad)
        for g in Gasto.query.filter(
            Gasto.propiedad_id.in_(ids_propiedades),
            Gasto.fecha >= inicio_mes,
            Gasto.fecha < fin_mes
        ).all()
    )

    return {
        'propiedades': len(ids_propiedades),
        'reservas_activas': reservas_activas,
        'entradas_manana': entradas_manana,
        'salidas_hoy': salidas_hoy,
        'tareas_pendientes': tareas_pendientes,
        'ingresos_mes': round(ingresos_mes, 2),
        'gastos_mes': round(gastos_mes, 2),
        'beneficio_mes': round(ingresos_mes - gastos_mes, 2),
    }


# ============================================================
# Alertas
# ============================================================

def _alertas(ids_propiedades, metricas_reservas):
    hoy = date.today()

    tareas_vencidas = Tarea.query.filter(
        Tarea.propiedad_id.in_(ids_propiedades),
        Tarea.completada.is_(False),
        Tarea.fecha_limite.isnot(None),
        Tarea.fecha_limite < hoy
    ).count() if ids_propiedades else 0

    contratos_vencer = Contrato.query.filter(
        Contrato.propiedad_id.in_(ids_propiedades),
        Contrato.fecha_fin.isnot(None),
        Contrato.fecha_fin >= hoy,
        Contrato.fecha_fin <= (hoy + timedelta(days=30))
    ).count() if ids_propiedades else 0

    ingreso_sin_gasto_items = [m for m in metricas_reservas if m['ingresos'] > 0 and m['gasto_estimado'] <= 0]
    margen_bajo_items = [m for m in metricas_reservas if m['ingresos'] > 0 and m['margen'] < 15]

    inicio_mes = hoy.replace(day=1)
    propiedades_mes = _propiedades_usuario()
    gastos_mes_por_propiedad = []
    historico_por_propiedad = []
    for prop in propiedades_mes:
        gasto_mes = sum(
            _safe_float(g.cantidad)
            for g in Gasto.query.filter(
                Gasto.propiedad_id == prop.id,
                Gasto.fecha >= inicio_mes,
                Gasto.fecha <= hoy
            ).all()
        )
        gastos_mes_por_propiedad.append((prop, gasto_mes))

        meses_previos = []
        for back in range(1, 4):
            ref = (inicio_mes - timedelta(days=back * 30))
            inicio_ref = ref.replace(day=1)
            if inicio_ref.month == 12:
                fin_ref = date(inicio_ref.year + 1, 1, 1)
            else:
                fin_ref = date(inicio_ref.year, inicio_ref.month + 1, 1)
            total_ref = sum(
                _safe_float(g.cantidad)
                for g in Gasto.query.filter(
                    Gasto.propiedad_id == prop.id,
                    Gasto.fecha >= inicio_ref,
                    Gasto.fecha < fin_ref
                ).all()
            )
            meses_previos.append(total_ref)
        media_prev = mean(meses_previos) if meses_previos and any(x > 0 for x in meses_previos) else 0.0
        historico_por_propiedad.append((prop, gasto_mes, media_prev))

    gasto_alto_items = []
    for prop, gasto_mes, media_prev in historico_por_propiedad:
        if gasto_mes > 0 and media_prev > 0 and gasto_mes >= media_prev * 1.35:
            gasto_alto_items.append({
                'propiedad': prop.nombre,
                'gasto_mes': round(gasto_mes, 2),
                'media_prev': round(media_prev, 2),
            })

    total_alertas = len(ingreso_sin_gasto_items) + len(margen_bajo_items) + tareas_vencidas + contratos_vencer + len(gasto_alto_items)

    principal = None
    if tareas_vencidas:
        principal = f'Hay {tareas_vencidas} tareas vencidas pendientes de revisión.'
    elif len(ingreso_sin_gasto_items):
        principal = f'Hay {len(ingreso_sin_gasto_items)} reservas con ingreso imputado y sin gasto asociado.'
    elif len(margen_bajo_items):
        principal = f'Hay {len(margen_bajo_items)} reservas con margen bajo.'
    elif contratos_vencer:
        principal = f'Hay {contratos_vencer} contratos próximos a vencer en 30 días.'
    elif len(gasto_alto_items):
        principal = f'Hay {len(gasto_alto_items)} propiedades con gasto alto este mes.'

    items = []
    if tareas_vencidas:
        items.append({'tipo': 'tareas_vencidas', 'texto': f'{tareas_vencidas} tareas vencidas'})
    if ingreso_sin_gasto_items:
        items.append({'tipo': 'ingreso_sin_gasto', 'texto': f'{len(ingreso_sin_gasto_items)} reservas con ingreso y sin gasto'})
    if margen_bajo_items:
        items.append({'tipo': 'margen_bajo', 'texto': f'{len(margen_bajo_items)} reservas con margen bajo'})
    if contratos_vencer:
        items.append({'tipo': 'contratos_vencer', 'texto': f'{contratos_vencer} contratos próximos a vencer'})
    if gasto_alto_items:
        items.append({'tipo': 'gasto_alto', 'texto': f'{len(gasto_alto_items)} propiedades con gasto alto'})

    return {
        'conteos': {
            'ingreso_sin_gasto': len(ingreso_sin_gasto_items),
            'margen_bajo': len(margen_bajo_items),
            'tareas_vencidas': tareas_vencidas,
            'contratos_vencer': contratos_vencer,
            'gasto_alto': len(gasto_alto_items),
            'total': total_alertas,
        },
        'principal': principal,
        'items': items,
        'detalles': {
            'ingreso_sin_gasto': ingreso_sin_gasto_items[:10],
            'margen_bajo': margen_bajo_items[:10],
            'gasto_alto': gasto_alto_items[:10],
        },
    }


# ============================================================
# Ranking
# ============================================================

def _ranking(ids_propiedades, metricas_reservas):
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)

    propiedades_beneficio = []
    propiedades_gasto = []

    for prop in _propiedades_usuario():
        beneficio_prop = sum(m['beneficio'] for m in metricas_reservas if m['propiedad_id'] == prop.id)
        gastos_prop_mes = sum(
            _safe_float(g.cantidad)
            for g in Gasto.query.filter(
                Gasto.propiedad_id == prop.id,
                Gasto.fecha >= inicio_mes,
                Gasto.fecha <= hoy
            ).all()
        )
        ingresos_prop_mes = sum(
            _safe_float(i.cantidad)
            for i in Ingreso.query.filter(
                Ingreso.propiedad_id == prop.id,
                Ingreso.fecha >= inicio_mes,
                Ingreso.fecha <= hoy
            ).all()
        )

        propiedades_beneficio.append({
            'propiedad': prop.nombre,
            'beneficio': round(beneficio_prop, 2),
            'ingresos_mes': round(ingresos_prop_mes, 2),
            'gastos_mes': round(gastos_prop_mes, 2),
        })
        propiedades_gasto.append({
            'propiedad': prop.nombre,
            'gastos_mes': round(gastos_prop_mes, 2),
            'ingresos_mes': round(ingresos_prop_mes, 2),
        })

    propiedades_beneficio.sort(key=lambda x: x['beneficio'], reverse=True)
    propiedades_gasto.sort(key=lambda x: x['gastos_mes'], reverse=True)

    reservas_ordenadas = sorted(metricas_reservas, key=lambda x: x['beneficio'], reverse=True)

    return {
        'propiedades_beneficio': propiedades_beneficio[:10],
        'propiedades_gasto': propiedades_gasto[:10],
        'reservas_top': reservas_ordenadas[:10],
        'reservas_peor': list(reversed(reservas_ordenadas[-10:])) if reservas_ordenadas else [],
    }


# ============================================================
# Ocupación y sugerencias de precio
# ============================================================

def _ocupacion_y_precios(ids_propiedades):
    hoy = date.today()
    horizonte = 30
    fin = hoy + timedelta(days=horizonte)

    propiedades_data = []
    ocupaciones_globales = []

    for prop in _propiedades_usuario():
        reservas_futuras = Reserva.query.filter(
            Reserva.propiedad_id == prop.id,
            Reserva.fecha_salida > hoy,
            Reserva.fecha_entrada < fin
        ).all()

        dias_ocupados = 0
        for reserva in reservas_futuras:
            inicio_solape = max(reserva.fecha_entrada, hoy)
            fin_solape = min(reserva.fecha_salida, fin)
            dias_ocupados += _safe_days(inicio_solape, fin_solape)

        porcentaje = _clamp((dias_ocupados / horizonte) * 100 if horizonte else 0)
        ocupaciones_globales.append(porcentaje)

        historicas = Reserva.query.filter(
            Reserva.propiedad_id == prop.id,
            Reserva.fecha_salida < hoy
        ).all()

        tarifas_historicas = []
        for res in historicas:
            noches = _safe_days(res.fecha_entrada, res.fecha_salida)
            if noches > 0 and _safe_float(res.precio_total) > 0:
                tarifas_historicas.append(_safe_float(res.precio_total) / noches)

        tarifa_media = mean(tarifas_historicas) if tarifas_historicas else _safe_float(prop.precio_noche)
        tarifa_actual = _safe_float(prop.precio_noche)
        diferencia_pct = ((tarifa_actual - tarifa_media) / tarifa_media * 100) if tarifa_media > 0 else 0.0

        if tarifa_media <= 0:
            sugerencia = tarifa_actual
            observacion = 'Sin base suficiente para sugerencia sólida.'
        elif tarifa_actual < tarifa_media * 0.90:
            sugerencia = tarifa_media
            observacion = 'Precio actual por debajo del histórico propio. Conviene revisar al alza.'
        elif tarifa_actual > tarifa_media * 1.15:
            sugerencia = tarifa_media
            observacion = 'Precio actual por encima del histórico propio. Conviene revisar competitividad interna.'
        else:
            sugerencia = tarifa_actual
            observacion = 'Precio alineado con el histórico propio.'

        confianza = _nivel_confianza(len(tarifas_historicas))

        props_huecos = []
        cursor = hoy
        reservas_ordenadas = sorted(reservas_futuras, key=lambda r: r.fecha_entrada)
        for res in reservas_ordenadas:
            if cursor < res.fecha_entrada:
                gap = _safe_days(cursor, min(res.fecha_entrada, fin))
                if gap >= 3:
                    props_huecos.append({
                        'desde': cursor,
                        'hasta': min(res.fecha_entrada, fin),
                        'dias': gap,
                    })
            cursor = max(cursor, res.fecha_salida)
        if cursor < fin:
            gap = _safe_days(cursor, fin)
            if gap >= 3:
                props_huecos.append({'desde': cursor, 'hasta': fin, 'dias': gap})

        propiedades_data.append({
            'propiedad': prop.nombre,
            'propiedad_id': prop.id,
            'porcentaje_mes': round(porcentaje, 2),
            'porcentaje_total': round(porcentaje, 2),
            'dias_ocupados': dias_ocupados,
            'dias_periodo': horizonte,
            'reservas_futuras': len(reservas_futuras),
            'confianza': confianza,
            'tendencia': 'subiendo' if len(reservas_futuras) >= 3 else 'estable',
            'explicacion': f'Ocupación prevista sobre {horizonte} días basada en {len(reservas_futuras)} reservas futuras.',
            'precio_actual': round(tarifa_actual, 2),
            'precio_historico': round(tarifa_media, 2),
            'precio_sugerido': round(sugerencia, 2),
            'diferencia_pct': round(diferencia_pct, 2),
            'observacion_precio': observacion,
            'huecos': props_huecos[:5],
        })

    promedio_ocupacion = round(mean(ocupaciones_globales), 2) if ocupaciones_globales else 0.0
    confianza_global = _nivel_confianza(len(propiedades_data))

    hace_30 = hoy - timedelta(days=30)
    hace_60 = hoy - timedelta(days=60)
    actual_reservas = Reserva.query.filter(
        Reserva.propiedad_id.in_(ids_propiedades),
        Reserva.fecha_creacion >= hace_30
    ).count() if ids_propiedades else 0
    anterior_reservas = Reserva.query.filter(
        Reserva.propiedad_id.in_(ids_propiedades),
        Reserva.fecha_creacion >= hace_60,
        Reserva.fecha_creacion < hace_30
    ).count() if ids_propiedades else 0

    tendencia_global = _calcular_tendencia(actual_reservas, anterior_reservas)

    return {
        'global': {
            'porcentaje_mes': promedio_ocupacion,
            'porcentaje_total': promedio_ocupacion,
            'confianza': confianza_global,
            'tendencia': tendencia_global,
            'explicacion': f'Ocupación media prevista { _resumen_tendencia_texto(tendencia_global) } en los próximos {horizonte} días.',
        },
        'propiedades': propiedades_data,
    }


# ============================================================
# Rentabilidad global / explicada
# ============================================================

def _rentabilidad(ids_propiedades, metricas_reservas):
    hoy = date.today()
    inicio_actual = hoy - timedelta(days=30)
    inicio_anterior = hoy - timedelta(days=60)

    ingresos_actual = sum(
        _safe_float(i.cantidad)
        for i in Ingreso.query.filter(
            Ingreso.propiedad_id.in_(ids_propiedades),
            Ingreso.fecha >= inicio_actual,
            Ingreso.fecha <= hoy
        ).all()
    ) if ids_propiedades else 0.0

    gastos_actual = sum(
        _safe_float(g.cantidad)
        for g in Gasto.query.filter(
            Gasto.propiedad_id.in_(ids_propiedades),
            Gasto.fecha >= inicio_actual,
            Gasto.fecha <= hoy
        ).all()
    ) if ids_propiedades else 0.0

    ingresos_anterior = sum(
        _safe_float(i.cantidad)
        for i in Ingreso.query.filter(
            Ingreso.propiedad_id.in_(ids_propiedades),
            Ingreso.fecha >= inicio_anterior,
            Ingreso.fecha < inicio_actual
        ).all()
    ) if ids_propiedades else 0.0

    beneficio = ingresos_actual - gastos_actual
    margen = (beneficio / ingresos_actual * 100) if ingresos_actual > 0 else 0.0
    tendencia = _calcular_tendencia(ingresos_actual, ingresos_anterior)
    confianza = _nivel_confianza(len(metricas_reservas))

    if beneficio < 0:
        explicacion = 'La rentabilidad es negativa: los gastos recientes superan a los ingresos del periodo.'
    elif margen < 15:
        explicacion = 'La rentabilidad es débil: hay margen bajo respecto al volumen de ingresos.'
    elif gastos_actual > ingresos_actual * 0.70:
        explicacion = 'La rentabilidad está presionada por un peso alto de los gastos sobre el ingreso.'
    else:
        explicacion = 'La rentabilidad se mantiene razonable con el nivel actual de ingresos y gastos.'

    return {
        'ingresos': round(ingresos_actual, 2),
        'gastos': round(gastos_actual, 2),
        'beneficio': round(beneficio, 2),
        'margen': round(margen, 2),
        'tendencia': tendencia,
        'confianza': confianza,
        'explicacion': explicacion,
    }


# ============================================================
# Recomendaciones IA
# ============================================================

def _recomendaciones(resumen, alertas, ocupacion, rentabilidad):
    recomendaciones = []

    if alertas['conteos']['tareas_vencidas'] > 0:
        recomendaciones.append('Revisar y cerrar tareas vencidas para evitar arrastre operativo.')

    if alertas['conteos']['ingreso_sin_gasto'] > 0:
        recomendaciones.append('Hay reservas con ingreso sin coste imputado. Conviene revisar gastos asociados.')

    if ocupacion['global']['porcentaje_mes'] < 40:
        recomendaciones.append('La ocupación prevista es baja. Conviene revisar precio interno y disponibilidad próxima.')

    if rentabilidad['beneficio'] < 0:
        recomendaciones.append('El beneficio del periodo es negativo. Conviene vigilar gasto operativo y reservas de bajo margen.')
    elif rentabilidad['margen'] < 15:
        recomendaciones.append('El margen es bajo. Conviene revisar costes y reservas menos rentables.')

    if alertas['conteos']['contratos_vencer'] > 0:
        recomendaciones.append('Hay contratos próximos a vencer. Conviene anticipar renovación o seguimiento.')

    if not recomendaciones:
        recomendaciones.append('Situación estable. Mantener seguimiento de ocupación y rentabilidad desde IA.')

    return recomendaciones[:5]


# ============================================================
# Consulta asistida simple
# ============================================================

def _resolver_consulta_simple(consulta, resumen, alertas, ocupacion, rentabilidad):
    q = (consulta or '').strip().lower()
    if not q:
        return None

    if 'resumen' in q or 'general' in q:
        return (
            f"Resumen actual: {resumen['reservas_activas']} reservas activas, "
            f"{resumen['tareas_pendientes']} tareas pendientes, "
            f"beneficio del mes {resumen['beneficio_mes']:.2f} €."
        )

    if 'alerta' in q or 'riesgo' in q:
        total = alertas['conteos']['total']
        principal = alertas['principal'] or 'No hay alertas críticas ahora mismo.'
        return f'Alertas detectadas: {total}. {principal}'

    if 'ocup' in q:
        g = ocupacion['global']
        return (
            f"Ocupación prevista: {g['porcentaje_mes']:.2f}% a 30 días, "
            f"tendencia {_resumen_tendencia_texto(g['tendencia'])}, "
            f"confianza {g['confianza']}."
        )

    if 'beneficio' in q or 'rentabilidad' in q or 'gasto' in q or 'ingreso' in q:
        return (
            f"Rentabilidad actual: ingresos {rentabilidad['ingresos']:.2f} €, "
            f"gastos {rentabilidad['gastos']:.2f} €, "
            f"beneficio {rentabilidad['beneficio']:.2f} €, "
            f"margen {rentabilidad['margen']:.2f}%."
        )

    if 'tarea' in q:
        return f"Tareas pendientes: {resumen['tareas_pendientes']}. Vencidas: {alertas['conteos']['tareas_vencidas']}."

    return 'Consulta recibida. Este módulo IA responde a resumen, alertas, ocupación, rentabilidad y tareas.'


# ============================================================
# Ruta principal
# ============================================================

@login_required
@ia_bp.route('/', methods=['GET', 'POST'])
def index():
    ids_propiedades = _ids_propiedades_usuario()

    resumen = _resumen_general(ids_propiedades)
    metricas_reservas = _metricas_reservas(ids_propiedades)
    alertas = _alertas(ids_propiedades, metricas_reservas)
    ranking = _ranking(ids_propiedades, metricas_reservas)
    ocupacion = _ocupacion_y_precios(ids_propiedades)
    rentabilidad = _rentabilidad(ids_propiedades, metricas_reservas)
    recomendaciones = _recomendaciones(resumen, alertas, ocupacion, rentabilidad)

    consulta = (request.form.get('consulta') or request.args.get('consulta') or '').strip()
    respuesta = _resolver_consulta_simple(consulta, resumen, alertas, ocupacion, rentabilidad)

    return render_template(
        'ia/index.html',
        resumen=resumen,
        alertas=alertas,
        ranking=ranking,
        ocupacion=ocupacion,
        rentabilidad=rentabilidad,
        recomendaciones=recomendaciones,
        consulta=consulta,
        respuesta=respuesta,
        now=datetime.now,
    )
