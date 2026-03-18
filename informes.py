from flask import Blueprint, render_template, request, send_file
from flask_login import login_required, current_user
from models import db, Propiedad, Reserva, Ingreso, Gasto
from datetime import datetime, timedelta
from io import BytesIO
import csv

informes_bp = Blueprint('informes', __name__, url_prefix='/informes')

@informes_bp.route('/')
@login_required
def index():
    """Página principal de informes"""
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    return render_template('informes/index.html', 
                          propiedades=propiedades,
                          now=datetime.now)

@informes_bp.route('/reservas')
@login_required
def informe_reservas():
    """Informe de reservas por período"""
    propiedad_id = request.args.get('propiedad_id', type=int)
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    formato = request.args.get('formato', 'html')
    
    # Construir query base
    query = Reserva.query.join(Propiedad).filter(Propiedad.usuario_id == current_user.id)
    
    if propiedad_id:
        query = query.filter(Reserva.propiedad_id == propiedad_id)
    
    if fecha_inicio:
        fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
        query = query.filter(Reserva.fecha_entrada >= fecha_inicio)
    
    if fecha_fin:
        fecha_fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
        query = query.filter(Reserva.fecha_salida <= fecha_fin)
    
    reservas = query.order_by(Reserva.fecha_entrada).all()
    
    # Estadísticas
    total_reservas = len(reservas)
    total_ingresos = sum(r.precio_total for r in reservas)
    total_pagado = sum(r.deposito_pagado for r in reservas)
    noches_totales = sum((r.fecha_salida - r.fecha_entrada).days for r in reservas)
    ocupacion_media = noches_totales / total_reservas if total_reservas > 0 else 0
    
    if formato == 'html':
        return render_template('informes/reservas.html', 
                              reservas=reservas,
                              total_reservas=total_reservas,
                              total_ingresos=total_ingresos,
                              total_pagado=total_pagado,
                              noches_totales=noches_totales,
                              ocupacion_media=ocupacion_media,
                              fecha_inicio=fecha_inicio,
                              fecha_fin=fecha_fin,
                              propiedad_id=propiedad_id,
                              now=datetime.now)
    elif formato == 'csv':
        return generar_csv_reservas(reservas)
    elif formato == 'pdf':
        return generar_pdf_informe_reservas(reservas, fecha_inicio, fecha_fin, propiedad_id)
    else:
        return render_template('informes/reservas.html', 
                              reservas=reservas,
                              total_reservas=total_reservas,
                              total_ingresos=total_ingresos,
                              total_pagado=total_pagado,
                              noches_totales=noches_totales,
                              ocupacion_media=ocupacion_media,
                              fecha_inicio=fecha_inicio,
                              fecha_fin=fecha_fin,
                              propiedad_id=propiedad_id,
                              now=datetime.now)

@informes_bp.route('/financiero')
@login_required
def informe_financiero():
    """Informe financiero (ingresos vs gastos)"""
    propiedad_id = request.args.get('propiedad_id', type=int)
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    formato = request.args.get('formato', 'html')
    
    # Fechas por defecto: último mes
    if not fecha_fin:
        fecha_fin = datetime.now().date()
    else:
        fecha_fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
    
    if not fecha_inicio:
        fecha_inicio = fecha_fin - timedelta(days=30)
    else:
        fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
    
    # Construir queries
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id)
    if propiedad_id:
        propiedades = propiedades.filter_by(id=propiedad_id)
    propiedad_ids = [p.id for p in propiedades]
    
    # Ingresos del período
    ingresos = Ingreso.query.filter(
        Ingreso.propiedad_id.in_(propiedad_ids),
        Ingreso.fecha >= fecha_inicio,
        Ingreso.fecha <= fecha_fin
    ).order_by(Ingreso.fecha).all()
    
    # Gastos del período
    gastos = Gasto.query.filter(
        Gasto.propiedad_id.in_(propiedad_ids),
        Gasto.fecha >= fecha_inicio,
        Gasto.fecha <= fecha_fin
    ).order_by(Gasto.fecha).all()
    
    # Totales
    total_ingresos = sum(i.cantidad for i in ingresos)
    total_gastos = sum(g.cantidad for g in gastos)
    balance = total_ingresos - total_gastos
    
    # Agrupar por categoría
    ingresos_por_metodo = {}
    for i in ingresos:
        ingresos_por_metodo[i.metodo_pago] = ingresos_por_metodo.get(i.metodo_pago, 0) + i.cantidad
    
    gastos_por_categoria = {}
    for g in gastos:
        gastos_por_categoria[g.categoria] = gastos_por_categoria.get(g.categoria, 0) + g.cantidad
    
    if formato == 'html':
        return render_template('informes/financiero.html',
                              ingresos=ingresos,
                              gastos=gastos,
                              total_ingresos=total_ingresos,
                              total_gastos=total_gastos,
                              balance=balance,
                              ingresos_por_metodo=ingresos_por_metodo,
                              gastos_por_categoria=gastos_por_categoria,
                              fecha_inicio=fecha_inicio,
                              fecha_fin=fecha_fin,
                              now=datetime.now)
    elif formato == 'csv':
        return generar_csv_financiero(ingresos, gastos, fecha_inicio, fecha_fin)
    elif formato == 'pdf':
        return generar_pdf_informe_financiero(ingresos, gastos, total_ingresos, total_gastos, balance,
                                             ingresos_por_metodo, gastos_por_categoria, fecha_inicio, fecha_fin)
    else:
        return render_template('informes/financiero.html',
                              ingresos=ingresos,
                              gastos=gastos,
                              total_ingresos=total_ingresos,
                              total_gastos=total_gastos,
                              balance=balance,
                              ingresos_por_metodo=ingresos_por_metodo,
                              gastos_por_categoria=gastos_por_categoria,
                              fecha_inicio=fecha_inicio,
                              fecha_fin=fecha_fin,
                              now=datetime.now)

def generar_csv_reservas(reservas):
    """Generar archivo CSV con el informe de reservas"""
    output = BytesIO()
    writer = csv.writer(output)
    
    # Cabeceras
    writer.writerow(['ID', 'Propiedad', 'Huésped', 'Entrada', 'Salida', 'Noches', 
                     'Huéspedes', 'Precio Total', 'Pagado', 'Pendiente', 'Estado'])
    
    # Datos
    for r in reservas:
        noches = (r.fecha_salida - r.fecha_entrada).days
        writer.writerow([
            r.id,
            r.propiedad.nombre,
            f"{r.huesped_nombre} {r.huesped_apellidos}",
            r.fecha_entrada,
            r.fecha_salida,
            noches,
            r.num_huespedes,
            r.precio_total,
            r.deposito_pagado,
            r.saldo_pendiente,
            r.estado
        ])
    
    output.seek(0)
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'reservas_{datetime.now().strftime("%Y%m%d")}.csv'
    )

def generar_csv_financiero(ingresos, gastos, fecha_inicio, fecha_fin):
    """Generar CSV con informe financiero"""
    output = BytesIO()
    writer = csv.writer(output)
    
    writer.writerow(['INFORME FINANCIERO', f'{fecha_inicio} - {fecha_fin}'])
    writer.writerow([])
    
    writer.writerow(['INGRESOS'])
    writer.writerow(['Fecha', 'Propiedad', 'Concepto', 'Método', 'Cantidad'])
    for i in ingresos:
        writer.writerow([i.fecha, i.propiedad.nombre if i.propiedad else 'General', 
                        i.concepto, i.metodo_pago, i.cantidad])
    
    total_ingresos = sum(i.cantidad for i in ingresos)
    writer.writerow(['', '', '', 'TOTAL INGRESOS', total_ingresos])
    writer.writerow([])
    
    writer.writerow(['GASTOS'])
    writer.writerow(['Fecha', 'Propiedad', 'Concepto', 'Categoría', 'Cantidad'])
    for g in gastos:
        writer.writerow([g.fecha, g.propiedad.nombre if g.propiedad else 'General',
                        g.concepto, g.categoria, g.cantidad])
    
    total_gastos = sum(g.cantidad for g in gastos)
    writer.writerow(['', '', '', 'TOTAL GASTOS', total_gastos])
    writer.writerow([])
    writer.writerow(['BALANCE', total_ingresos - total_gastos])
    
    output.seek(0)
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'financiero_{datetime.now().strftime("%Y%m%d")}.csv'
    )

def generar_pdf_informe_reservas(reservas, fecha_inicio, fecha_fin, propiedad_id):
    """Generar PDF con informe de reservas"""
    try:
        from weasyprint import HTML
        
        html = render_template('informes/reservas_pdf.html',
                              reservas=reservas,
                              fecha_inicio=fecha_inicio,
                              fecha_fin=fecha_fin,
                              now=datetime.now)
        
        pdf = HTML(string=html).write_pdf()
        output = BytesIO(pdf)
        output.seek(0)
        return send_file(
            output,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'informe_reservas_{datetime.now().strftime("%Y%m%d")}.pdf'
        )
    except Exception as e:
        print(f"Error generando PDF: {e}")
        return render_template('informes/reservas.html',
                              reservas=reservas,
                              fecha_inicio=fecha_inicio,
                              fecha_fin=fecha_fin,
                              propiedad_id=propiedad_id,
                              error_pdf=str(e),
                              now=datetime.now)

def generar_pdf_informe_financiero(ingresos, gastos, total_ingresos, total_gastos, balance,
                                  ingresos_por_metodo, gastos_por_categoria, fecha_inicio, fecha_fin):
    """Generar PDF con informe financiero"""
    try:
        from weasyprint import HTML
        
        html = render_template('informes/financiero_pdf.html',
                              ingresos=ingresos,
                              gastos=gastos,
                              total_ingresos=total_ingresos,
                              total_gastos=total_gastos,
                              balance=balance,
                              ingresos_por_metodo=ingresos_por_metodo,
                              gastos_por_categoria=gastos_por_categoria,
                              fecha_inicio=fecha_inicio,
                              fecha_fin=fecha_fin,
                              now=datetime.now)
        
        pdf = HTML(string=html).write_pdf()
        output = BytesIO(pdf)
        output.seek(0)
        return send_file(
            output,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'informe_financiero_{datetime.now().strftime("%Y%m%d")}.pdf'
        )
    except Exception as e:
        print(f"Error generando PDF: {e}")
        return render_template('informes/financiero.html',
                              ingresos=ingresos,
                              gastos=gastos,
                              total_ingresos=total_ingresos,
                              total_gastos=total_gastos,
                              balance=balance,
                              ingresos_por_metodo=ingresos_por_metodo,
                              gastos_por_categoria=gastos_por_categoria,
                              fecha_inicio=fecha_inicio,
                              fecha_fin=fecha_fin,
                              error_pdf=str(e),
                              now=datetime.now)