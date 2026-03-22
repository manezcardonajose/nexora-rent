from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, Propiedad, Reserva
from forms import PropiedadForm
from datetime import datetime
from utils import log_audit

# Crear el blueprint
propiedades_bp = Blueprint('propiedades', __name__, url_prefix='/propiedades')

@propiedades_bp.route('/')
@login_required
def index():
    """Listado de propiedades del usuario"""
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    return render_template('propiedades/index.html', propiedades=propiedades)

@propiedades_bp.route('/nueva', methods=['GET', 'POST'])
@login_required
def nueva():
    """Crear una nueva propiedad"""
    form = PropiedadForm()
    if form.validate_on_submit():
        propiedad = Propiedad(
            nombre=form.nombre.data,
            descripcion=form.descripcion.data,
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
            usuario_id=current_user.id
        )
        db.session.add(propiedad)
        db.session.commit()
        # 🔐 LOG: Creación de propiedad
        log_audit(current_user.id, 'crear', 'propiedad', propiedad.id, 
                  None, {'nombre': propiedad.nombre, 'direccion': propiedad.direccion})
        
        flash('Propiedad creada correctamente', 'success')
        return redirect(url_for('propiedades.index'))
    return render_template('propiedades/nueva.html', form=form)

@propiedades_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Editar una propiedad existente"""
    propiedad = Propiedad.query.get_or_404(id)
    log_audit(current_user.id, 'crear', 'propiedad', propiedad.id, None, {'nombre': propiedad.nombre})
    
    # Verificar que la propiedad pertenece al usuario
    if propiedad.usuario_id != current_user.id:
        flash('No tienes permiso para editar esta propiedad', 'danger')
        return redirect(url_for('propiedades.index'))
    
    form = PropiedadForm(obj=propiedad)
    if form.validate_on_submit():
        form.populate_obj(propiedad)
        db.session.commit()
        flash('Propiedad actualizada correctamente', 'success')
        return redirect(url_for('propiedades.index'))

 # 🔐 LOG: Edición de propiedad
        datos_despues = {
            'nombre': propiedad.nombre,
            'direccion': propiedad.direccion,
            'precio_noche': propiedad.precio_noche,
            'activa': propiedad.activa
        }
        log_audit(current_user.id, 'editar', 'propiedad', propiedad.id, datos_antes, datos_despues)
        
        flash('Propiedad actualizada', 'success')
        return redirect(url_for('propiedades.index'))
    return render_template('propiedades/editar.html', form=form, propiedad=propiedad)
    
   

@propiedades_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    propiedad = Propiedad.query.get_or_404(id)
    if propiedad.usuario_id != current_user.id:
        flash('No tienes permiso', 'danger')
        return redirect(url_for('propiedades.index'))
    
    # 🔐 LOG: Eliminación de propiedad (guardar datos antes de eliminar)
    datos_eliminados = {'nombre': propiedad.nombre, 'direccion': propiedad.direccion}
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
    
    # Verificar que la propiedad pertenece al usuario
    if propiedad.usuario_id != current_user.id:
        flash('No tienes permiso para ver esta propiedad', 'danger')
        return redirect(url_for('propiedades.index'))
    
    # Calcular reservas futuras (desde hoy en adelante)
    hoy = datetime.today().date()
    reservas_futuras = propiedad.reservas.filter(
        Reserva.fecha_salida >= hoy,
        Reserva.estado.in_(['confirmada', 'pendiente'])
    ).order_by(Reserva.fecha_entrada).limit(5).all()
    
    return render_template('propiedades/ver.html', 
                           propiedad=propiedad,
                           reservas_futuras=reservas_futuras,
                           ahora=hoy)  # Pasamos 'ahora' por si la plantilla lo necesita

@propiedades_bp.route('/ses/<int:id>')
@login_required
def ses_config(id):
    """Página de configuración SES para una propiedad"""
    propiedad = Propiedad.query.get_or_404(id)
    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('propiedades.index'))
    
    return render_template('propiedades/ses_config.html', propiedad=propiedad)

@propiedades_bp.route('/ses/guardar/<int:id>', methods=['POST'])
@login_required
def guardar_ses(id):
    """Guardar configuración SES"""
    propiedad = Propiedad.query.get_or_404(id)
    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('propiedades.index'))
    
    propiedad.codigo_ses = request.form.get('codigo_ses')
    propiedad.codigo_arrendador = request.form.get('codigo_arrendador')
    propiedad.usuario_ses = request.form.get('usuario_ses')
    propiedad.password_ses = request.form.get('password_ses')
    
    db.session.commit()
    flash('Configuración SES guardada correctamente', 'success')
    return redirect(url_for('propiedades.ver', id=id))