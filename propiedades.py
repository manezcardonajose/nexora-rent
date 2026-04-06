from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, Propiedad, Reserva
from forms import PropiedadForm
from datetime import datetime
from utils import log_audit
from permisos import propiedades_visibles_query, propiedad_es_visible, propiedad_es_editable, usuario_tiene_permiso

propiedades_bp = Blueprint('propiedades', __name__, url_prefix='/propiedades')


@propiedades_bp.route('/')
@login_required
def index():
    """Listado de propiedades visibles para el usuario"""
    propiedades = propiedades_visibles_query().order_by(Propiedad.fecha_creacion.desc()).all()
    return render_template('propiedades/index.html', propiedades=propiedades)


@propiedades_bp.route('/nueva', methods=['GET', 'POST'])
@login_required
def nueva():
    """Crear una nueva propiedad"""
    if not usuario_tiene_permiso('puede_gestionar_propiedades'):
        flash('No tienes permisos para crear propiedades.', 'danger')
        return redirect(url_for('propiedades.index'))

    form = PropiedadForm()

    if form.validate_on_submit():
        if not current_user.puede_crear_propiedad():
            flash('Has alcanzado el límite de propiedades de tu plan.', 'warning')
            return redirect(url_for('propiedades.index'))

        propiedad = Propiedad(
            nombre=form.nombre.data,
            descripcion=form.descripcion.data,

            tipo_inmueble=request.form.get("tipo_inmueble"),
            referencia_catastral=request.form.get("referencia_catastral"),
            municipio=request.form.get("municipio"),

            direccion=form.direccion.data,
            ciudad=form.ciudad.data,
            codigo_postal=form.codigo_postal.data,
            pais=form.pais.data,

            num_habitaciones=form.num_habitaciones.data,
            num_banos=form.num_banos.data,
            capacidad_max=form.capacidad_max.data,

            precio_noche=form.precio_noche.data,
            moneda=form.moneda.data,
            activa=form.activa.data,

            tipo_impuesto=form.tipo_impuesto.data,
            porcentaje_impuesto=form.porcentaje_impuesto.data,
            aplicar_retencion=form.aplicar_retencion.data,
            porcentaje_retencion=form.porcentaje_retencion.data,

            gastos_individuales_texto=request.form.get("gastos_individuales_texto"),
            suministros_incluidos_texto=request.form.get("suministros_incluidos_texto"),
            caracteristicas_tecnicas_texto=request.form.get("caracteristicas_tecnicas_texto"),
            contacto_administracion_texto=request.form.get("contacto_administracion_texto"),
            iban_cobro=request.form.get("iban_cobro"),
            entidad_bancaria=request.form.get("entidad_bancaria"),
            concepto_transferencia=request.form.get("concepto_transferencia"),

            usuario_id=current_user.id,
            cuenta_id=current_user.cuenta_id
        )

        db.session.add(propiedad)
        db.session.commit()

        log_audit(
            current_user.id,
            'crear',
            'propiedad',
            propiedad.id,
            None,
            {
                'nombre': propiedad.nombre,
                'direccion': propiedad.direccion,
                'municipio': propiedad.municipio,
                'referencia_catastral': propiedad.referencia_catastral,
                'tipo_inmueble': propiedad.tipo_inmueble
            }
        )

        flash('Propiedad creada correctamente', 'success')
        return redirect(url_for('propiedades.index'))

    return render_template('propiedades/nueva.html', form=form)


@propiedades_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Editar una propiedad existente"""
    propiedad = Propiedad.query.get_or_404(id)

    if not propiedad_es_editable(propiedad):
        flash('No tienes permiso para editar esta propiedad', 'danger')
        return redirect(url_for('propiedades.index'))

    form = PropiedadForm(obj=propiedad)

    if form.validate_on_submit():
        datos_antes = {
            'nombre': propiedad.nombre,
            'direccion': propiedad.direccion,
            'municipio': propiedad.municipio,
            'referencia_catastral': propiedad.referencia_catastral,
            'tipo_inmueble': propiedad.tipo_inmueble,
            'precio_noche': propiedad.precio_noche,
            'activa': propiedad.activa
        }

        form.populate_obj(propiedad)

        propiedad.tipo_inmueble = request.form.get("tipo_inmueble")
        propiedad.referencia_catastral = request.form.get("referencia_catastral")
        propiedad.municipio = request.form.get("municipio")

        propiedad.gastos_individuales_texto = request.form.get("gastos_individuales_texto")
        propiedad.suministros_incluidos_texto = request.form.get("suministros_incluidos_texto")
        propiedad.caracteristicas_tecnicas_texto = request.form.get("caracteristicas_tecnicas_texto")
        propiedad.contacto_administracion_texto = request.form.get("contacto_administracion_texto")
        propiedad.iban_cobro = request.form.get("iban_cobro")
        propiedad.entidad_bancaria = request.form.get("entidad_bancaria")
        propiedad.concepto_transferencia = request.form.get("concepto_transferencia")

        db.session.commit()

        datos_despues = {
            'nombre': propiedad.nombre,
            'direccion': propiedad.direccion,
            'municipio': propiedad.municipio,
            'referencia_catastral': propiedad.referencia_catastral,
            'tipo_inmueble': propiedad.tipo_inmueble,
            'precio_noche': propiedad.precio_noche,
            'activa': propiedad.activa
        }

        log_audit(current_user.id, 'editar', 'propiedad', propiedad.id, datos_antes, datos_despues)

        flash('Propiedad actualizada correctamente', 'success')
        return redirect(url_for('propiedades.index'))

    return render_template('propiedades/editar.html', form=form, propiedad=propiedad)


@propiedades_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    propiedad = Propiedad.query.get_or_404(id)

    if not propiedad_es_editable(propiedad):
        flash('No tienes permiso', 'danger')
        return redirect(url_for('propiedades.index'))

    datos_eliminados = {
        'nombre': propiedad.nombre,
        'direccion': propiedad.direccion,
        'municipio': propiedad.municipio,
        'referencia_catastral': propiedad.referencia_catastral
    }
    log_audit(current_user.id, 'eliminar', 'propiedad', propiedad.id, datos_eliminados, None)

    db.session.delete(propiedad)
    db.session.commit()
    flash('Propiedad eliminada', 'success')
    return redirect(url_for('propiedades.index'))


@propiedades_bp.route('/<int:id>')
@login_required
def ver(id):
    """Ver detalle de una propiedad con sus próximas reservas"""
    propiedad = Propiedad.query.get_or_404(id)

    if not propiedad_es_visible(propiedad):
        flash('No tienes permiso para ver esta propiedad', 'danger')
        return redirect(url_for('propiedades.index'))

    hoy = datetime.today().date()
    reservas_futuras = propiedad.reservas.filter(
        Reserva.fecha_salida >= hoy,
        Reserva.estado.in_(['confirmada', 'pendiente'])
    ).order_by(Reserva.fecha_entrada).limit(5).all()

    return render_template(
        'propiedades/ver.html',
        propiedad=propiedad,
        reservas_futuras=reservas_futuras,
        ahora=hoy
    )


@propiedades_bp.route('/ses/<int:id>')
@login_required
def ses_config(id):
    """Página de configuración SES para una propiedad"""
    propiedad = Propiedad.query.get_or_404(id)

    if not propiedad_es_editable(propiedad):
        flash('No autorizado', 'danger')
        return redirect(url_for('propiedades.index'))

    return render_template('propiedades/ses_config.html', propiedad=propiedad)


@propiedades_bp.route('/ses/guardar/<int:id>', methods=['POST'])
@login_required
def guardar_ses(id):
    """Guardar configuración SES"""
    propiedad = Propiedad.query.get_or_404(id)

    if not propiedad_es_editable(propiedad):
        flash('No autorizado', 'danger')
        return redirect(url_for('propiedades.index'))

    propiedad.codigo_ses = request.form.get('codigo_ses')
    propiedad.codigo_arrendador = request.form.get('codigo_arrendador')
    propiedad.usuario_ses = request.form.get('usuario_ses')
    propiedad.password_ses = request.form.get('password_ses')

    db.session.commit()
    flash('Configuración SES guardada correctamente', 'success')
    return redirect(url_for('propiedades.ver', id=id))