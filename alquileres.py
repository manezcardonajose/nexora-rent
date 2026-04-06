from datetime import datetime, date

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from models import (
    db,
    Propiedad,
    Inquilino,
    Contrato,
    ContadorSuministro,
    LecturaContador,
    Recibo,
    ReciboLinea,
    Ingreso,
    Reserva
)

alquileres_bp = Blueprint('alquileres', __name__, url_prefix='/alquileres')


# ======================================================
# UTILIDADES
# ======================================================

def _propiedades_usuario():
    return Propiedad.query.filter_by(usuario_id=current_user.id).order_by(Propiedad.nombre.asc()).all()


def _ids_propiedades_usuario():
    return [p.id for p in _propiedades_usuario()]


def _contrato_permitido(contrato):
    return contrato and contrato.propiedad and contrato.propiedad.usuario_id == current_user.id


def _contador_permitido(contador):
    return contador and contador.propiedad and contador.propiedad.usuario_id == current_user.id


def _lectura_permitida(lectura):
    return lectura and lectura.contador and lectura.contador.propiedad and lectura.contador.propiedad.usuario_id == current_user.id


def _recibo_permitido(recibo):
    return recibo and recibo.propiedad and recibo.propiedad.usuario_id == current_user.id


def obtener_reserva_solapada(propiedad_id, inicio, fin, reserva_id_excluir=None):
    q = Reserva.query.filter(
        Reserva.propiedad_id == propiedad_id,
        Reserva.estado != 'cancelada',
        Reserva.fecha_entrada < fin,
        Reserva.fecha_salida > inicio
    ).order_by(Reserva.fecha_entrada.asc())

    if reserva_id_excluir:
        q = q.filter(Reserva.id != reserva_id_excluir)

    return q.first()


def hay_reserva_solapada(propiedad_id, inicio, fin, reserva_id_excluir=None):
    return obtener_reserva_solapada(propiedad_id, inicio, fin, reserva_id_excluir=reserva_id_excluir) is not None


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


def _crear_ingreso_desde_recibo(recibo):
    if recibo.estado != 'pagado':
        return

    ingreso = Ingreso.query.filter_by(recibo_id=recibo.id).first()

    concepto = f"Pago recibo {recibo.numero or recibo.id}"
    primera_linea = recibo.lineas.first()
    if primera_linea:
        concepto = primera_linea.concepto

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
            observaciones=f'Generado automáticamente desde recibo {recibo.numero or recibo.id}'
        )
        db.session.add(ingreso)
    else:
        ingreso.propiedad_id = recibo.propiedad_id
        ingreso.contrato_id = recibo.contrato_id
        ingreso.fecha = recibo.fecha_pago or date.today()
        ingreso.concepto = concepto
        ingreso.cantidad = recibo.total or 0
        ingreso.metodo_pago = recibo.metodo_pago or 'transferencia'

    db.session.commit()


def _borrar_ingreso_recibo(recibo):
    ingreso = Ingreso.query.filter_by(recibo_id=recibo.id).first()
    if ingreso:
        db.session.delete(ingreso)
        db.session.commit()


# ======================================================
# PANEL
# ======================================================

@alquileres_bp.route('/')
@login_required
def index():
    ids = _ids_propiedades_usuario()

    contratos = Contrato.query.filter(Contrato.propiedad_id.in_(ids)).order_by(Contrato.id.desc()).all() if ids else []
    lecturas = (
        LecturaContador.query.join(ContadorSuministro)
        .filter(ContadorSuministro.propiedad_id.in_(ids))
        .order_by(LecturaContador.fecha_lectura.desc(), LecturaContador.id.desc())
        .all()
        if ids else []
    )
    contadores = ContadorSuministro.query.filter(ContadorSuministro.propiedad_id.in_(ids)).order_by(ContadorSuministro.id.desc()).all() if ids else []

    return render_template(
        'alquileres/index.html',
        contratos=contratos,
        lecturas=lecturas,
        contadores=contadores
    )


# ======================================================
# INQUILINOS
# ======================================================

@alquileres_bp.route('/inquilinos')
@login_required
def inquilinos():
    lista = Inquilino.query.order_by(Inquilino.nombre.asc(), Inquilino.apellidos.asc()).all()
    return render_template('alquileres/inquilinos.html', inquilinos=lista)


@alquileres_bp.route('/inquilinos/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_inquilino():
    if request.method == 'POST':
        fecha_nacimiento = None
        if request.form.get('fecha_nacimiento'):
            fecha_nacimiento = datetime.strptime(
                request.form.get('fecha_nacimiento'),
                '%Y-%m-%d'
            ).date()

        inquilino = Inquilino(
            nombre=request.form.get('nombre'),
            apellidos=request.form.get('apellidos') or '',
            dni=request.form.get('dni'),
            nacionalidad=request.form.get('nacionalidad'),
            telefono=request.form.get('telefono'),
            email=request.form.get('email'),
            direccion=request.form.get('direccion'),
            codigo_postal=request.form.get('codigo_postal'),
            municipio=request.form.get('municipio'),
            provincia=request.form.get('provincia'),
            fecha_nacimiento=fecha_nacimiento,
            estado_civil=request.form.get('estado_civil')
        )
        db.session.add(inquilino)
        db.session.commit()
        flash('Inquilino creado correctamente', 'success')
        return redirect(url_for('alquileres.inquilinos'))

    return render_template('alquileres/nuevo_inquilino.html')


@alquileres_bp.route('/inquilinos/<int:id>')
@login_required
def ver_inquilino(id):
    inquilino = Inquilino.query.get_or_404(id)
    return render_template('alquileres/ver_inquilino.html', inquilino=inquilino)

@alquileres_bp.route('/inquilinos/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_inquilino(id):
    inquilino = Inquilino.query.get_or_404(id)

    if request.method == 'POST':
        fecha_nacimiento = None
        if request.form.get('fecha_nacimiento'):
            fecha_nacimiento = datetime.strptime(
                request.form.get('fecha_nacimiento'),
                '%Y-%m-%d'
            ).date()

        inquilino.nombre = request.form.get('nombre')
        inquilino.apellidos = request.form.get('apellidos') or ''
        inquilino.dni = request.form.get('dni')
        inquilino.nacionalidad = request.form.get('nacionalidad')
        inquilino.telefono = request.form.get('telefono')
        inquilino.email = request.form.get('email')
        inquilino.direccion = request.form.get('direccion')
        inquilino.codigo_postal = request.form.get('codigo_postal')
        inquilino.municipio = request.form.get('municipio')
        inquilino.provincia = request.form.get('provincia')
        inquilino.fecha_nacimiento = fecha_nacimiento
        inquilino.estado_civil = request.form.get('estado_civil')

        db.session.commit()
        flash('Inquilino actualizado correctamente', 'success')
        return redirect(url_for('alquileres.inquilinos'))

    return render_template('alquileres/editar_inquilino.html', inquilino=inquilino)

@alquileres_bp.route('/inquilinos/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_inquilino(id):
    inquilino = Inquilino.query.get_or_404(id)
    db.session.delete(inquilino)
    db.session.commit()
    flash('Inquilino eliminado correctamente', 'success')
    return redirect(url_for('alquileres.inquilinos'))


# ======================================================
# CONTRATOS
# ======================================================

@alquileres_bp.route('/contratos')
@login_required
def contratos():
    ids = _ids_propiedades_usuario()
    lista = Contrato.query.filter(Contrato.propiedad_id.in_(ids)).order_by(Contrato.id.desc()).all() if ids else []
    return render_template('alquileres/contratos.html', contratos=lista)


@alquileres_bp.route('/contratos/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_contrato():
    propiedades = _propiedades_usuario()
    inquilinos = Inquilino.query.order_by(Inquilino.nombre.asc(), Inquilino.apellidos.asc()).all()

    if request.method == 'POST':
        propiedad_id = request.form.get('propiedad_id', type=int)
        if propiedad_id not in _ids_propiedades_usuario():
            abort(403)

        fecha_inicio = datetime.strptime(request.form.get('fecha_inicio'), '%Y-%m-%d').date()
        fecha_fin = datetime.strptime(request.form.get('fecha_fin'), '%Y-%m-%d').date() if request.form.get('fecha_fin') else None
        fecha_fin_control = fecha_fin or date(2100, 1, 1)

        reserva_conflictiva = obtener_reserva_solapada(propiedad_id, fecha_inicio, fecha_fin_control)
        if reserva_conflictiva:
            flash(
                f'No se puede crear contrato de larga duración. La propiedad tiene una reserva vacacional del {reserva_conflictiva.fecha_entrada:%d/%m/%Y} al {reserva_conflictiva.fecha_salida:%d/%m/%Y}.',
                'danger'
            )
            return render_template('alquileres/nuevo_contrato.html', propiedades=propiedades, inquilinos=inquilinos)

        contrato = Contrato(
            propiedad_id=propiedad_id,
            inquilino_id=request.form.get('inquilino_id', type=int),
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            renta_mensual=float(request.form.get('renta_mensual') or 0),
            fianza=float(request.form.get('fianza') or 0),
            estado=request.form.get('estado') or 'activo'
        )
        db.session.add(contrato)
        db.session.commit()
        flash('Contrato creado correctamente', 'success')
        return redirect(url_for('contratos.editar_contrato', contrato_id=contrato.id))

    return render_template('alquileres/nuevo_contrato.html', propiedades=propiedades, inquilinos=inquilinos)


@alquileres_bp.route('/contratos/<int:id>')
@login_required
def ver_contrato(id):
    contrato = Contrato.query.get_or_404(id)
    if not _contrato_permitido(contrato):
        abort(403)
    return render_template('alquileres/ver_contrato.html', contrato=contrato)


@alquileres_bp.route('/contratos/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_contrato(id):
    contrato = Contrato.query.get_or_404(id)
    if not _contrato_permitido(contrato):
        abort(403)

    propiedades = _propiedades_usuario()
    inquilinos = Inquilino.query.order_by(Inquilino.nombre.asc(), Inquilino.apellidos.asc()).all()

    if request.method == 'POST':
        propiedad_id = request.form.get('propiedad_id', type=int)
        if propiedad_id not in _ids_propiedades_usuario():
            abort(403)

        fecha_inicio = datetime.strptime(request.form.get('fecha_inicio'), '%Y-%m-%d').date()
        fecha_fin = datetime.strptime(request.form.get('fecha_fin'), '%Y-%m-%d').date() if request.form.get('fecha_fin') else None
        fecha_fin_control = fecha_fin or date(2100, 1, 1)

        reserva_conflictiva = obtener_reserva_solapada(propiedad_id, fecha_inicio, fecha_fin_control)
        if reserva_conflictiva:
            flash(
                f'No se puede guardar el contrato. La propiedad tiene una reserva vacacional del {reserva_conflictiva.fecha_entrada:%d/%m/%Y} al {reserva_conflictiva.fecha_salida:%d/%m/%Y}.',
                'danger'
            )
            return render_template(
                'alquileres/editar_contrato.html',
                contrato=contrato,
                propiedades=propiedades,
                inquilinos=inquilinos
            )

        contrato.propiedad_id = propiedad_id
        contrato.inquilino_id = request.form.get('inquilino_id', type=int)
        contrato.fecha_inicio = fecha_inicio
        contrato.fecha_fin = fecha_fin
        contrato.renta_mensual = float(request.form.get('renta_mensual') or 0)
        contrato.fianza = float(request.form.get('fianza') or 0)
        contrato.estado = request.form.get('estado') or contrato.estado

        db.session.commit()
        flash('Contrato actualizado correctamente', 'success')
        return redirect(url_for('alquileres.ver_contrato', id=contrato.id))

    return render_template(
        'alquileres/editar_contrato.html',
        contrato=contrato,
        propiedades=propiedades,
        inquilinos=inquilinos
    )

@alquileres_bp.route('/contratos/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_contrato(id):
    contrato = Contrato.query.get_or_404(id)
    if not _contrato_permitido(contrato):
        abort(403)

    recibos_asociados = Recibo.query.filter_by(contrato_id=contrato.id).count()
    lecturas_asociadas = LecturaContador.query.filter_by(contrato_id=contrato.id).count()

    if recibos_asociados > 0 or lecturas_asociadas > 0:
        flash(
            'No se puede eliminar el contrato porque tiene recibos o lecturas de suministros asociadas. '
            'Finalízalo o elimina primero los registros relacionados.',
            'warning'
        )
        return redirect(url_for('alquileres.contratos'))

    db.session.delete(contrato)
    db.session.commit()
    flash('Contrato eliminado correctamente', 'success')
    return redirect(url_for('alquileres.contratos'))


# ======================================================
# CONTADORES
# ======================================================

@alquileres_bp.route('/contadores')
@login_required
def contadores():
    ids = _ids_propiedades_usuario()
    contadores = ContadorSuministro.query.filter(ContadorSuministro.propiedad_id.in_(ids)).order_by(ContadorSuministro.id.desc()).all() if ids else []
    return render_template('alquileres/contadores.html', contadores=contadores)


@alquileres_bp.route('/contadores/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_contador():
    propiedades = _propiedades_usuario()

    if request.method == 'POST':
        propiedad_id = request.form.get('propiedad_id', type=int)
        if propiedad_id not in _ids_propiedades_usuario():
            abort(403)

        contador = ContadorSuministro(
            propiedad_id=propiedad_id,
            tipo=request.form.get('tipo'),
            nombre=request.form.get('nombre'),
            numero_serie=request.form.get('numero_serie'),
            activo=True if request.form.get('activo') == '1' else False
        )
        db.session.add(contador)
        db.session.commit()
        flash('Contador creado correctamente', 'success')
        return redirect(url_for('alquileres.contadores'))

    return render_template('alquileres/nuevo_contador.html', propiedades=propiedades)


@alquileres_bp.route('/contadores/<int:id>')
@login_required
def ver_contador(id):
    contador = ContadorSuministro.query.get_or_404(id)
    if not _contador_permitido(contador):
        abort(403)
    return render_template('alquileres/ver_contador.html', contador=contador)


@alquileres_bp.route('/contadores/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_contador(id):
    contador = ContadorSuministro.query.get_or_404(id)
    if not _contador_permitido(contador):
        abort(403)

    propiedades = _propiedades_usuario()

    if request.method == 'POST':
        propiedad_id = request.form.get('propiedad_id', type=int)
        if propiedad_id not in _ids_propiedades_usuario():
            abort(403)

        contador.propiedad_id = propiedad_id
        contador.tipo = request.form.get('tipo')
        contador.nombre = request.form.get('nombre')
        contador.numero_serie = request.form.get('numero_serie')
        contador.activo = True if request.form.get('activo') == '1' else False

        db.session.commit()
        flash('Contador actualizado correctamente', 'success')
        return redirect(url_for('alquileres.contadores'))

    return render_template('alquileres/editar_contador.html', contador=contador, propiedades=propiedades)


@alquileres_bp.route('/contadores/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_contador(id):
    contador = ContadorSuministro.query.get_or_404(id)
    if not _contador_permitido(contador):
        abort(403)

    db.session.delete(contador)
    db.session.commit()
    flash('Contador eliminado correctamente', 'success')
    return redirect(url_for('alquileres.contadores'))


# ======================================================
# LECTURAS
# ======================================================

@alquileres_bp.route('/lecturas')
@login_required
def lecturas():
    ids = _ids_propiedades_usuario()
    lecturas = (
        LecturaContador.query.join(ContadorSuministro)
        .filter(ContadorSuministro.propiedad_id.in_(ids))
        .order_by(LecturaContador.fecha_lectura.desc(), LecturaContador.id.desc())
        .all()
        if ids else []
    )
    return render_template('alquileres/lecturas.html', lecturas=lecturas)


@alquileres_bp.route('/lecturas/nueva', methods=['GET', 'POST'])
@login_required
def nueva_lectura():
    ids = _ids_propiedades_usuario()
    contadores = ContadorSuministro.query.filter(ContadorSuministro.propiedad_id.in_(ids)).all() if ids else []
    contratos = Contrato.query.filter(Contrato.propiedad_id.in_(ids)).all() if ids else []

    if request.method == 'POST':
        contador_id = request.form.get('contador_id', type=int)
        contador = ContadorSuministro.query.get_or_404(contador_id)
        if not _contador_permitido(contador):
            abort(403)

        contrato_id = request.form.get('contrato_id', type=int) or None
        contrato = Contrato.query.get(contrato_id) if contrato_id else None
        if contrato and not _contrato_permitido(contrato):
            abort(403)

        lectura = LecturaContador(
            contador_id=contador_id,
            contrato_id=contrato_id,
            fecha_lectura=datetime.strptime(request.form.get('fecha_lectura'), '%Y-%m-%d').date() if request.form.get('fecha_lectura') else date.today(),
            lectura_anterior=float(request.form.get('lectura_anterior') or 0),
            lectura_actual=float(request.form.get('lectura_actual') or 0),
            precio_unitario=float(request.form.get('precio_unitario') or 0),
            observaciones=request.form.get('observaciones'),
        )
        lectura.calcular_consumo()
        db.session.add(lectura)
        db.session.commit()

        if request.form.get('generar_recibo') == '1':
            contrato = lectura.contrato
            inquilino = contrato.inquilino if contrato else None

            recibo = Recibo(
                propiedad_id=contador.propiedad_id,
                contrato_id=contrato.id if contrato else None,
                inquilino_id=inquilino.id if inquilino else None,
                numero=_numero_recibo(),
                fecha_emision=date.today(),
                tipo='suministro',
                estado='pendiente',
                subtotal=lectura.importe_total,
                total=lectura.importe_total,
                metodo_pago='transferencia',
                observaciones=f'Generado automáticamente desde lectura #{lectura.id}',
                instrucciones_pago='Pago por transferencia o el medio pactado.',
                origen='lectura',
                referencia_origen_id=lectura.id
            )
            db.session.add(recibo)
            db.session.flush()

            linea = ReciboLinea(
                recibo_id=recibo.id,
                tipo='suministro',
                concepto=f'{contador.tipo.capitalize()} - lectura {lectura.fecha_lectura}',
                cantidad=lectura.consumo or 0,
                precio_unitario=lectura.precio_unitario or 0,
                importe=lectura.importe_total or 0,
                referencia_origen='lectura_contador',
                referencia_origen_id=lectura.id,
                observaciones=lectura.observaciones
            )
            db.session.add(linea)
            db.session.commit()

        flash('Lectura guardada correctamente', 'success')
        return redirect(url_for('alquileres.lecturas'))

    return render_template('alquileres/nueva_lectura.html', contadores=contadores, contratos=contratos)


@alquileres_bp.route('/lecturas/<int:id>')
@login_required
def ver_lectura(id):
    lectura = LecturaContador.query.get_or_404(id)
    if not _lectura_permitida(lectura):
        abort(403)
    return render_template('alquileres/ver_lectura.html', lectura=lectura)


@alquileres_bp.route('/lecturas/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_lectura(id):
    lectura = LecturaContador.query.get_or_404(id)
    if not _lectura_permitida(lectura):
        abort(403)

    ids = _ids_propiedades_usuario()
    contadores = ContadorSuministro.query.filter(ContadorSuministro.propiedad_id.in_(ids)).all() if ids else []
    contratos = Contrato.query.filter(Contrato.propiedad_id.in_(ids)).all() if ids else []

    if request.method == 'POST':
        contador_id = request.form.get('contador_id', type=int)
        contador = ContadorSuministro.query.get_or_404(contador_id)
        if not _contador_permitido(contador):
            abort(403)

        contrato_id = request.form.get('contrato_id', type=int) or None
        contrato = Contrato.query.get(contrato_id) if contrato_id else None
        if contrato and not _contrato_permitido(contrato):
            abort(403)

        lectura.contador_id = contador_id
        lectura.contrato_id = contrato_id
        lectura.fecha_lectura = datetime.strptime(request.form.get('fecha_lectura'), '%Y-%m-%d').date()
        lectura.lectura_anterior = float(request.form.get('lectura_anterior') or 0)
        lectura.lectura_actual = float(request.form.get('lectura_actual') or 0)
        lectura.precio_unitario = float(request.form.get('precio_unitario') or 0)
        lectura.observaciones = request.form.get('observaciones')
        lectura.calcular_consumo()

        db.session.commit()
        flash('Lectura actualizada correctamente', 'success')
        return redirect(url_for('alquileres.lecturas'))

    return render_template('alquileres/editar_lectura.html', lectura=lectura, contadores=contadores, contratos=contratos)


@alquileres_bp.route('/lecturas/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_lectura(id):
    lectura = LecturaContador.query.get_or_404(id)
    if not _lectura_permitida(lectura):
        abort(403)

    db.session.delete(lectura)
    db.session.commit()
    flash('Lectura eliminada correctamente', 'success')
    return redirect(url_for('alquileres.lecturas'))


# ======================================================
# RECIBOS DESDE ALQUILERES
# ======================================================

@alquileres_bp.route('/recibos')
@login_required
def recibos():
    ids = _ids_propiedades_usuario()
    lista = Recibo.query.filter(Recibo.propiedad_id.in_(ids)).order_by(Recibo.fecha_emision.desc(), Recibo.id.desc()).all() if ids else []
    return render_template('alquileres/recibos.html', recibos=lista)


@alquileres_bp.route('/recibos/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_recibo():
    propiedades = _propiedades_usuario()
    ids = _ids_propiedades_usuario()
    contratos = Contrato.query.filter(Contrato.propiedad_id.in_(ids)).all() if ids else []
    inquilinos = Inquilino.query.order_by(Inquilino.nombre.asc(), Inquilino.apellidos.asc()).all()

    if request.method == 'POST':
        propiedad_id = request.form.get('propiedad_id', type=int)
        if propiedad_id not in ids:
            abort(403)

        recibo = Recibo(
            propiedad_id=propiedad_id,
            contrato_id=request.form.get('contrato_id', type=int) or None,
            inquilino_id=request.form.get('inquilino_id', type=int) or None,
            numero=_numero_recibo(),
            fecha_emision=datetime.strptime(request.form.get('fecha_emision'), '%Y-%m-%d').date() if request.form.get('fecha_emision') else date.today(),
            fecha_vencimiento=datetime.strptime(request.form.get('fecha_vencimiento'), '%Y-%m-%d').date() if request.form.get('fecha_vencimiento') else None,
            tipo='alquiler',
            estado=request.form.get('estado') or 'pendiente',
            metodo_pago=request.form.get('metodo_pago') or None,
            observaciones=request.form.get('observaciones'),
            instrucciones_pago='Pago por transferencia o el medio pactado.',
            leyenda_legal='La mera tenencia o recepción de este recibo no acredita su pago. Solo se considerará abonado cuando vaya acompañado del correspondiente justificante de pago.'
        )
        db.session.add(recibo)
        db.session.flush()

        importe = float(request.form.get('importe') or 0)
        concepto = request.form.get('concepto') or 'Recibo alquiler'

        linea = ReciboLinea(
            recibo_id=recibo.id,
            tipo='alquiler',
            concepto=concepto,
            cantidad=1,
            precio_unitario=importe,
            importe=importe,
            observaciones=request.form.get('observaciones')
        )
        db.session.add(linea)

        recibo.subtotal = importe
        recibo.total = importe

        db.session.commit()

        if recibo.estado == 'pagado':
            recibo.fecha_pago = date.today()
            db.session.commit()
            _crear_ingreso_desde_recibo(recibo)

        flash('Recibo creado correctamente', 'success')
        return redirect(url_for('alquileres.recibos'))

    return render_template('alquileres/nuevo_recibo.html', propiedades=propiedades, contratos=contratos, inquilinos=inquilinos)


@alquileres_bp.route('/recibos/<int:id>')
@login_required
def ver_recibo(id):
    recibo = Recibo.query.get_or_404(id)
    if not _recibo_permitido(recibo):
        abort(403)
    return render_template('alquileres/ver_recibo.html', recibo=recibo)


@alquileres_bp.route('/recibos/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_recibo(id):
    recibo = Recibo.query.get_or_404(id)
    if not _recibo_permitido(recibo):
        abort(403)

    propiedades = _propiedades_usuario()
    ids = _ids_propiedades_usuario()
    contratos = Contrato.query.filter(Contrato.propiedad_id.in_(ids)).all() if ids else []
    inquilinos = Inquilino.query.order_by(Inquilino.nombre.asc(), Inquilino.apellidos.asc()).all()

    if request.method == 'POST':
        propiedad_id = request.form.get('propiedad_id', type=int)
        if propiedad_id not in ids:
            abort(403)

        recibo.propiedad_id = propiedad_id
        recibo.contrato_id = request.form.get('contrato_id', type=int) or None
        recibo.inquilino_id = request.form.get('inquilino_id', type=int) or None
        recibo.fecha_emision = datetime.strptime(request.form.get('fecha_emision'), '%Y-%m-%d').date() if request.form.get('fecha_emision') else recibo.fecha_emision
        recibo.fecha_vencimiento = datetime.strptime(request.form.get('fecha_vencimiento'), '%Y-%m-%d').date() if request.form.get('fecha_vencimiento') else None
        recibo.estado = request.form.get('estado') or recibo.estado
        recibo.metodo_pago = request.form.get('metodo_pago') or None
        recibo.observaciones = request.form.get('observaciones')

        concepto = request.form.get('concepto') or 'Recibo alquiler'
        importe = float(request.form.get('importe') or 0)

        primera_linea = recibo.lineas.first()
        if primera_linea:
            primera_linea.concepto = concepto
            primera_linea.cantidad = 1
            primera_linea.precio_unitario = importe
            primera_linea.importe = importe
            primera_linea.observaciones = request.form.get('observaciones')

        recibo.subtotal = importe
        recibo.total = importe

        db.session.commit()

        if recibo.estado == 'pagado':
            recibo.fecha_pago = recibo.fecha_pago or date.today()
            db.session.commit()
            _crear_ingreso_desde_recibo(recibo)
        else:
            recibo.fecha_pago = None
            db.session.commit()
            _borrar_ingreso_recibo(recibo)

        flash('Recibo actualizado correctamente', 'success')
        return redirect(url_for('alquileres.recibos'))

    return render_template('alquileres/editar_recibo.html', recibo=recibo, propiedades=propiedades, contratos=contratos, inquilinos=inquilinos)


@alquileres_bp.route('/recibos/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_recibo(id):
    recibo = Recibo.query.get_or_404(id)
    if not _recibo_permitido(recibo):
        abort(403)

    _borrar_ingreso_recibo(recibo)
    db.session.delete(recibo)
    db.session.commit()
    flash('Recibo eliminado correctamente', 'success')
    return redirect(url_for('alquileres.recibos'))


@alquileres_bp.route('/recibos/<int:id>/pagar', methods=['POST'])
@login_required
def marcar_pagado_recibo(id):
    recibo = Recibo.query.get_or_404(id)
    if not _recibo_permitido(recibo):
        abort(403)

    recibo.estado = 'pagado'
    recibo.fecha_pago = date.today()
    recibo.metodo_pago = recibo.metodo_pago or 'transferencia'
    db.session.commit()

    _crear_ingreso_desde_recibo(recibo)

    flash('Recibo marcado como pagado', 'success')
    return redirect(url_for('alquileres.recibos'))


@alquileres_bp.route('/recibos/<int:id>/deshacer-pago', methods=['POST'])
@login_required
def deshacer_pago_recibo(id):
    recibo = Recibo.query.get_or_404(id)
    if not _recibo_permitido(recibo):
        abort(403)

    recibo.estado = 'pendiente'
    recibo.fecha_pago = None
    db.session.commit()

    _borrar_ingreso_recibo(recibo)

    flash('Pago deshecho correctamente', 'success')
    return redirect(url_for('alquileres.recibos'))