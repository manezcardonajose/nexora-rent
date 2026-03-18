from flask import Blueprint, render_template, jsonify, url_for
from flask_login import login_required, current_user
from models import db, Reserva, Propiedad, Habitacion, BloqueoPropiedad
from datetime import datetime

# 🔴 PRIMERO: Crear el blueprint
calendario_bp = Blueprint('calendario', __name__, url_prefix='/calendario')

# 🔴 DESPUÉS: Definir las rutas usando el blueprint

@calendario_bp.route('/')
@login_required
def index():
    """Vista principal del calendario"""
    return render_template('calendario/index.html')

@calendario_bp.route('/eventos')
@login_required
def eventos():
    """Devuelve eventos (reservas y bloqueos) para FullCalendar"""
    print(f"📅 [DEBUG] Usuario {current_user.id} solicitando eventos")
    
    # Obtener todas las propiedades del usuario
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    propiedad_ids = [p.id for p in propiedades]
    
    if not propiedad_ids:
        print("📅 [DEBUG] Usuario sin propiedades")
        return jsonify([])
    
    eventos = []
    
    # 1️⃣ RESERVAS
    reservas = Reserva.query.filter(Reserva.propiedad_id.in_(propiedad_ids)).all()
    print(f"📅 [DEBUG] {len(reservas)} reservas encontradas")
    
    for r in reservas:
        propiedad = next((p for p in propiedades if p.id == r.propiedad_id), None)
        
        # Obtener el primer huésped para el nombre
        primer_huesped = r.huespedes.first()
        if primer_huesped:
            nombre_huesped = f"{primer_huesped.nombre} {primer_huesped.apellidos}"
        else:
            nombre_huesped = "Sin huésped"
        
        if propiedad:
            title = f"🟢 {propiedad.nombre[:15]} - {nombre_huesped}"
        else:
            title = f"🟢 Reserva #{r.id} - {nombre_huesped}"
        
        # Determinar color según estado
        if r.estado == 'cancelada':
            bg_color = '#dc3545'  # Rojo
        elif r.estado == 'pendiente':
            bg_color = '#ffc107'  # Amarillo
        else:
            bg_color = '#28a745'  # Verde (confirmada)
        
        eventos.append({
            'title': title,
            'start': r.fecha_entrada.isoformat(),
            'end': r.fecha_salida.isoformat(),
            'url': url_for('reservas.ver', id=r.id),
            'backgroundColor': bg_color,
            'borderColor': bg_color,
            'textColor': 'white',
            'allDay': True,
            'extendedProps': {
                'tipo': 'reserva',
                'estado': r.estado,
                'huesped': nombre_huesped,
                'propiedad': propiedad.nombre if propiedad else 'N/A'
            }
        })
    
    # 2️⃣ BLOQUEOS DE PROPIEDAD COMPLETA
    bloqueos_prop = BloqueoPropiedad.query.filter(
        BloqueoPropiedad.propiedad_id.in_(propiedad_ids),
        BloqueoPropiedad.habitacion_id == None,
        BloqueoPropiedad.activo == True
    ).all()
    
    for b in bloqueos_prop:
        propiedad = next((p for p in propiedades if p.id == b.propiedad_id), None)
        if propiedad:
            eventos.append({
                'title': f"🔴 BLOQUEO: {propiedad.nombre[:20]}",
                'start': b.fecha_inicio.isoformat(),
                'end': b.fecha_fin.isoformat(),
                'backgroundColor': '#dc3545',
                'borderColor': '#dc3545',
                'textColor': 'white',
                'allDay': True,
                'extendedProps': {
                    'tipo': 'bloqueo',
                    'motivo': b.motivo
                }
            })
    
    # 3️⃣ BLOQUEOS DE HABITACIONES
    bloqueos_hab = BloqueoPropiedad.query.filter(
        BloqueoPropiedad.propiedad_id.in_(propiedad_ids),
        BloqueoPropiedad.habitacion_id != None,
        BloqueoPropiedad.activo == True
    ).all()
    
    for b in bloqueos_hab:
        propiedad = next((p for p in propiedades if p.id == b.propiedad_id), None)
        habitacion = Habitacion.query.get(b.habitacion_id)
        if propiedad and habitacion:
            eventos.append({
                'title': f"🟡 {propiedad.nombre[:10]} - {habitacion.nombre[:15]}",
                'start': b.fecha_inicio.isoformat(),
                'end': b.fecha_fin.isoformat(),
                'backgroundColor': '#ffc107',
                'borderColor': '#ffc107',
                'textColor': 'black',
                'allDay': True,
                'extendedProps': {
                    'tipo': 'bloqueo_habitacion',
                    'motivo': b.motivo,
                    'habitacion': habitacion.nombre
                }
            })
    
    print(f"📅 [DEBUG] Total eventos enviados: {len(eventos)}")
    return jsonify(eventos)
