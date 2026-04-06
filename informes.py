from unittest import result

from flask import Blueprint, render_template, request, send_file, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import func
from models import (
    Propiedad,
    Reserva,
    Ingreso,
    Gasto,
    Contrato,
    Recibo,
    ContadorSuministro,
    LecturaContador,
)
from datetime import datetime, timedelta, date
from io import BytesIO, StringIO
from collections import defaultdict
import csv
from licencias_utils import puede_usar_modulo
from permisos import propiedades_visibles_query, propiedad_es_visible, usuario_tiene_permiso
from finanzas import calcular_rentabilidad_reserva

informes_bp = Blueprint('informes', __name__, url_prefix='/informes')


def _propiedades_usuario():
    return propiedades_visibles_query().order_by(Propiedad.nombre.asc()).all()


def _ids_propiedades_usuario():
    return [p.id for p in _propiedades_usuario()]


# =========================
# Helpers generales
# =========================

def _parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, '%Y-%m-%d').date()


def _owned_properties_query():
    return propiedades_visibles_query()


def _owned_property_ids(propiedad_id=None):
    query = _owned_properties_query()
    if propiedad_id:
        query = query.filter_by(id=propiedad_id)
    return [p.id for p in query.all()]


def _to_csv_response(text_value, filename):
    buffer = BytesIO(text_value.encode('utf-8-sig'))
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename,
    )


# =========================
# Helpers vacacional
# =========================

def _reserva_overlap_filter(query, fecha_inicio=None, fecha_fin=None):
    if fecha_inicio and fecha_fin:
        return query.filter(
            Reserva.fecha_entrada <= fecha_fin,
            Reserva.fecha_salida >= fecha_inicio,
        )
    if fecha_inicio:
        return query.filter(Reserva.fecha_salida >= fecha_inicio)
    if fecha_fin:
        return query.filter(Reserva.fecha_entrada <= fecha_fin)
    return query


def _query_reservas_usuario(propiedad_id=None, fecha_inicio=None, fecha_fin=None, estado=None):
    propiedad_ids = _owned_property_ids(propiedad_id)
    if not propiedad_ids:
        return []

    query = Reserva.query.filter(Reserva.propiedad_id.in_(propiedad_ids))

    query = _reserva_overlap_filter(query, fecha_inicio, fecha_fin)

    if estado:
        query = query.filter(Reserva.estado == estado)

    return query.order_by(Reserva.fecha_entrada).all()


def _estadisticas_reservas(reservas):
    total_reservas = len(reservas)
    total_ingresos = sum((r.precio_total or 0) for r in reservas)
    total_pagado = sum((getattr(r, 'deposito_pagado', 0) or 0) for r in reservas)
    total_pendiente = sum((getattr(r, 'saldo_pendiente', 0) or 0) for r in reservas)
    noches_totales = sum((r.fecha_salida - r.fecha_entrada).days for r in reservas)
    media_noches = noches_totales / total_reservas if total_reservas else 0

    estados = defaultdict(int)
    for r in reservas:
        estados[r.estado or 'sin_estado'] += 1

    return {
        'total_reservas': total_reservas,
        'total_ingresos': total_ingresos,
        'total_pagado': total_pagado,
        'total_pendiente': total_pendiente,
        'noches_totales': noches_totales,
        'media_noches': media_noches,
        'estados_resumen': dict(estados),
    }


def _estadisticas_ocupacion(reservas, fecha_inicio, fecha_fin, propiedad_ids):
    if not fecha_inicio:
        fecha_inicio = datetime.now().date().replace(day=1)

    if not fecha_fin:
        fecha_fin = datetime.now().date()

    dias_periodo = (fecha_fin - fecha_inicio).days + 1
    total_propiedades = len(propiedad_ids)
    noches_disponibles = dias_periodo * total_propiedades if total_propiedades else 0

    noches_ocupadas = 0
    entradas = 0
    salidas = 0

    ocupacion_por_propiedad = defaultdict(lambda: {
        'propiedad': None,
        'noches_ocupadas': 0,
        'reservas': 0,
        'ingresos': 0,
    })

    reservas_validas = []
    for r in reservas:
        estado = (r.estado or '').lower()
        if estado in ['cancelada', 'cancelado']:
            continue
        reservas_validas.append(r)

    for r in reservas_validas:
        inicio_real = max(r.fecha_entrada, fecha_inicio)
        fin_real = min(r.fecha_salida, fecha_fin)

        noches = max((fin_real - inicio_real).days, 0)
        noches_ocupadas += noches

        if fecha_inicio <= r.fecha_entrada <= fecha_fin:
            entradas += 1
        if fecha_inicio <= r.fecha_salida <= fecha_fin:
            salidas += 1

        nombre_propiedad = r.propiedad.nombre if r.propiedad else 'Sin propiedad'
        ocupacion_por_propiedad[nombre_propiedad]['propiedad'] = r.propiedad
        ocupacion_por_propiedad[nombre_propiedad]['noches_ocupadas'] += noches
        ocupacion_por_propiedad[nombre_propiedad]['reservas'] += 1
        ocupacion_por_propiedad[nombre_propiedad]['ingresos'] += (r.precio_total or 0)

    porcentaje_ocupacion = (
        (noches_ocupadas / noches_disponibles) * 100
        if noches_disponibles > 0 else 0
    )

    detalle_propiedades = []
    for nombre, data in ocupacion_por_propiedad.items():
        noches_disp_prop = dias_periodo
        porcentaje_prop = (
            (data['noches_ocupadas'] / noches_disp_prop) * 100
            if noches_disp_prop > 0 else 0
        )
        detalle_propiedades.append({
            'nombre': nombre,
            'noches_ocupadas': data['noches_ocupadas'],
            'noches_disponibles': noches_disp_prop,
            'ocupacion': porcentaje_prop,
            'reservas': data['reservas'],
            'ingresos': data['ingresos'],
        })

    detalle_propiedades.sort(key=lambda x: x['ocupacion'], reverse=True)

    return {
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'dias_periodo': dias_periodo,
        'total_propiedades': total_propiedades,
        'noches_disponibles': noches_disponibles,
        'noches_ocupadas': noches_ocupadas,
        'porcentaje_ocupacion': porcentaje_ocupacion,
        'entradas': entradas,
        'salidas': salidas,
        'detalle_propiedades': detalle_propiedades,
        'reservas_validas': reservas_validas,
    }


def _query_ingresos_gastos(propiedad_id=None, fecha_inicio=None, fecha_fin=None):
    propiedad_ids = _owned_property_ids(propiedad_id)
    if not propiedad_ids:
        return [], []

    if not fecha_fin:
        fecha_fin = datetime.now().date()
    if not fecha_inicio:
        fecha_inicio = fecha_fin - timedelta(days=30)

    ingresos = Ingreso.query.filter(
        Ingreso.propiedad_id.in_(propiedad_ids),
        Ingreso.fecha >= fecha_inicio,
        Ingreso.fecha <= fecha_fin,
    ).order_by(Ingreso.fecha).all()

    gastos = Gasto.query.filter(
        Gasto.propiedad_id.in_(propiedad_ids),
        Gasto.fecha >= fecha_inicio,
        Gasto.fecha <= fecha_fin,
    ).order_by(Gasto.fecha).all()

    return ingresos, gastos


# =========================
# Índice
# =========================

@informes_bp.route('/')
@login_required
def index():
    if not puede_usar_modulo(current_user, "informes"):
        flash("Tu plan no permite acceder a informes.", "warning")
        return redirect(url_for("main.dashboard"))

    if not usuario_tiene_permiso('puede_ver_informes'):
        flash("No tienes permisos para acceder a informes.", "danger")
        return redirect(url_for("main.dashboard"))

    propiedades = _owned_properties_query().all()
    return render_template('informes/index.html', propiedades=propiedades, now=datetime.now)


# =========================
# VACACIONAL
# =========================

@informes_bp.route('/reservas')
@login_required
def informe_reservas():
    if not usuario_tiene_permiso('puede_ver_informes'):
        flash("No tienes permisos para acceder a informes.", "danger")
        return redirect(url_for("main.dashboard"))

    propiedad_id = request.args.get('propiedad_id', type=int)
    fecha_inicio = _parse_date(request.args.get('fecha_inicio'))
    fecha_fin = _parse_date(request.args.get('fecha_fin'))
    estado = request.args.get('estado', '').strip() or None
    formato = request.args.get('formato', 'html')

    reservas = _query_reservas_usuario(
        propiedad_id=propiedad_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        estado=estado,
    )
    stats = _estadisticas_reservas(reservas)

    context = {
        'reservas': reservas,
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'propiedad_id': propiedad_id,
        'estado': estado,
        'now': datetime.now,
        **stats,
    }

    if formato == 'csv':
        return generar_csv_reservas(reservas)

    return render_template('informes/vacacional/produccion.html', **context)


@informes_bp.route('/vacacional/produccion')
@login_required
def informe_vv_produccion():
    return informe_reservas()


@informes_bp.route('/vacacional/ocupacion')
@login_required
def informe_vv_ocupacion():
    if not usuario_tiene_permiso('puede_ver_informes'):
        flash("No tienes permisos para acceder a informes.", "danger")
        return redirect(url_for("main.dashboard"))

    propiedad_id = request.args.get('propiedad_id', type=int)
    fecha_inicio = _parse_date(request.args.get('fecha_inicio'))
    fecha_fin = _parse_date(request.args.get('fecha_fin'))
    estado = request.args.get('estado', '').strip() or None
    formato = request.args.get('formato', 'html')

    reservas = _query_reservas_usuario(
        propiedad_id=propiedad_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        estado=estado,
    )

    propiedad_ids = _owned_property_ids(propiedad_id)
    stats = _estadisticas_ocupacion(reservas, fecha_inicio, fecha_fin, propiedad_ids)

    context = {
        'reservas': reservas,
        'propiedad_id': propiedad_id,
        'estado': estado,
        'now': datetime.now,
        **stats,
    }

    if formato == 'csv':
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Propiedad', 'Noches ocupadas', 'Noches disponibles',
            '% Ocupacion', 'Reservas', 'Ingresos'
        ])
        for item in stats['detalle_propiedades']:
            writer.writerow([
                item['nombre'],
                item['noches_ocupadas'],
                item['noches_disponibles'],
                f"{item['ocupacion']:.2f}",
                item['reservas'],
                f"{item['ingresos']:.2f}",
            ])
        return _to_csv_response(
            output.getvalue(),
            f"ocupacion_{datetime.now().strftime('%Y%m%d')}.csv",
        )

    return render_template('informes/vacacional/ocupacion.html', **context)


@informes_bp.route('/vacacional/cobros')
@login_required
def informe_vv_cobros():
    if not usuario_tiene_permiso('puede_ver_informes'):
        flash("No tienes permisos para acceder a informes.", "danger")
        return redirect(url_for("main.dashboard"))

    propiedad_id = request.args.get('propiedad_id', type=int)
    fecha_inicio = _parse_date(request.args.get('fecha_inicio'))
    fecha_fin = _parse_date(request.args.get('fecha_fin'))
    estado = request.args.get('estado', '').strip() or None
    formato = request.args.get('formato', 'html')

    reservas = _query_reservas_usuario(
        propiedad_id=propiedad_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        estado=estado,
    )

    pendientes = [r for r in reservas if (getattr(r, 'saldo_pendiente', 0) or 0) > 0]
    cobradas = [r for r in reservas if (getattr(r, 'saldo_pendiente', 0) or 0) <= 0]
    total_reservado = sum((r.precio_total or 0) for r in reservas)
    total_cobrado = sum((getattr(r, 'deposito_pagado', 0) or 0) for r in reservas)
    total_pendiente = sum((getattr(r, 'saldo_pendiente', 0) or 0) for r in reservas)

    if formato == 'csv':
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'ID', 'Propiedad', 'Huésped', 'Entrada', 'Salida',
            'Precio total', 'Cobrado', 'Pendiente', 'Estado'
        ])
        for r in reservas:
            writer.writerow([
                r.id,
                r.propiedad.nombre if r.propiedad else '',
                f"{getattr(r, 'huesped_nombre', '')} {getattr(r, 'huesped_apellidos', '')}".strip(),
                r.fecha_entrada,
                r.fecha_salida,
                r.precio_total or 0,
                getattr(r, 'deposito_pagado', 0) or 0,
                getattr(r, 'saldo_pendiente', 0) or 0,
                r.estado or '',
            ])
        return _to_csv_response(
            output.getvalue(),
            f"cobros_vacacional_{datetime.now().strftime('%Y%m%d')}.csv",
        )

    return render_template(
        'informes/vacacional/cobros.html',
        reservas=reservas,
        pendientes=pendientes,
        cobradas=cobradas,
        total_reservado=total_reservado,
        total_cobrado=total_cobrado,
        total_pendiente=total_pendiente,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        estado=estado,
        now=datetime.now,
    )


@informes_bp.route('/financiero')
@login_required
def informe_financiero():
    if not usuario_tiene_permiso('puede_ver_informes'):
        flash("No tienes permisos para acceder a informes.", "danger")
        return redirect(url_for("main.dashboard"))

    propiedad_id = request.args.get('propiedad_id', type=int)
    fecha_inicio = _parse_date(request.args.get('fecha_inicio'))
    fecha_fin = _parse_date(request.args.get('fecha_fin'))
    formato = request.args.get('formato', 'html')

    ingresos, gastos = _query_ingresos_gastos(propiedad_id, fecha_inicio, fecha_fin)

    if not fecha_fin:
        fecha_fin = datetime.now().date()
    if not fecha_inicio:
        fecha_inicio = fecha_fin - timedelta(days=30)

    total_ingresos = sum((i.cantidad or 0) for i in ingresos)
    total_gastos = sum((g.cantidad or 0) for g in gastos)
    balance = total_ingresos - total_gastos

    ingresos_por_metodo = defaultdict(float)
    for i in ingresos:
        ingresos_por_metodo[i.metodo_pago or 'sin_metodo'] += i.cantidad or 0

    gastos_por_categoria = defaultdict(float)
    for g in gastos:
        gastos_por_categoria[g.categoria or 'sin_categoria'] += g.cantidad or 0

    if formato == 'csv':
        return generar_csv_financiero(ingresos, gastos, fecha_inicio, fecha_fin)

    return render_template(
        'informes/financiero.html',
        ingresos=ingresos,
        gastos=gastos,
        total_ingresos=total_ingresos,
        total_gastos=total_gastos,
        balance=balance,
        ingresos_por_metodo=dict(ingresos_por_metodo),
        gastos_por_categoria=dict(gastos_por_categoria),
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        now=datetime.now,
    )


@informes_bp.route("/vacacional/rentabilidad")
@login_required
def informe_vacacional_rentabilidad():
    if not usuario_tiene_permiso('puede_ver_informes'):
        flash("No tienes permisos para acceder a informes.", "danger")
        return redirect(url_for("main.dashboard"))

    ids = _ids_propiedades_usuario()
    propiedades = Propiedad.query.filter(
        Propiedad.id.in_(ids)
    ).order_by(Propiedad.nombre.asc()).all() if ids else []

    propiedades_vv_ids = []
    for p in propiedades:
        contrato_activo = Contrato.query.filter_by(
            propiedad_id=p.id,
            estado="activo"
        ).first()
        if not contrato_activo:
            propiedades_vv_ids.append(p.id)

    reservas = Reserva.query.filter(
        Reserva.propiedad_id.in_(propiedades_vv_ids)
    ).order_by(Reserva.fecha_entrada.desc(), Reserva.id.desc()).all() if propiedades_vv_ids else []

    resultado = []

    for r in reservas:
        calculo = calcular_rentabilidad_reserva(r)
        if not calculo or calculo['es_larga_duracion']:
            continue

        if (
            calculo['ingresos'] > 0
            or calculo['gastos_reserva'] > 0
            or calculo['gasto_propiedad_imputado'] > 0
        ):
            resultado.append({
                "reserva": calculo["reserva"],
                "propiedad": calculo["propiedad"],
                "canal": calculo["canal"],
                "ingresos": calculo["ingresos"],
                "gastos_reserva": calculo["gastos_reserva"],
                "comisiones": calculo["comisiones"],
                "gastos_propiedad": calculo["gastos_propiedad"],
                "gasto_propiedad_imputado": calculo["gasto_propiedad_imputado"],
                "beneficio": calculo["beneficio"],
                "noches": calculo["noches"],
                "criterio_prorrateo": calculo["criterio_prorrateo"],
            })

    total_ingresos = sum(x["ingresos"] for x in resultado)
    total_gastos_reserva = sum(x["gastos_reserva"] for x in resultado)
    total_comisiones = sum(x["comisiones"] for x in resultado)
    total_gastos_imputados = sum(x["gasto_propiedad_imputado"] for x in resultado)
    total_beneficio = sum(x["beneficio"] for x in resultado)

    return render_template(
        "informes/vacacional/rentabilidad.html",
        resultado=resultado,
        total_ingresos=total_ingresos,
        total_gastos_reserva=total_gastos_reserva,
        total_comisiones=total_comisiones,
        total_gastos_imputados=total_gastos_imputados,
        total_beneficio=total_beneficio,
    )


# =========================
# LARGA DURACIÓN
# =========================

@informes_bp.route("/larga-duracion/contratos")
@login_required
def informe_ld_contratos():
    if not usuario_tiene_permiso('puede_ver_informes'):
        flash("No tienes permisos para acceder a informes.", "danger")
        return redirect(url_for("main.dashboard"))

    ids = _ids_propiedades_usuario()
    estado = request.args.get("estado", "").strip()
    propiedad_id = request.args.get("propiedad_id", type=int)

    query = Contrato.query.filter(Contrato.propiedad_id.in_(ids)) if ids else Contrato.query.filter(False)

    if estado:
        query = query.filter(Contrato.estado == estado)

    if propiedad_id and propiedad_id in ids:
        query = query.filter(Contrato.propiedad_id == propiedad_id)
    else:
        propiedad_id = None

    contratos = query.order_by(Contrato.fecha_inicio.desc(), Contrato.id.desc()).all()

    activos = [c for c in contratos if c.estado == "activo"]
    finalizados = [c for c in contratos if c.estado == "finalizado"]
    cancelados = [c for c in contratos if c.estado == "cancelado"]

    renta_activa = sum(c.renta_mensual or 0 for c in activos)
    fianzas = sum(c.fianza or 0 for c in contratos)

    if request.args.get("export") == "csv":
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Inquilino", "Propiedad", "Fecha inicio", "Fecha fin", "Estado", "Renta mensual", "Fianza"])
        for c in contratos:
            inquilino = f"{c.inquilino.nombre or ''} {c.inquilino.apellidos or ''}".strip() if c.inquilino else ""
            writer.writerow([
                c.id,
                inquilino,
                c.propiedad.nombre if c.propiedad else "",
                c.fecha_inicio or "",
                c.fecha_fin or "",
                c.estado or "",
                f"{c.renta_mensual or 0:.2f}",
                f"{c.fianza or 0:.2f}",
            ])
        return _to_csv_response(output.getvalue(), "informe_contratos_ld.csv")

    propiedades = Propiedad.query.filter(Propiedad.id.in_(ids)).order_by(Propiedad.nombre.asc()).all() if ids else []

    return render_template(
        "informes/larga_duracion/contratos.html",
        contratos=contratos,
        activos=len(activos),
        finalizados=len(finalizados),
        cancelados=len(cancelados),
        renta_activa=renta_activa,
        fianzas=fianzas,
        propiedades=propiedades,
        propiedad_id=propiedad_id,
        estado=estado,
    )


@informes_bp.route("/larga-duracion/cobros")
@login_required
def informe_ld_cobros():
    if not usuario_tiene_permiso('puede_ver_informes'):
        flash("No tienes permisos para acceder a informes.", "danger")
        return redirect(url_for("main.dashboard"))

    ids = _ids_propiedades_usuario()
    fecha_inicio = request.args.get("fecha_inicio")
    fecha_fin = request.args.get("fecha_fin")
    estado = request.args.get("estado", "").strip()

    query = Recibo.query.filter(Recibo.propiedad_id.in_(ids)) if ids else Recibo.query.filter(False)

    if fecha_inicio:
        try:
            fi = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
            query = query.filter(Recibo.fecha_emision >= fi)
        except ValueError:
            fecha_inicio = ""

    if fecha_fin:
        try:
            ff = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
            query = query.filter(Recibo.fecha_emision <= ff)
        except ValueError:
            fecha_fin = ""

    if estado:
        query = query.filter(Recibo.estado == estado)

    recibos = query.order_by(Recibo.fecha_emision.desc(), Recibo.id.desc()).all()

    total_emitido = sum(r.total or 0 for r in recibos)
    total_cobrado = sum((r.total or 0) for r in recibos if r.estado == "pagado")
    total_pendiente = sum((r.total or 0) for r in recibos if r.estado == "pendiente")
    total_impagado = sum((r.total or 0) for r in recibos if r.estado == "impagado")
    total_reclamado = sum((r.total or 0) for r in recibos if r.estado == "reclamado")

    contratos_activos = (
        Contrato.query.filter(Contrato.propiedad_id.in_(ids), Contrato.estado == "activo").all()
        if ids else []
    )
    renta_teorica_mensual = sum(c.renta_mensual or 0 for c in contratos_activos)

    por_metodo = {}
    for r in recibos:
        metodo = r.metodo_pago or "sin definir"
        por_metodo[metodo] = por_metodo.get(metodo, 0) + (r.total or 0)

    if request.args.get("export") == "csv":
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Numero", "Propiedad", "Inquilino", "Emision", "Vencimiento", "Estado", "Metodo", "Importe"])
        for r in recibos:
            inquilino = f"{r.inquilino.nombre or ''} {r.inquilino.apellidos or ''}".strip() if r.inquilino else ""
            writer.writerow([
                r.numero or f"#{r.id}",
                r.propiedad.nombre if r.propiedad else "",
                inquilino,
                r.fecha_emision or "",
                r.fecha_vencimiento or "",
                r.estado or "",
                r.metodo_pago or "",
                f"{r.total or 0:.2f}",
            ])
        return _to_csv_response(output.getvalue(), "informe_cobros_ld.csv")

    return render_template(
        "informes/larga_duracion/cobros.html",
        recibos=recibos,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        estado=estado,
        total_emitido=total_emitido,
        total_cobrado=total_cobrado,
        total_pendiente=total_pendiente,
        total_impagado=total_impagado,
        total_reclamado=total_reclamado,
        renta_teorica_mensual=renta_teorica_mensual,
        por_metodo=por_metodo,
    )


@informes_bp.route("/larga-duracion/morosidad")
@login_required
def informe_ld_morosidad():
    if not usuario_tiene_permiso('puede_ver_informes'):
        flash("No tienes permisos para acceder a informes.", "danger")
        return redirect(url_for("main.dashboard"))

    ids = _ids_propiedades_usuario()
    estado = request.args.get("estado", "").strip()
    propiedad_id = request.args.get("propiedad_id", type=int)

    query = Recibo.query.filter(Recibo.propiedad_id.in_(ids)) if ids else Recibo.query.filter(False)
    query = query.filter(Recibo.estado.in_(["pendiente", "impagado", "reclamado"]))

    if estado:
        query = query.filter(Recibo.estado == estado)

    if propiedad_id and propiedad_id in ids:
        query = query.filter(Recibo.propiedad_id == propiedad_id)
    else:
        propiedad_id = None

    recibos = query.order_by(Recibo.fecha_vencimiento.desc(), Recibo.fecha_emision.desc(), Recibo.id.desc()).all()

    hoy = date.today()
    total_deuda = sum(r.total or 0 for r in recibos)
    total_vencido = sum((r.total or 0) for r in recibos if r.fecha_vencimiento and r.fecha_vencimiento < hoy)
    total_no_vencido = total_deuda - total_vencido

    deuda_por_inquilino = {}
    deuda_por_propiedad = {}

    for r in recibos:
        nombre_inquilino = "Sin inquilino"
        if r.inquilino:
            nombre_inquilino = f"{r.inquilino.nombre or ''} {r.inquilino.apellidos or ''}".strip()
        nombre_propiedad = r.propiedad.nombre if r.propiedad else "Sin propiedad"
        importe = r.total or 0
        deuda_por_inquilino[nombre_inquilino] = deuda_por_inquilino.get(nombre_inquilino, 0) + importe
        deuda_por_propiedad[nombre_propiedad] = deuda_por_propiedad.get(nombre_propiedad, 0) + importe

    deuda_por_inquilino = sorted(deuda_por_inquilino.items(), key=lambda x: x[1], reverse=True)
    deuda_por_propiedad = sorted(deuda_por_propiedad.items(), key=lambda x: x[1], reverse=True)

    if request.args.get("export") == "csv":
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Numero", "Inquilino", "Propiedad", "Emision", "Vencimiento", "Estado", "Dias vencido", "Importe"])
        for r in recibos:
            inquilino = f"{r.inquilino.nombre or ''} {r.inquilino.apellidos or ''}".strip() if r.inquilino else ""
            dias_vencido = (hoy - r.fecha_vencimiento).days if r.fecha_vencimiento and r.fecha_vencimiento < hoy else 0
            writer.writerow([
                r.numero or f"#{r.id}",
                inquilino,
                r.propiedad.nombre if r.propiedad else "",
                r.fecha_emision or "",
                r.fecha_vencimiento or "",
                r.estado or "",
                dias_vencido,
                f"{r.total or 0:.2f}",
            ])
        return _to_csv_response(output.getvalue(), "informe_morosidad_ld.csv")

    propiedades = Propiedad.query.filter(Propiedad.id.in_(ids)).order_by(Propiedad.nombre.asc()).all() if ids else []

    return render_template(
        "informes/larga_duracion/morosidad.html",
        recibos=recibos,
        propiedades=propiedades,
        propiedad_id=propiedad_id,
        estado=estado,
        total_deuda=total_deuda,
        total_vencido=total_vencido,
        total_no_vencido=total_no_vencido,
        deuda_por_inquilino=deuda_por_inquilino,
        deuda_por_propiedad=deuda_por_propiedad,
        hoy=hoy,
    )


@informes_bp.route("/larga-duracion/vencimientos")
@login_required
def informe_ld_vencimientos():
    if not usuario_tiene_permiso('puede_ver_informes'):
        flash("No tienes permisos para acceder a informes.", "danger")
        return redirect(url_for("main.dashboard"))

    ids = _ids_propiedades_usuario()
    horizonte = request.args.get("horizonte", type=int) or 90
    propiedad_id = request.args.get("propiedad_id", type=int)

    if horizonte not in (30, 60, 90, 120):
        horizonte = 90

    query = Contrato.query.filter(Contrato.propiedad_id.in_(ids)) if ids else Contrato.query.filter(False)
    query = query.filter(Contrato.estado == "activo")

    if propiedad_id and propiedad_id in ids:
        query = query.filter(Contrato.propiedad_id == propiedad_id)
    else:
        propiedad_id = None

    contratos = query.order_by(Contrato.fecha_fin.asc(), Contrato.id.desc()).all()

    hoy = date.today()
    limite = hoy + timedelta(days=horizonte)

    vencen_30 = 0
    vencen_60 = 0
    vencen_90 = 0
    vencidos = 0
    renta_en_riesgo = 0
    detalle = []

    for c in contratos:
        if not c.fecha_fin:
            continue

        dias_restantes = (c.fecha_fin - hoy).days
        item = {"contrato": c, "dias_restantes": dias_restantes, "vencido": c.fecha_fin < hoy}

        if c.fecha_fin < hoy:
            vencidos += 1
            renta_en_riesgo += c.renta_mensual or 0
            detalle.append(item)
            continue

        if c.fecha_fin <= hoy + timedelta(days=30):
            vencen_30 += 1
        if c.fecha_fin <= hoy + timedelta(days=60):
            vencen_60 += 1
        if c.fecha_fin <= hoy + timedelta(days=90):
            vencen_90 += 1

        if c.fecha_fin <= limite:
            renta_en_riesgo += c.renta_mensual or 0
            detalle.append(item)

    detalle.sort(key=lambda x: (x["contrato"].fecha_fin, x["contrato"].id))

    if request.args.get("export") == "csv":
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Contrato", "Inquilino", "Propiedad", "Inicio", "Fin", "Dias restantes", "Situacion", "Renta mensual"])
        for item in detalle:
            c = item["contrato"]
            inquilino = f"{c.inquilino.nombre or ''} {c.inquilino.apellidos or ''}".strip() if c.inquilino else ""
            writer.writerow([
                c.id,
                inquilino,
                c.propiedad.nombre if c.propiedad else "",
                c.fecha_inicio or "",
                c.fecha_fin or "",
                item["dias_restantes"],
                "Vencido" if item["vencido"] else "En plazo",
                f"{c.renta_mensual or 0:.2f}",
            ])
        return _to_csv_response(output.getvalue(), "informe_vencimientos_ld.csv")

    propiedades = Propiedad.query.filter(Propiedad.id.in_(ids)).order_by(Propiedad.nombre.asc()).all() if ids else []

    return render_template(
        "informes/larga_duracion/vencimientos.html",
        propiedades=propiedades,
        propiedad_id=propiedad_id,
        horizonte=horizonte,
        hoy=hoy,
        vencen_30=vencen_30,
        vencen_60=vencen_60,
        vencen_90=vencen_90,
        vencidos=vencidos,
        renta_en_riesgo=renta_en_riesgo,
        detalle=detalle,
    )


@informes_bp.route("/larga-duracion/suministros")
@login_required
def informe_ld_suministros():
    if not usuario_tiene_permiso('puede_ver_informes'):
        flash("No tienes permisos para acceder a informes.", "danger")
        return redirect(url_for("main.dashboard"))

    ids = _ids_propiedades_usuario()
    propiedad_id = request.args.get("propiedad_id", type=int)
    contrato_id = request.args.get("contrato_id", type=int)
    tipo = request.args.get("tipo", "").strip()

    query = (
        LecturaContador.query
        .join(ContadorSuministro, LecturaContador.contador_id == ContadorSuministro.id)
        .filter(ContadorSuministro.propiedad_id.in_(ids))
        if ids else LecturaContador.query.filter(False)
    )

    if propiedad_id and propiedad_id in ids:
        query = query.filter(ContadorSuministro.propiedad_id == propiedad_id)
    else:
        propiedad_id = None

    if contrato_id:
        query = query.filter(LecturaContador.contrato_id == contrato_id)
    else:
        contrato_id = None

    if tipo:
        query = query.filter(ContadorSuministro.tipo == tipo)

    lecturas = query.order_by(LecturaContador.fecha_lectura.desc(), LecturaContador.id.desc()).all()

    total_consumo = sum(l.consumo or 0 for l in lecturas)
    total_importe = sum(l.importe_total or 0 for l in lecturas)
    total_agua = sum((l.importe_total or 0) for l in lecturas if l.contador and l.contador.tipo == "agua")
    total_luz = sum((l.importe_total or 0) for l in lecturas if l.contador and l.contador.tipo == "luz")
    total_gas = sum((l.importe_total or 0) for l in lecturas if l.contador and l.contador.tipo == "gas")
    total_otro = sum((l.importe_total or 0) for l in lecturas if l.contador and l.contador.tipo == "otro")

    por_propiedad = {}
    por_contrato = {}

    for l in lecturas:
        nombre_propiedad = l.contador.propiedad.nombre if l.contador and l.contador.propiedad else "-"
        por_propiedad.setdefault(nombre_propiedad, {"lecturas": 0, "consumo": 0, "importe": 0})
        por_propiedad[nombre_propiedad]["lecturas"] += 1
        por_propiedad[nombre_propiedad]["consumo"] += l.consumo or 0
        por_propiedad[nombre_propiedad]["importe"] += l.importe_total or 0

        clave_contrato = "Sin contrato"
        if l.contrato:
            inquilino = f"{l.contrato.inquilino.nombre or ''} {l.contrato.inquilino.apellidos or ''}".strip() if l.contrato.inquilino else "-"
            clave_contrato = f"#{l.contrato.id} · {inquilino}"

        por_contrato.setdefault(clave_contrato, {"propiedad": nombre_propiedad, "lecturas": 0, "consumo": 0, "importe": 0})
        por_contrato[clave_contrato]["lecturas"] += 1
        por_contrato[clave_contrato]["consumo"] += l.consumo or 0
        por_contrato[clave_contrato]["importe"] += l.importe_total or 0

    por_propiedad = sorted(por_propiedad.items(), key=lambda x: x[1]["importe"], reverse=True)
    por_contrato = sorted(por_contrato.items(), key=lambda x: x[1]["importe"], reverse=True)

    if request.args.get("export") == "csv":
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Fecha", "Contador", "Tipo", "Propiedad", "Contrato", "Anterior", "Actual", "Consumo", "Precio", "Importe"])
        for l in lecturas:
            writer.writerow([
                l.fecha_lectura or "",
                l.contador.nombre if l.contador else "",
                l.contador.tipo if l.contador else "",
                l.contador.propiedad.nombre if l.contador and l.contador.propiedad else "",
                l.contrato.id if l.contrato else "",
                f"{l.lectura_anterior or 0:.2f}",
                f"{l.lectura_actual or 0:.2f}",
                f"{l.consumo or 0:.2f}",
                f"{l.precio_unitario or 0:.2f}",
                f"{l.importe_total or 0:.2f}",
            ])
        return _to_csv_response(output.getvalue(), "informe_suministros_ld.csv")

    propiedades = Propiedad.query.filter(Propiedad.id.in_(ids)).order_by(Propiedad.nombre.asc()).all() if ids else []
    contratos = Contrato.query.filter(Contrato.propiedad_id.in_(ids)).order_by(Contrato.id.desc()).all() if ids else []

    return render_template(
        "informes/larga_duracion/suministros.html",
        lecturas=lecturas,
        propiedades=propiedades,
        contratos=contratos,
        propiedad_id=propiedad_id,
        contrato_id=contrato_id,
        tipo=tipo,
        total_consumo=total_consumo,
        total_importe=total_importe,
        total_agua=total_agua,
        total_luz=total_luz,
        total_gas=total_gas,
        total_otro=total_otro,
        por_propiedad=por_propiedad,
        por_contrato=por_contrato,
    )


@informes_bp.route("/larga-duracion/rentabilidad")
@login_required
def informe_ld_rentabilidad():
    if not usuario_tiene_permiso('puede_ver_informes'):
        flash("No tienes permisos para acceder a informes.", "danger")
        return redirect(url_for("main.dashboard"))

    ids = _ids_propiedades_usuario()
    propiedades = Propiedad.query.filter(
        Propiedad.id.in_(ids)
    ).order_by(Propiedad.nombre.asc()).all() if ids else []

    resultado = []

    for propiedad in propiedades:
        contratos = Contrato.query.filter_by(propiedad_id=propiedad.id).all()
        recibos = Recibo.query.filter_by(propiedad_id=propiedad.id).all()

        contrato_activo = next((c for c in contratos if c.estado == "activo"), None)
        if not contrato_activo and not contratos:
            continue

        renta_activa = sum((c.renta_mensual or 0) for c in contratos if c.estado == "activo")
        total_facturado = sum((r.total or 0) for r in recibos)
        total_cobrado = sum((r.total or 0) for r in recibos if r.estado == "pagado")
        total_pendiente = sum((r.total or 0) for r in recibos if r.estado in ["pendiente", "impagado", "reclamado"])

        total_suministros_facturados = sum(
            (r.total or 0)
            for r in recibos
            if (getattr(r, "tipo", "") or "").lower() == "suministro"
        )

        total_suministros_cobrados = sum(
            (r.total or 0)
            for r in recibos
            if (getattr(r, "tipo", "") or "").lower() == "suministro" and r.estado == "pagado"
        )

        gastos_propiedad = Gasto.query.filter(
            Gasto.propiedad_id == propiedad.id,
            Gasto.reserva_id.is_(None)
        ).all()

        total_gastos = sum(g.cantidad or 0 for g in gastos_propiedad)
        cobrado_renta = sum(
            (r.total or 0)
            for r in recibos
            if (getattr(r, "tipo", "") or "").lower() != "suministro"
            and r.estado == "pagado"
        )

        beneficio_real = cobrado_renta - total_gastos

        resultado.append({
            "propiedad": propiedad,
            "renta_activa": renta_activa,
            "total_facturado": total_facturado,
            "total_cobrado": total_cobrado,
            "total_pendiente": total_pendiente,
            "total_suministros_facturados": total_suministros_facturados,
            "total_suministros_cobrados": total_suministros_cobrados,
            "total_gastos": total_gastos,
            "beneficio_real": beneficio_real,
            "gasto_suministros": total_suministros_facturados,
            "saldo_neto": beneficio_real,
        })

    total_renta_activa = sum(x["renta_activa"] for x in resultado)
    total_facturado = sum(x["total_facturado"] for x in resultado)
    total_cobrado = sum(x["total_cobrado"] for x in resultado)
    total_pendiente = sum(x["total_pendiente"] for x in resultado)
    total_suministros_facturados = sum(x["total_suministros_facturados"] for x in resultado)
    total_suministros_cobrados = sum(x["total_suministros_cobrados"] for x in resultado)
    total_gastos = sum(x["total_gastos"] for x in resultado)
    total_beneficio_real = sum(x["beneficio_real"] for x in resultado)

    if request.args.get("export") == "csv":
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Propiedad",
            "Renta activa",
            "Facturado",
            "Cobrado",
            "Pendiente",
            "Suministros facturados",
            "Suministros cobrados",
            "Gastos reales",
            "Beneficio real"
        ])
        for item in resultado:
            writer.writerow([
                item["propiedad"].nombre,
                f'{item["renta_activa"]:.2f}',
                f'{item["total_facturado"]:.2f}',
                f'{item["total_cobrado"]:.2f}',
                f'{item["total_pendiente"]:.2f}',
                f'{item["total_suministros_facturados"]:.2f}',
                f'{item["total_suministros_cobrados"]:.2f}',
                f'{item["total_gastos"]:.2f}',
                f'{item["beneficio_real"]:.2f}',
            ])
        return _to_csv_response(output.getvalue(), "informe_rentabilidad_ld.csv")

    return render_template(
        "informes/larga_duracion/rentabilidad.html",
        resultado=resultado,
        total_renta_activa=total_renta_activa,
        total_facturado=total_facturado,
        total_cobrado=total_cobrado,
        total_pendiente=total_pendiente,
        total_suministros_facturados=total_suministros_facturados,
        total_suministros_cobrados=total_suministros_cobrados,
        total_gastos=total_gastos,
        total_beneficio_real=total_beneficio_real,
        total_suministros=total_suministros_facturados,
        total_neto=total_beneficio_real,
    )


@informes_bp.route("/larga-duracion/resumen")
@login_required
def informe_ld_resumen():
    if not usuario_tiene_permiso('puede_ver_informes'):
        flash("No tienes permisos para acceder a informes.", "danger")
        return redirect(url_for("main.dashboard"))

    ids = _ids_propiedades_usuario()
    hoy = date.today()

    propiedades = Propiedad.query.filter(Propiedad.id.in_(ids)).order_by(Propiedad.nombre.asc()).all() if ids else []
    contratos = Contrato.query.filter(Contrato.propiedad_id.in_(ids)).all() if ids else []
    recibos = Recibo.query.filter(Recibo.propiedad_id.in_(ids)).all() if ids else []
    lecturas = (
        LecturaContador.query
        .join(ContadorSuministro, LecturaContador.contador_id == ContadorSuministro.id)
        .filter(ContadorSuministro.propiedad_id.in_(ids))
        .all() if ids else []
    )

    contratos_activos = [c for c in contratos if c.estado == "activo"]
    contratos_finalizados = [c for c in contratos if c.estado == "finalizado"]
    contratos_cancelados = [c for c in contratos if c.estado == "cancelado"]

    renta_mensual_activa = sum(c.renta_mensual or 0 for c in contratos_activos)
    total_fianzas = sum(c.fianza or 0 for c in contratos)
    total_facturado = sum(r.total or 0 for r in recibos)
    total_cobrado = sum((r.total or 0) for r in recibos if r.estado == "pagado")
    total_pendiente = sum((r.total or 0) for r in recibos if r.estado == "pendiente")
    total_impagado = sum((r.total or 0) for r in recibos if r.estado == "impagado")
    total_reclamado = sum((r.total or 0) for r in recibos if r.estado == "reclamado")
    deuda_total = total_pendiente + total_impagado + total_reclamado

    gastos_reales_ld = Gasto.query.filter(
        Gasto.propiedad_id.in_(ids),
        Gasto.reserva_id.is_(None)
    ).all() if ids else []

    total_gastos_reales = sum(g.cantidad or 0 for g in gastos_reales_ld)
    saldo_neto = total_cobrado - total_gastos_reales

    vencen_30 = 0
    vencidos = 0
    for c in contratos_activos:
        if not c.fecha_fin:
            continue
        if c.fecha_fin < hoy:
            vencidos += 1
        elif c.fecha_fin <= hoy + timedelta(days=30):
            vencen_30 += 1

    resumen_propiedades = []
    for p in propiedades:
        contratos_p = [c for c in contratos if c.propiedad_id == p.id]
        recibos_p = [r for r in recibos if r.propiedad_id == p.id]
        gastos_p = Gasto.query.filter(
            Gasto.propiedad_id == p.id,
            Gasto.reserva_id.is_(None)
        ).all()

        activos_p = [c for c in contratos_p if c.estado == "activo"]
        renta_p = sum(c.renta_mensual or 0 for c in activos_p)
        cobrado_p = sum((r.total or 0) for r in recibos_p if r.estado == "pagado")
        deuda_p = sum((r.total or 0) for r in recibos_p if r.estado in ["pendiente", "impagado", "reclamado"])
        gastos_reales_p = sum(g.cantidad or 0 for g in gastos_p)
        neto_p = cobrado_p - gastos_reales_p

        resumen_propiedades.append({
            "propiedad": p,
            "contratos_activos": len(activos_p),
            "renta_mensual": renta_p,
            "cobrado": cobrado_p,
            "deuda": deuda_p,
            "gastos_reales": gastos_reales_p,
            "neto": neto_p,
        })

    resumen_propiedades.sort(key=lambda x: x["neto"], reverse=True)

    if request.args.get("export") == "csv":
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Propiedad", "Contratos activos", "Renta mensual", "Cobrado", "Deuda", "Gastos reales", "Neto"])
        for item in resumen_propiedades:
            writer.writerow([
                item["propiedad"].nombre,
                item["contratos_activos"],
                f'{item["renta_mensual"]:.2f}',
                f'{item["cobrado"]:.2f}',
                f'{item["deuda"]:.2f}',
                f'{item["gastos_reales"]:.2f}',
                f'{item["neto"]:.2f}',
            ])
        return _to_csv_response(output.getvalue(), "resumen_general_ld.csv")

    return render_template(
        "informes/larga_duracion/resumen.html",
        hoy=hoy,
        total_propiedades=len(propiedades),
        contratos_activos=len(contratos_activos),
        contratos_finalizados=len(contratos_finalizados),
        contratos_cancelados=len(contratos_cancelados),
        renta_mensual_activa=renta_mensual_activa,
        total_fianzas=total_fianzas,
        total_facturado=total_facturado,
        total_cobrado=total_cobrado,
        total_pendiente=total_pendiente,
        total_impagado=total_impagado,
        total_reclamado=total_reclamado,
        deuda_total=deuda_total,
        total_suministros=0,
        total_gastos_reales=total_gastos_reales,
        saldo_neto=saldo_neto,
        vencen_30=vencen_30,
        vencidos=vencidos,
        resumen_propiedades=resumen_propiedades,
    )


# =========================
# Exportaciones CSV vacacional
# =========================

def generar_csv_reservas(reservas):
    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        'ID', 'Propiedad', 'Huésped', 'Entrada', 'Salida', 'Noches',
        'Huéspedes', 'Precio Total', 'Pagado', 'Pendiente', 'Estado'
    ])

    for r in reservas:
        noches = (r.fecha_salida - r.fecha_entrada).days
        writer.writerow([
            r.id,
            r.propiedad.nombre if r.propiedad else '',
            f"{getattr(r, 'huesped_nombre', '')} {getattr(r, 'huesped_apellidos', '')}".strip(),
            r.fecha_entrada,
            r.fecha_salida,
            noches,
            getattr(r, 'num_huespedes', ''),
            r.precio_total,
            getattr(r, 'deposito_pagado', 0) or 0,
            getattr(r, 'saldo_pendiente', 0) or 0,
            r.estado,
        ])

    return _to_csv_response(
        output.getvalue(),
        f"reservas_{datetime.now().strftime('%Y%m%d')}.csv",
    )


def generar_csv_financiero(ingresos, gastos, fecha_inicio, fecha_fin):
    output = StringIO()
    writer = csv.writer(output)

    writer.writerow(['INFORME FINANCIERO', f'{fecha_inicio} - {fecha_fin}'])
    writer.writerow([])

    writer.writerow(['INGRESOS'])
    writer.writerow(['Fecha', 'Propiedad', 'Concepto', 'Método', 'Cantidad'])
    for i in ingresos:
        writer.writerow([
            i.fecha,
            i.propiedad.nombre if i.propiedad else 'General',
            i.concepto,
            i.metodo_pago,
            i.cantidad,
        ])

    total_ingresos = sum((i.cantidad or 0) for i in ingresos)
    writer.writerow(['', '', '', 'TOTAL INGRESOS', total_ingresos])
    writer.writerow([])

    writer.writerow(['GASTOS'])
    writer.writerow(['Fecha', 'Propiedad', 'Concepto', 'Categoría', 'Cantidad'])
    for g in gastos:
        writer.writerow([
            g.fecha,
            g.propiedad.nombre if g.propiedad else 'General',
            g.concepto,
            g.categoria,
            g.cantidad,
        ])

    total_gastos = sum((g.cantidad or 0) for g in gastos)
    writer.writerow(['', '', '', 'TOTAL GASTOS', total_gastos])
    writer.writerow([])
    writer.writerow(['BALANCE', total_ingresos - total_gastos])

    return _to_csv_response(
        output.getvalue(),
        f"financiero_{datetime.now().strftime('%Y%m%d')}.csv",
    )


# =========================
# SES / Hospedajes
# =========================

@informes_bp.route('/exportar-ses/<int:reserva_id>')
@login_required
def exportar_ses(reserva_id):
    if not usuario_tiene_permiso('puede_ver_informes'):
        flash("No tienes permisos para exportar SES.", "danger")
        return redirect(url_for("main.dashboard"))

    reserva = Reserva.query.get_or_404(reserva_id)
    if not reserva.propiedad or not propiedad_es_visible(reserva.propiedad):
        flash("No tienes permiso.", "danger")
        return redirect(url_for("informes.index"))

    lineas = []
    for idx, h in enumerate(reserva.huespedes):
        apellido1 = h.apellidos.split()[0] if h.apellidos and len(h.apellidos.split()) > 0 else ''
        apellido2 = h.apellidos.split()[1] if h.apellidos and len(h.apellidos.split()) > 1 else ''
        linea = [
            h.nombre,
            apellido1,
            apellido2,
            (h.sexo or '')[:1].upper(),
            h.fecha_nacimiento.strftime('%d%m%Y') if h.fecha_nacimiento else '',
            h.tipo_documento,
            h.numero_documento,
            h.nacionalidad,
            reserva.fecha_entrada.strftime('%d%m%Y'),
            '16:00',
            reserva.fecha_salida.strftime('%d%m%Y'),
            '11:00',
            h.domicilio or '',
            h.ciudad or '',
            h.codigo_postal or '',
            reserva.propiedad.ciudad or '',
            h.pais or 'ES',
            h.telefono or '',
            h.email or '',
            'Titular' if idx == 0 else 'Acompañante',
        ]
        lineas.append('\t'.join(str(campo) for campo in linea))

    output = '\n'.join(lineas)
    buffer = BytesIO(output.encode('utf-8'))
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"ses_hospedajes_{reserva.id}.txt",
        mimetype='text/plain',
    )


@informes_bp.route('/vacacional/ses')
@login_required
def informe_vv_ses():
    if not usuario_tiene_permiso('puede_ver_informes'):
        flash("No tienes permisos para acceder a informes.", "danger")
        return redirect(url_for("main.dashboard"))

    propiedad_id = request.args.get('propiedad_id', type=int)
    fecha_inicio = _parse_date(request.args.get('fecha_inicio'))
    fecha_fin = _parse_date(request.args.get('fecha_fin'))
    estado = request.args.get('estado', '').strip() or None

    reservas = _query_reservas_usuario(
        propiedad_id=propiedad_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        estado=estado,
    )

    completas = []
    incompletas = []

    for r in reservas:
        errores = []

        huespedes_rel = getattr(r, 'huespedes', None)
        if huespedes_rel is None:
            huespedes = []
        elif hasattr(huespedes_rel, 'all'):
            huespedes = huespedes_rel.all()
        else:
            huespedes = list(huespedes_rel)

        if not huespedes:
            errores.append('Sin huéspedes')

        for idx, h in enumerate(huespedes, start=1):
            if not getattr(h, 'nombre', None):
                errores.append(f'Huésped {idx}: sin nombre')
            if not getattr(h, 'apellidos', None):
                errores.append(f'Huésped {idx}: sin apellidos')
            if not getattr(h, 'tipo_documento', None):
                errores.append(f'Huésped {idx}: sin tipo documento')
            if not getattr(h, 'numero_documento', None):
                errores.append(f'Huésped {idx}: sin número documento')
            if not getattr(h, 'nacionalidad', None):
                errores.append(f'Huésped {idx}: sin nacionalidad')
            if not getattr(h, 'fecha_nacimiento', None):
                errores.append(f'Huésped {idx}: sin fecha nacimiento')

        item = {
            'reserva': r,
            'errores': errores,
            'total_huespedes': len(huespedes),
        }

        if errores:
            incompletas.append(item)
        else:
            completas.append(item)

    return render_template(
        'informes/vacacional/ses.html',
        reservas=reservas,
        completas=completas,
        incompletas=incompletas,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        propiedad_id=propiedad_id,
        estado=estado,
        total_reservas=len(reservas),
        total_completas=len(completas),
        total_incompletas=len(incompletas),
        now=datetime.now,
    )


@informes_bp.route('/exportar-ses-xml/<int:reserva_id>')
@login_required
def exportar_ses_xml(reserva_id):
    from xml.dom import minidom

    if not usuario_tiene_permiso('puede_ver_informes'):
        flash("No tienes permisos para exportar SES.", "danger")
        return redirect(url_for("main.dashboard"))

    reserva = Reserva.query.get_or_404(reserva_id)
    if not reserva.propiedad or not propiedad_es_visible(reserva.propiedad):
        flash("No tienes permiso.", "danger")
        return redirect(url_for("informes.index"))

    doc = minidom.Document()

    root = doc.createElement('ComunicacionHospedajes')
    doc.appendChild(root)

    cabecera = doc.createElement('Cabecera')
    root.appendChild(cabecera)

    fecha_envio = doc.createElement('FechaEnvio')
    fecha_envio.appendChild(doc.createTextNode(datetime.now().strftime('%Y-%m-%d')))
    cabecera.appendChild(fecha_envio)

    parte = doc.createElement('ParteViajeros')
    root.appendChild(parte)

    estancia = doc.createElement('DatosEstancia')
    parte.appendChild(estancia)

    entrada = doc.createElement('FechaEntrada')
    entrada.appendChild(doc.createTextNode(reserva.fecha_entrada.strftime('%Y-%m-%d')))
    estancia.appendChild(entrada)

    salida = doc.createElement('FechaSalida')
    salida.appendChild(doc.createTextNode(reserva.fecha_salida.strftime('%Y-%m-%d')))
    estancia.appendChild(salida)

    for idx, h in enumerate(reserva.huespedes):
        viajero = doc.createElement('Viajero')
        viajero.setAttribute('rol', 'TITULAR' if idx == 0 else 'ACOMPAÑANTE')
        parte.appendChild(viajero)

        apellido1 = h.apellidos.split()[0] if h.apellidos else ''
        apellido2 = h.apellidos.split()[1] if h.apellidos and len(h.apellidos.split()) > 1 else ''

        campos = [
            ('Nombre', h.nombre),
            ('Apellido1', apellido1),
            ('Apellido2', apellido2),
            ('TipoDocumento', h.tipo_documento),
            ('NumeroDocumento', h.numero_documento),
            ('SoporteDocumento', h.numero_soporte or ''),
            ('FechaNacimiento', h.fecha_nacimiento.strftime('%Y-%m-%d') if h.fecha_nacimiento else ''),
            ('Nacionalidad', h.nacionalidad),
            ('Sexo', (h.sexo or '')[:1].upper()),
            ('Domicilio', h.domicilio or ''),
            ('Ciudad', h.ciudad or ''),
            ('CodigoPostal', h.codigo_postal or ''),
            ('Pais', h.pais or 'ES'),
            ('Telefono', h.telefono or ''),
            ('Email', h.email or ''),
        ]

        for tag, valor in campos:
            elem = doc.createElement(tag)
            elem.appendChild(doc.createTextNode(str(valor)))
            viajero.appendChild(elem)

    xml_string = doc.toprettyxml(encoding='utf-8')
    buffer = BytesIO(xml_string)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"ses_hospedajes_{reserva.id}.xml",
        mimetype='application/xml',
    )


@informes_bp.route('/vacacional/operativo')
@login_required
def informe_vv_operativo():
    if not usuario_tiene_permiso('puede_ver_informes'):
        flash("No tienes permisos para acceder a informes.", "danger")
        return redirect(url_for("main.dashboard"))

    propiedad_id = request.args.get('propiedad_id', type=int)
    fecha = _parse_date(request.args.get('fecha')) or datetime.now().date()

    propiedades_query = _owned_properties_query()
    if propiedad_id:
        propiedades_query = propiedades_query.filter_by(id=propiedad_id)
    propiedades = propiedades_query.all()

    propiedad_ids = [p.id for p in propiedades]
    if not propiedad_ids:
        return render_template(
            'informes/vacacional/operativo.html',
            fecha=fecha,
            propiedades=[],
            propiedad_id=propiedad_id,
            checkins_hoy=[],
            checkouts_hoy=[],
            ocupadas_hoy=[],
            libres_hoy=[],
            limpieza_hoy=[],
            llegadas_manana=[],
            salidas_manana=[],
            total_checkins=0,
            total_checkouts=0,
            total_ocupadas=0,
            total_libres=0,
            total_limpieza=0,
            now=datetime.now,
        )

    todas_reservas = Reserva.query.filter(
        Reserva.propiedad_id.in_(propiedad_ids)
    ).all()

    checkins_hoy = []
    checkouts_hoy = []
    ocupadas_hoy = []
    llegadas_manana = []
    salidas_manana = []

    manana = fecha + timedelta(days=1)

    for r in todas_reservas:
        estado = (r.estado or '').lower()
        if estado in ['cancelada', 'cancelado']:
            continue

        if r.fecha_entrada == fecha:
            checkins_hoy.append(r)

        if r.fecha_salida == fecha:
            checkouts_hoy.append(r)

        if r.fecha_entrada <= fecha <= r.fecha_salida:
            ocupadas_hoy.append(r)

        if r.fecha_entrada == manana:
            llegadas_manana.append(r)

        if r.fecha_salida == manana:
            salidas_manana.append(r)

    propiedades_ocupadas_ids = {
        r.propiedad_id for r in ocupadas_hoy if r.propiedad_id
    }

    libres_hoy = [p for p in propiedades if p.id not in propiedades_ocupadas_ids]

    requiere_limpieza_ids = {
        r.propiedad_id for r in checkouts_hoy if r.propiedad_id
    }
    limpieza_hoy = [p for p in propiedades if p.id in requiere_limpieza_ids]

    return render_template(
        'informes/vacacional/operativo.html',
        fecha=fecha,
        propiedades=propiedades,
        propiedad_id=propiedad_id,
        checkins_hoy=checkins_hoy,
        checkouts_hoy=checkouts_hoy,
        ocupadas_hoy=ocupadas_hoy,
        libres_hoy=libres_hoy,
        limpieza_hoy=limpieza_hoy,
        llegadas_manana=llegadas_manana,
        salidas_manana=salidas_manana,
        total_checkins=len(checkins_hoy),
        total_checkouts=len(checkouts_hoy),
        total_ocupadas=len(propiedades_ocupadas_ids),
        total_libres=len(libres_hoy),
        total_limpieza=len(limpieza_hoy),
        now=datetime.now,
    )