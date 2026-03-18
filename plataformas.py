from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, PlataformaReserva, CalendarioIcal, Propiedad
from forms import PlataformaForm, IcalForm
from utils import importar_ical, exportar_ical
from datetime import datetime

plataformas_bp = Blueprint('plataformas', __name__, url_prefix='/plataformas')

@plataformas_bp.route('/')
@login_required
def index():
    """Listado de plataformas conectadas"""
    plataformas = PlataformaReserva.query.filter_by(usuario_id=current_user.id).all()
    return render_template('plataformas/index.html', plataformas=plataformas)

@plataformas_bp.route('/nueva', methods=['GET', 'POST'])
@login_required
def nueva():
    """Conectar nueva plataforma"""
    form = PlataformaForm()
    if form.validate_on_submit():
        plataforma = PlataformaReserva(
            usuario_id=current_user.id,
            nombre=form.nombre.data,
            nombre_personalizado=form.nombre_personalizado.data,
            email_cuenta=form.email_cuenta.data,
            activa=True
        )
        db.session.add(plataforma)
        db.session.commit()
        flash('Plataforma añadida correctamente', 'success')
        return redirect(url_for('plataformas.index'))
    return render_template('plataformas/nueva.html', form=form)

@plataformas_bp.route('/<int:id>/calendarios')
@login_required
def calendarios(id):
    """Ver calendarios iCal de una plataforma"""
    plataforma = PlataformaReserva.query.get_or_404(id)
    if plataforma.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('plataformas.index'))
    
    calendarios = CalendarioIcal.query.filter_by(plataforma_id=id).all()
    return render_template('plataformas/calendarios.html', plataforma=plataforma, calendarios=calendarios)

@plataformas_bp.route('/sincronizar-todo')
@login_required
def sincronizar_todo():
    """Sincronizar todos los calendarios iCal activos"""
    from utils import importar_ical
    
    calendarios = CalendarioIcal.query.join(PlataformaReserva).filter(
        PlataformaReserva.usuario_id == current_user.id,
        CalendarioIcal.activo == True
    ).all()
    
    sincronizados = 0
    for cal in calendarios:
        try:
            eventos = importar_ical(cal.url, cal.propiedad_id)
            cal.ultima_sincronizacion = datetime.utcnow()
            sincronizados += 1
        except Exception as e:
            print(f"Error sincronizando {cal.nombre}: {e}")
    
    db.session.commit()
    flash(f'Sincronización completada. {sincronizados} calendarios actualizados.', 'success')
    return redirect(url_for('plataformas.index'))