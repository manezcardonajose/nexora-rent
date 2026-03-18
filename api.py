from flask import Blueprint, jsonify
from flask_login import login_required, current_user
from models import Habitacion, Propiedad

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/habitaciones/<int:propiedad_id>')
@login_required
def habitaciones_api(propiedad_id):
    propiedad = Propiedad.query.get_or_404(propiedad_id)
    if propiedad.usuario_id != current_user.id:
        return jsonify({'error': 'No autorizado'}), 403
    
    habitaciones = Habitacion.query.filter_by(propiedad_id=propiedad_id, activa=True).order_by(Habitacion.orden).all()
    return jsonify([{
        'id': h.id,
        'nombre': h.nombre,
        'tipo': h.tipo,
        'capacidad': h.capacidad,
        'tiene_bano_suite': h.tiene_bano_suite,
        'camas': h.camas or '',
        'precio_base': h.precio_base
    } for h in habitaciones])