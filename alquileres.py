from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, Inquilino, Contrato, Propiedad, ReciboAlquiler, ContadorSuministro, LecturaContador
from datetime import datetime, date

alquileres_bp = Blueprint('alquileres', __name__, url_prefix='/alquileres')


# ============================================
# LISTADO CONTRATOS
# ============================================
@alquileres_bp.route('/')
def index():
    contratos = Contrato.query.order_by(Contrato.id.desc()).all()
    return render_template('alquileres/index.html', contratos=contratos)


# ============================================
# LISTADO RECIBOS
# ============================================
@alquileres_bp.route('/recibos')
def recibos():
    recibos = ReciboAlquiler.query.order_by(ReciboAlquiler.id.desc()).all()
    return render_template('alquileres/recibos.html', recibos=recibos)


# ============================================
# NUEVO INQUILINO
# ============================================
@alquileres_bp.route('/inquilino/nuevo', methods=['GET', 'POST'])
def nuevo_inquilino():
    if request.method == 'POST':
        inquilino = Inquilino(
            nombre=request.form.get('nombre'),
            apellidos=request.form.get('apellidos'),
            dni=request.form.get('dni'),
            telefono=request.form.get('telefono'),
            email=request.form.get('email')
        )

        db.session.add(inquilino)
        db.session.commit()

        flash('Inquilino creado correctamente', 'success')
        return redirect(url_for('alquileres.index'))

    return render_template('alquileres/nuevo_inquilino.html')

# ============================================
# NUEVO CONTRATO
# ============================================
@alquileres_bp.route('/contrato/nuevo', methods=['GET', 'POST'])
def nuevo_contrato():
    propiedades = Propiedad.query.all()
    inquilinos = Inquilino.query.all()

    if request.method == 'POST':
        contrato = Contrato(
            propiedad_id=request.form.get('propiedad_id'),
            inquilino_id=request.form.get('inquilino_id'),
            fecha_inicio=datetime.strptime(request.form.get('fecha_inicio'), '%Y-%m-%d').date(),
            fecha_fin=datetime.strptime(request.form.get('fecha_fin'), '%Y-%m-%d').date() if request.form.get('fecha_fin') else None,
            renta_mensual=float(request.form.get('renta_mensual')),
            fianza=float(request.form.get('fianza') or 0),
            estado=request.form.get('estado') or 'activo'
        )

        db.session.add(contrato)
        db.session.commit()

        flash('Contrato creado correctamente', 'success')
        return redirect(url_for('alquileres.index'))

    return render_template('alquileres/nuevo_contrato.html', propiedades=propiedades, inquilinos=inquilinos)


# ============================================
# VER CONTRATO
# ============================================
@alquileres_bp.route('/contrato/<int:id>')
def ver_contrato(id):
    contrato = Contrato.query.get_or_404(id)
    return render_template('alquileres/ver_contrato.html', contrato=contrato)


# ============================================
# GENERAR RECIBO
# ============================================
@alquileres_bp.route('/contrato/<int:contrato_id>/recibo/nuevo', methods=['GET', 'POST'])
def nuevo_recibo(contrato_id):
    contrato = Contrato.query.get_or_404(contrato_id)

    periodo_actual = date.today().strftime('%Y-%m')

    # Buscar lecturas del contrato para el período actual o el elegido
    periodo = request.form.get('periodo') if request.method == 'POST' else periodo_actual

    lecturas_periodo = []
    importe_agua = 0
    importe_luz = 0

    for lectura in contrato.lecturas_contador:
        if lectura.fecha_lectura.strftime('%Y-%m') == periodo:
            lecturas_periodo.append(lectura)
            if lectura.contador.tipo == 'agua':
                importe_agua += lectura.importe_total or 0
            elif lectura.contador.tipo == 'luz':
                importe_luz += lectura.importe_total or 0

    if request.method == 'POST':
        existe = ReciboAlquiler.query.filter_by(
            contrato_id=contrato.id,
            periodo=periodo
        ).first()

        if existe:
            flash('Ya existe un recibo para ese período', 'warning')
            return redirect(url_for('alquileres.ver_contrato', id=contrato.id))

        recibo = ReciboAlquiler(
            contrato_id=contrato.id,
            fecha_emision=date.today(),
            periodo=periodo,
            concepto=request.form.get('concepto') or 'Alquiler mensual',
            importe_base=float(request.form.get('importe_base') or 0),
            importe_agua=float(request.form.get('importe_agua') or 0),
            importe_luz=float(request.form.get('importe_luz') or 0),
            otros_importes=float(request.form.get('otros_importes') or 0),
            observaciones=request.form.get('observaciones')
        )

        recibo.calcular_total()

        db.session.add(recibo)
        db.session.commit()

        flash('Recibo generado correctamente', 'success')
        return redirect(url_for('alquileres.ver_contrato', id=contrato.id))

    return render_template(
        'alquileres/nuevo_recibo.html',
        contrato=contrato,
        periodo_actual=periodo_actual,
        lecturas_periodo=lecturas_periodo,
        importe_agua=importe_agua,
        importe_luz=importe_luz
    )


# ============================================
# MARCAR RECIBO COMO PAGADO
# ============================================
@alquileres_bp.route('/recibo/<int:id>/pagar', methods=['POST'])
def pagar_recibo(id):
    recibo = ReciboAlquiler.query.get_or_404(id)

    recibo.estado = 'pagado'
    recibo.fecha_pago = date.today()
    recibo.metodo_pago = request.form.get('metodo_pago') or 'transferencia'

    db.session.commit()

    flash('Recibo marcado como pagado', 'success')
    return redirect(url_for('alquileres.recibos'))


# ============================================
# LISTADO CONTADORES
# ============================================
@alquileres_bp.route('/contadores')
def contadores():
    contadores = ContadorSuministro.query.order_by(ContadorSuministro.id.desc()).all()
    return render_template('alquileres/contadores.html', contadores=contadores)


# ============================================
# NUEVO CONTADOR
# ============================================
@alquileres_bp.route('/contador/nuevo', methods=['GET', 'POST'])
def nuevo_contador():
    propiedades = Propiedad.query.all()

    if request.method == 'POST':
        contador = ContadorSuministro(
            propiedad_id=request.form.get('propiedad_id'),
            tipo=request.form.get('tipo'),
            nombre=request.form.get('nombre'),
            numero_serie=request.form.get('numero_serie'),
            activo=True if request.form.get('activo') == 'on' else False
        )

        db.session.add(contador)
        db.session.commit()

        flash('Contador creado correctamente', 'success')
        return redirect(url_for('alquileres.contadores'))

    return render_template('alquileres/nuevo_contador.html', propiedades=propiedades)


# ============================================
# LISTADO LECTURAS
# ============================================
@alquileres_bp.route('/lecturas')
def lecturas():
    lecturas = LecturaContador.query.order_by(LecturaContador.id.desc()).all()
    return render_template('alquileres/lecturas.html', lecturas=lecturas)


# ============================================
# NUEVA LECTURA
# ============================================
@alquileres_bp.route('/lectura/nueva', methods=['GET', 'POST'])
def nueva_lectura():
    contadores = ContadorSuministro.query.filter_by(activo=True).all()
    contratos = Contrato.query.filter_by(estado='activo').all()

    if request.method == 'POST':
        lectura = LecturaContador(
            contador_id=request.form.get('contador_id'),
            contrato_id=request.form.get('contrato_id') or None,
            fecha_lectura=datetime.strptime(request.form.get('fecha_lectura'), '%Y-%m-%d').date(),
            lectura_anterior=float(request.form.get('lectura_anterior') or 0),
            lectura_actual=float(request.form.get('lectura_actual') or 0),
            precio_unitario=float(request.form.get('precio_unitario') or 0),
            observaciones=request.form.get('observaciones')
        )

        lectura.calcular_consumo()

        db.session.add(lectura)
        db.session.commit()

        flash('Lectura guardada correctamente', 'success')
        return redirect(url_for('alquileres.lecturas'))

    return render_template('alquileres/nueva_lectura.html', contadores=contadores, contratos=contratos)
