from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import Propiedad, Reserva, Tarea
from datetime import datetime, timedelta

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    return render_template('index.html')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    # Estadísticas rápidas
    num_propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).count()
    hoy = datetime.today().date()
    reservas_hoy = 0
    tareas_pendientes = 0
    proximas_reservas = []
    
    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    propiedad_ids = [p.id for p in propiedades]
    
    if propiedad_ids:
        reservas_hoy = Reserva.query.filter(
            Reserva.propiedad_id.in_(propiedad_ids),
            Reserva.fecha_entrada <= hoy,
            Reserva.fecha_salida >= hoy,
            Reserva.estado != 'cancelada'
        ).count()
        
        tareas_pendientes = Tarea.query.filter(
            Tarea.propiedad_id.in_(propiedad_ids),
            Tarea.completada == False
        ).count()
        
        proximas_reservas = Reserva.query.filter(
            Reserva.propiedad_id.in_(propiedad_ids),
            Reserva.fecha_entrada >= hoy,
            Reserva.estado != 'cancelada'
        ).order_by(Reserva.fecha_entrada).limit(5).all()
    
    return render_template('dashboard.html',
                           num_propiedades=num_propiedades,
                           reservas_hoy=reservas_hoy,
                           tareas_pendientes=tareas_pendientes,
                           proximas_reservas=proximas_reservas)

@main_bp.route('/ayuda')
def ayuda():
    return render_template('ayuda/index.html')