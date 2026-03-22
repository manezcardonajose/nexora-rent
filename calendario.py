from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Reserva, Propiedad, Habitacion, CalendarioIcal, PlataformaReserva, BloqueoPropiedad
from utils import importar_ical, exportar_ical, log_audit
from forms import IcalForm
from datetime import datetime

calendario_bp = Blueprint('calendario', __name__, url_prefix='/calendario')


@calendario_bp.route('/')
@login_required
def index():
    """Vista del calendario"""
    return render_template('calendario/index.html')


@calendario_bp.route('/eventos')
@login_required
def eventos():
    """Devuelve eventos (reservas y bloqueos) para FullCalendar"""
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    propiedad_ids = [p.id for p in propiedades]
    
    eventos = []
    
    # 1️⃣ Reservas normales
    reservas = Reserva.query.filter(Reserva.propiedad_id.in_(propiedad_ids)).all()
    for r in reservas:
        propiedad = next((p for p in propiedades if p.id == r.propiedad_id), None)
        title = f"🟢 {propiedad.nombre[:15]} - {r.huespedes.first().nombre if r.huespedes.first() else 'Sin huésped'}" if propiedad else "Reserva"
        eventos.append({
            'title': title,
            'start': r.fecha_entrada.isoformat(),
            'end': r.fecha_salida.isoformat(),
            'url': url_for('reservas.ver', id=r.id),
            'backgroundColor': '#28a745',
            'borderColor': '#28a745',
            'textColor': 'white',
            'extendedProps': {'tipo': 'reserva'}
        })
    
    # 2️⃣ Bloqueos de toda la propiedad
    bloqueos_prop = BloqueoPropiedad.query.filter(
        BloqueoPropiedad.propiedad_id.in_(propiedad_ids),
        BloqueoPropiedad.habitacion_id == None,
        BloqueoPropiedad.activo == True
    ).all()
    
    for b in bloqueos_prop:
        propiedad = Propiedad.query.get(b.propiedad_id)
        eventos.append({
            'title': f"🔴 {propiedad.nombre[:15]} - {b.motivo}",
            'start': b.fecha_inicio.isoformat(),
            'end': b.fecha_fin.isoformat(),
            'backgroundColor': '#dc3545',
            'borderColor': '#dc3545',
            'textColor': 'white',
            'extendedProps': {
                'tipo': 'bloqueo',
                'motivo': b.motivo,
                'descripcion': b.descripcion
            }
        })
    
    # 3️⃣ Bloqueos de habitaciones individuales
    bloqueos_hab = BloqueoPropiedad.query.filter(
        BloqueoPropiedad.propiedad_id.in_(propiedad_ids),
        BloqueoPropiedad.habitacion_id != None,
        BloqueoPropiedad.activo == True
    ).all()
    
    for b in bloqueos_hab:
        propiedad = Propiedad.query.get(b.propiedad_id)
        habitacion = Habitacion.query.get(b.habitacion_id)
        eventos.append({
            'title': f"🟡 {propiedad.nombre[:10]} - {habitacion.nombre} ({b.motivo})",
            'start': b.fecha_inicio.isoformat(),
            'end': b.fecha_fin.isoformat(),
            'backgroundColor': '#ffc107',
            'borderColor': '#ffc107',
            'textColor': 'black',
            'extendedProps': {
                'tipo': 'bloqueo_habitacion',
                'motivo': b.motivo,
                'habitacion': habitacion.nombre
            }
        })
    
    return jsonify(eventos)


# ============================================
# RUTAS PARA CALENDARIOS ICAL
# ============================================

@calendario_bp.route('/ical/nuevo/<int:plataforma_id>', methods=['POST'])
@login_required
def nuevo_ical(plataforma_id):
    """Añadir nuevo calendario iCal a una plataforma"""
    plataforma = PlataformaReserva.query.get_or_404(plataforma_id)
    if plataforma.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('plataformas.index'))
    
    form = IcalForm()
    if form.validate_on_submit():
        ical = CalendarioIcal(
            propiedad_id=form.propiedad_id.data,
            plataforma_id=plataforma_id,
            nombre=form.nombre.data,
            plataforma_origen=plataforma.nombre,
            activo=form.activo.data
        )
        # Guardar URL cifrada
        ical.set_url(form.url.data)
        
        db.session.add(ical)
        db.session.commit()
        
        # 🔐 LOG: Creación de calendario iCal
        log_audit(current_user.id, 'crear', 'calendario', ical.id, None,
                  {'plataforma': plataforma.nombre, 'propiedad_id': form.propiedad_id.data})
        
        flash('Calendario iCal añadido correctamente', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'Error en {field}: {error}', 'danger')
    
    return redirect(url_for('plataformas.calendarios', id=plataforma_id))


@calendario_bp.route('/ical/sincronizar/<int:id>', methods=['POST'])
@login_required
def sincronizar_ical(id):
    """Sincronizar un calendario iCal específico"""
    ical = CalendarioIcal.query.get_or_404(id)
    propiedad = Propiedad.query.get(ical.propiedad_id)
    
    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('plataformas.index'))
    
    try:
        # Obtener URL descifrada
        url = ical.get_url()
        
        eventos = importar_ical(url, ical.propiedad_id)
        ical.ultima_sincronizacion = datetime.utcnow()
        db.session.commit()
        
        # 🔐 LOG: Sincronización de calendario
        log_audit(current_user.id, 'sincronizar', 'calendario', ical.id, None, 
                  {'plataforma': ical.plataforma_origen, 'eventos_importados': eventos})
        
        flash(f'Sincronización completada. {eventos} eventos importados.', 'success')
    except Exception as e:
        flash(f'Error al sincronizar: {str(e)}', 'danger')
    
    return redirect(url_for('plataformas.calendarios', id=ical.plataforma_id))


@calendario_bp.route('/ical/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_ical(id):
    """Eliminar un calendario iCal"""
    ical = CalendarioIcal.query.get_or_404(id)
    propiedad = Propiedad.query.get(ical.propiedad_id)
    
    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('plataformas.index'))
    
    plataforma_id = ical.plataforma_id
    
    # 🔐 LOG: Eliminación de calendario
    log_audit(current_user.id, 'eliminar', 'calendario', ical.id, 
              {'url': '***cifrada***', 'propiedad_id': ical.propiedad_id}, None)
    
    db.session.delete(ical)
    db.session.commit()
    flash('Calendario eliminado', 'success')
    
    return redirect(url_for('plataformas.calendarios', id=plataforma_id))


@calendario_bp.route('/exportar/<int:propiedad_id>')
@login_required
def exportar(propiedad_id):
    """Exportar calendario iCal de una propiedad"""
    propiedad = Propiedad.query.get_or_404(propiedad_id)
    if propiedad.usuario_id != current_user.id:
        flash('No autorizado', 'danger')
        return redirect(url_for('propiedades.index'))
    
    ical_data = exportar_ical(propiedad_id)
    
    from flask import Response
    return Response(
        ical_data,
        mimetype='text/calendar',
        headers={'Content-Disposition': f'attachment; filename=calendario_{propiedad_id}.ics'}
    )