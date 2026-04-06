from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, Response, current_app, jsonify
from flask_login import login_required, current_user
from flask_mail import Message

from models import db, Recibo, ReciboLinea, Propiedad, Contrato, Inquilino, LecturaContador, Ingreso

recibos_bp = Blueprint('recibos', __name__, url_prefix='/recibos')

ESTADOS_RECIBO = ['pendiente', 'pagado', 'impagado', 'reclamado']
METODOS_ABONO = ['transferencia', 'efectivo', 'tarjeta', 'bizum', 'domiciliacion']
TIPOS_RECIBO = ['manual', 'alquiler', 'suministro', 'mixto', 'otro']


def _propiedades_usuario():
    return Propiedad.query.filter_by(usuario_id=current_user.id).order_by(Propiedad.nombre.asc()).all()


def _ids_propiedades_usuario():
    return [p.id for p in _propiedades_usuario()]


def _recibo_permitido(recibo):
    return recibo and recibo.propiedad and recibo.propiedad.usuario_id == current_user.id


def _contratos_usuario():
    ids = _ids_propiedades_usuario()
    if not ids:
        return []
    return Contrato.query.filter(Contrato.propiedad_id.in_(ids)).order_by(Contrato.id.desc()).all()


def _inquilinos_usuario():
    contratos = _contratos_usuario()
    ids = sorted({c.inquilino_id for c in contratos if c.inquilino_id})
    if not ids:
        return []
    return Inquilino.query.filter(Inquilino.id.in_(ids)).order_by(Inquilino.nombre.asc(), Inquilino.apellidos.asc()).all()


def _numero_recibo():
    hoy = date.today()
    prefijo = f"R-{hoy.year}-"
    ultimo = Recibo.query.filter(Recibo.numero.like(f"{prefijo}%")).order_by(Recibo.id.desc()).first()
    siguiente = 1
    if ultimo and ultimo.numero:
        try:
            siguiente = int(ultimo.numero.split('-')[-1]) + 1
        except Exception:
            siguiente = 1
    return f"{prefijo}{siguiente:05d}"


def _parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, '%Y-%m-%d').date()


def _lineas_desde_form(recibo, form):
    conceptos = form.getlist('linea_concepto[]')
    tipos = form.getlist('linea_tipo[]')
    cantidades = form.getlist('linea_cantidad[]')
    precios = form.getlist('linea_precio[]')
    observaciones = form.getlist('linea_observaciones[]')

    for i, concepto in enumerate(conceptos):
        if not (concepto or '').strip():
            continue

        linea = ReciboLinea(
            recibo=recibo,
            tipo=(tipos[i] or 'otro'),
            concepto=concepto.strip(),
            cantidad=float(cantidades[i] or 0),
            precio_unitario=float(precios[i] or 0),
            observaciones=observaciones[i] if i < len(observaciones) else None,
        )
        linea.calcular()
        db.session.add(linea)


def _recalcular_y_guardar(recibo):
    recibo.recalcular()
    db.session.commit()


def _crear_o_actualizar_ingreso(recibo):
    if recibo.estado != 'pagado':
        return

    concepto = f"Pago recibo {recibo.numero or recibo.id}"
    if recibo.lineas.count() == 1:
        primera = recibo.lineas.first()
        concepto = primera.concepto

    ingreso = recibo.ingreso_generado

    if ingreso is None:
        ingreso = Ingreso(
            propiedad_id=recibo.propiedad_id,
            contrato_id=recibo.contrato_id,
            recibo_id=recibo.id,
            fecha=recibo.fecha_pago or date.today(),
            concepto=concepto,
            cantidad=recibo.total or 0,
            moneda='EUR',
            metodo_pago=recibo.metodo_pago or 'transferencia',
            observaciones=f"Ingreso generado automáticamente desde recibo {recibo.numero or recibo.id}"
        )
        db.session.add(ingreso)
    else:
        ingreso.propiedad_id = recibo.propiedad_id
        ingreso.contrato_id = recibo.contrato_id
        ingreso.fecha = recibo.fecha_pago or date.today()
        ingreso.concepto = concepto
        ingreso.cantidad = recibo.total or 0
        ingreso.metodo_pago = recibo.metodo_pago or ingreso.metodo_pago or 'transferencia'

    db.session.commit()


def _borrar_ingreso_si_existe(recibo):
    if recibo.ingreso_generado:
        db.session.delete(recibo.ingreso_generado)
        db.session.commit()


def _datos_emisor():
    nombre = (current_user.nombre or '').strip()
    apellidos = (current_user.apellidos or '').strip()
    nombre_completo = f"{nombre} {apellidos}".strip() or current_user.username

    return {
        'nombre': nombre_completo,
        'email': current_user.email or '',
        'usuario': current_user.username or ''
    }


def _texto_recibo(recibo):
    emisor = _datos_emisor()
    lineas = []
    for l in recibo.lineas:
        lineas.append(f"- {l.concepto}: {l.cantidad} x {l.precio_unitario:.2f} = {l.importe:.2f} EUR")

    propiedad = recibo.propiedad.nombre if recibo.propiedad else '-'
    inquilino = '-'
    if recibo.inquilino:
        inquilino = f"{recibo.inquilino.nombre} {recibo.inquilino.apellidos}"

    return f"""RECIBO {recibo.numero or recibo.id}

EMISOR
Nombre: {emisor['nombre']}
Email: {emisor['email']}
Usuario: {emisor['usuario']}

DATOS DEL RECIBO
Fecha emisión: {recibo.fecha_emision}
Vencimiento: {recibo.fecha_vencimiento or '-'}
Propiedad: {propiedad}
Contrato: {recibo.contrato.id if recibo.contrato else '-'}
Inquilino: {inquilino}
Situación: {recibo.estado}
Método de abono: {recibo.metodo_pago or '-'}

LÍNEAS
{chr(10).join(lineas)}

Subtotal: {recibo.subtotal:.2f} EUR
Impuestos: {recibo.impuestos:.2f} EUR
Total: {recibo.total:.2f} EUR

INSTRUCCIONES DE PAGO
{recibo.instrucciones_pago or '-'}

OBSERVACIONES
{recibo.observaciones or '-'}

{recibo.leyenda_legal}
"""


@recibos_bp.route('/')
@login_required
def index():
    ids = _ids_propiedades_usuario()
    if not ids:
        return render_template(
            'recibos/index.html',
            recibos=[],
            propiedades=[],
            contratos=[],
            estados=ESTADOS_RECIBO,
            tipos=TIPOS_RECIBO
        )

    query = Recibo.query.filter(Recibo.propiedad_id.in_(ids))

    propiedad_id = request.args.get('propiedad_id', type=int)
    if propiedad_id:
        query = query.filter_by(propiedad_id=propiedad_id)

    contrato_id = request.args.get('contrato_id', type=int)
    if contrato_id:
        query = query.filter_by(contrato_id=contrato_id)

    estado = request.args.get('estado')
    if estado:
        query = query.filter_by(estado=estado)

    tipo = request.args.get('tipo')
    if tipo:
        query = query.filter_by(tipo=tipo)

    recibos = query.order_by(Recibo.fecha_emision.desc(), Recibo.id.desc()).all()

    return render_template(
        'recibos/index.html',
        recibos=recibos,
        propiedades=_propiedades_usuario(),
        contratos=_contratos_usuario(),
        estados=ESTADOS_RECIBO,
        tipos=TIPOS_RECIBO
    )


@recibos_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    propiedades = _propiedades_usuario()
    contratos = _contratos_usuario()
    inquilinos = _inquilinos_usuario()

    # 🔥 NUEVO: valores precargados
    contrato_id = request.args.get('contrato_id', type=int)
    propiedad_id = request.args.get('propiedad_id', type=int)
    inquilino_id = request.args.get('inquilino_id', type=int)
    importe = request.args.get('importe', type=float)

    if request.method == 'POST':
        propiedad_id = request.form.get('propiedad_id', type=int)
        if propiedad_id not in _ids_propiedades_usuario():
            abort(403)

        recibo = Recibo(
            propiedad_id=propiedad_id,
            contrato_id=request.form.get('contrato_id', type=int) or None,
            inquilino_id=request.form.get('inquilino_id', type=int) or None,
            numero=_numero_recibo(),
            fecha_emision=_parse_date(request.form.get('fecha_emision')) or date.today(),
            fecha_vencimiento=_parse_date(request.form.get('fecha_vencimiento')),
            tipo=request.form.get('tipo') or 'manual',
            estado=request.form.get('estado') or 'pendiente',
            impuestos=float(request.form.get('impuestos') or 0),
            metodo_pago=request.form.get('metodo_pago') or None,
            fecha_pago=_parse_date(request.form.get('fecha_pago')),
            observaciones=request.form.get('observaciones'),
            instrucciones_pago=request.form.get('instrucciones_pago'),
            leyenda_legal=request.form.get('leyenda_legal') or 'La mera tenencia o recepción de este recibo no acredita su pago.'
        )

        db.session.add(recibo)
        db.session.flush()

        _lineas_desde_form(recibo, request.form)
        db.session.commit()
        _recalcular_y_guardar(recibo)

        if recibo.estado == 'pagado':
            _crear_o_actualizar_ingreso(recibo)

        flash('Recibo creado correctamente', 'success')
        return redirect(url_for('recibos.ver', id=recibo.id))

    return render_template(
        'recibos/nuevo.html',
        propiedades=propiedades,
        contratos=contratos,
        inquilinos=inquilinos,
        estados=ESTADOS_RECIBO,
        metodos_abono=METODOS_ABONO,
        tipos_recibo=TIPOS_RECIBO,
        contrato_id=contrato_id,
        propiedad_id=propiedad_id,
        inquilino_id=inquilino_id,
        importe=importe
    )


@recibos_bp.route('/<int:id>')
@login_required
def ver(id):
    recibo = Recibo.query.get_or_404(id)
    if not _recibo_permitido(recibo):
        abort(403)

    return render_template(
        'recibos/ver.html',
        recibo=recibo,
        emisor=_datos_emisor()
    )


@recibos_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    recibo = Recibo.query.get_or_404(id)
    if not _recibo_permitido(recibo):
        abort(403)

    propiedades = _propiedades_usuario()
    contratos = _contratos_usuario()
    inquilinos = _inquilinos_usuario()

    if request.method == 'POST':
        propiedad_id = request.form.get('propiedad_id', type=int)
        if propiedad_id not in _ids_propiedades_usuario():
            abort(403)

        recibo.propiedad_id = propiedad_id
        recibo.contrato_id = request.form.get('contrato_id', type=int) or None
        recibo.inquilino_id = request.form.get('inquilino_id', type=int) or None
        recibo.fecha_emision = _parse_date(request.form.get('fecha_emision')) or recibo.fecha_emision
        recibo.fecha_vencimiento = _parse_date(request.form.get('fecha_vencimiento'))
        recibo.tipo = request.form.get('tipo') or recibo.tipo
        recibo.estado = request.form.get('estado') or recibo.estado
        recibo.impuestos = float(request.form.get('impuestos') or 0)
        recibo.metodo_pago = request.form.get('metodo_pago') or None
        recibo.fecha_pago = _parse_date(request.form.get('fecha_pago'))
        recibo.observaciones = request.form.get('observaciones')
        recibo.instrucciones_pago = request.form.get('instrucciones_pago')
        recibo.leyenda_legal = request.form.get('leyenda_legal') or recibo.leyenda_legal

        for linea in list(recibo.lineas):
            db.session.delete(linea)
        db.session.flush()

        _lineas_desde_form(recibo, request.form)
        db.session.commit()
        _recalcular_y_guardar(recibo)

        if recibo.estado == 'pagado':
            _crear_o_actualizar_ingreso(recibo)
        else:
            _borrar_ingreso_si_existe(recibo)

        flash('Recibo actualizado correctamente', 'success')
        return redirect(url_for('recibos.ver', id=recibo.id))

    return render_template(
        'recibos/editar.html',
        recibo=recibo,
        propiedades=propiedades,
        contratos=contratos,
        inquilinos=inquilinos,
        estados=ESTADOS_RECIBO,
        metodos_abono=METODOS_ABONO,
        tipos_recibo=TIPOS_RECIBO
    )


@recibos_bp.route('/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar(id):
    recibo = Recibo.query.get_or_404(id)
    if not _recibo_permitido(recibo):
        abort(403)

    _borrar_ingreso_si_existe(recibo)
    db.session.delete(recibo)
    db.session.commit()
    flash('Recibo eliminado correctamente', 'success')
    return redirect(url_for('recibos.index'))


@recibos_bp.route('/<int:id>/pagar', methods=['POST'])
@login_required
def pagar(id):
    recibo = Recibo.query.get_or_404(id)
    if not _recibo_permitido(recibo):
        abort(403)

    recibo.estado = 'pagado'
    recibo.fecha_pago = date.today()
    recibo.metodo_pago = request.form.get('metodo_pago') or recibo.metodo_pago or 'transferencia'
    db.session.commit()

    _crear_o_actualizar_ingreso(recibo)

    flash('Recibo marcado como pagado', 'success')
    return redirect(url_for('recibos.index'))


@recibos_bp.route('/<int:id>/deshacer-pago', methods=['POST'])
@login_required
def deshacer_pago(id):
    recibo = Recibo.query.get_or_404(id)
    if not _recibo_permitido(recibo):
        abort(403)

    recibo.estado = 'pendiente'
    recibo.fecha_pago = None
    recibo.metodo_pago = None
    db.session.commit()

    _borrar_ingreso_si_existe(recibo)

    flash('Pago deshecho correctamente', 'success')
    return redirect(url_for('recibos.index'))


@recibos_bp.route('/generar-desde-lectura/<int:lectura_id>', methods=['POST'])
@login_required
def generar_desde_lectura(lectura_id):
    lectura = LecturaContador.query.get_or_404(lectura_id)
    if not lectura.contador or not lectura.contador.propiedad or lectura.contador.propiedad.usuario_id != current_user.id:
        abort(403)

    contrato = lectura.contrato
    inquilino = contrato.inquilino if contrato else None

    recibo = Recibo(
        propiedad_id=lectura.contador.propiedad_id,
        contrato_id=contrato.id if contrato else None,
        inquilino_id=inquilino.id if inquilino else None,
        numero=_numero_recibo(),
        fecha_emision=date.today(),
        tipo='suministro',
        estado='pendiente',
        observaciones=f'Generado automáticamente desde lectura #{lectura.id}',
        instrucciones_pago='Pago por transferencia o el medio pactado.',
        origen='lectura',
        referencia_origen_id=lectura.id,
        enviado_email=False,
        enviado_whatsapp=False
    )
    db.session.add(recibo)
    db.session.flush()

    linea = ReciboLinea(
        recibo_id=recibo.id,
        tipo='suministro',
        concepto=f'{lectura.contador.tipo.capitalize()} - lectura {lectura.fecha_lectura}',
        cantidad=lectura.consumo or 0,
        precio_unitario=lectura.precio_unitario or 0,
        referencia_origen='lectura_contador',
        referencia_origen_id=lectura.id,
        observaciones=lectura.observaciones
    )
    linea.calcular()
    db.session.add(linea)
    db.session.commit()

    _recalcular_y_guardar(recibo)

    flash('Recibo generado desde la lectura correctamente', 'success')
    return redirect(url_for('recibos.ver', id=recibo.id))


@recibos_bp.route('/<int:id>/exportar')
@login_required
def exportar(id):
    recibo = Recibo.query.get_or_404(id)
    if not _recibo_permitido(recibo):
        abort(403)

    contenido = _texto_recibo(recibo)
    return Response(
        contenido,
        mimetype='text/plain; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename=recibo_{recibo.numero or recibo.id}.txt'}
    )


@recibos_bp.route('/<int:id>/email', methods=['POST'])
@login_required
def enviar_email(id):
    recibo = Recibo.query.get_or_404(id)
    if not _recibo_permitido(recibo):
        abort(403)

    if not recibo.inquilino or not recibo.inquilino.email:
        flash('El recibo no tiene un inquilino con email definido', 'warning')
        return redirect(url_for('recibos.ver', id=recibo.id))

    try:
        send_email_for_user(
            current_user,
            subject=f'Recibo {recibo.numero or recibo.id}',
            recipients=[recibo.inquilino.email],
            body=_texto_recibo(recibo)
        )

        recibo.enviado_email = True
        db.session.commit()

        flash('Recibo enviado por email correctamente', 'success')

    except Exception as e:
        flash(f'No se pudo enviar el email: {e}', 'danger')

    return redirect(url_for('recibos.ver', id=recibo.id))


@recibos_bp.route('/<int:id>/whatsapp')
@login_required
def enviar_whatsapp(id):
    recibo = Recibo.query.get_or_404(id)
    if not _recibo_permitido(recibo):
        abort(403)

    recibo.enviado_whatsapp = True
    db.session.commit()

    texto = _texto_recibo(recibo).replace('\n', '%0A')
    return redirect(f'https://wa.me/?text={texto}')


@recibos_bp.route('/contrato/<int:contrato_id>/datos')
@login_required
def datos_contrato(contrato_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    if contrato.propiedad_id not in _ids_propiedades_usuario():
        abort(403)

    inquilino = contrato.inquilino
    propiedad = contrato.propiedad

    return jsonify({
        'contrato_id': contrato.id,
        'propiedad_id': propiedad.id if propiedad else None,
        'propiedad_nombre': propiedad.nombre if propiedad else '',
        'inquilino_id': inquilino.id if inquilino else None,
        'inquilino_nombre': f"{inquilino.nombre} {inquilino.apellidos}" if inquilino else '',
        'renta_mensual': contrato.renta_mensual or 0
    })