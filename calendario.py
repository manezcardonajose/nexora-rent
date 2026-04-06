from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Reserva, Propiedad, Habitacion, CalendarioIcal, PlataformaReserva, BloqueoPropiedad, Tarea
from utils import importar_ical, exportar_ical, log_audit
from forms import IcalForm
from datetime import datetime

calendario_bp = Blueprint('calendario', __name__, url_prefix='/calendario')


def _texto_habitaciones_reserva(reserva, propiedad=None):
    habitaciones_asignadas = reserva.habitaciones_asignadas.all() if hasattr(reserva.habitaciones_asignadas, 'all') else list(reserva.habitaciones_asignadas or [])

    if not habitaciones_asignadas:
        return 'Sin asignar'

    nombres = [rh.habitacion.nombre for rh in habitaciones_asignadas if getattr(rh, 'habitacion', None)]
    if not nombres:
        return 'Sin asignar'

    total_habitaciones_propiedad = 0
    if propiedad and hasattr(propiedad.habitaciones, 'count'):
        try:
            total_habitaciones_propiedad = propiedad.habitaciones.count()
        except Exception:
            total_habitaciones_propiedad = len(propiedad.habitaciones.all()) if hasattr(propiedad.habitaciones, 'all') else len(propiedad.habitaciones or [])

    if total_habitaciones_propiedad and len(nombres) == total_habitaciones_propiedad:
        return 'Vivienda completa'

    return ', '.join(nombres)


@calendario_bp.route('/')
@login_required
def index():
    return render_template('calendario/index.html')


@calendario_bp.route('/eventos')
@login_required
def eventos():
    """
    Calendario PRO:
    - Reservas
    - Bloqueos
    - Tareas
    """

    propiedades = Propiedad.query.filter_by(usuario_id=current_user.id).all()
    propiedad_ids = [p.id for p in propiedades]

    eventos = []

    # =========================
    # 🔵 RESERVAS
    # =========================
    reservas = Reserva.query.filter(Reserva.propiedad_id.in_(propiedad_ids)).all()

    for r in reservas:
        propiedad = next((p for p in propiedades if p.id == r.propiedad_id), None)

        huesped = r.huespedes.first()
        nombre_huesped = f"{huesped.nombre}" if huesped else "Sin huésped"
        habitaciones_texto = _texto_habitaciones_reserva(r, propiedad)

        color = "#28a745"  # verde
        if r.estado == "pendiente":
            color = "#ffc107"
        elif r.estado == "cancelada":
            color = "#6c757d"

        eventos.append({
            'title': f"{propiedad.nombre[:12] if propiedad else 'Reserva'} · {habitaciones_texto}",
            'start': r.fecha_entrada.isoformat(),
            'end': r.fecha_salida.isoformat(),
            'url': url_for('reservas.ver', id=r.id),
            'backgroundColor': color,
            'borderColor': color,
            'textColor': 'black' if color == "#ffc107" else 'white',
            'extendedProps': {
                'tipo': 'reserva',
                'estado': r.estado,
                'propiedad': propiedad.nombre if propiedad else '',
                'habitacion': habitaciones_texto,
                'huesped': nombre_huesped,
                'importe': r.precio_total,
                'saldo': r.saldo_pendiente
            }
        })

    # =========================
    # 🔴 BLOQUEOS (PROPIEDAD)
    # =========================
    bloqueos_prop = BloqueoPropiedad.query.filter(
        BloqueoPropiedad.propiedad_id.in_(propiedad_ids),
        BloqueoPropiedad.habitacion_id == None,
        BloqueoPropiedad.activo == True
    ).all()

    for b in bloqueos_prop:
        propiedad = next((p for p in propiedades if p.id == b.propiedad_id), None)

        eventos.append({
            'title': f"Bloqueo · {propiedad.nombre if propiedad else ''}",
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

    # =========================
    # 🟡 BLOQUEOS HABITACIÓN
    # =========================
    bloqueos_hab = BloqueoPropiedad.query.filter(
        BloqueoPropiedad.propiedad_id.in_(propiedad_ids),
        BloqueoPropiedad.habitacion_id != None,
        BloqueoPropiedad.activo == True
    ).all()

    for b in bloqueos_hab:
        propiedad = next((p for p in propiedades if p.id == b.propiedad_id), None)
        habitacion = Habitacion.query.get(b.habitacion_id)

        eventos.append({
            'title': f"{habitacion.nombre if habitacion else ''} · {b.motivo}",
            'start': b.fecha_inicio.isoformat(),
            'end': b.fecha_fin.isoformat(),
            'backgroundColor': '#ffc107',
            'borderColor': '#ffc107',
            'textColor': 'black',
            'extendedProps': {
                'tipo': 'bloqueo_habitacion',
                'habitacion': habitacion.nombre if habitacion else '',
                'motivo': b.motivo
            }
        })

    # =========================
    # 🔵 TAREAS (CLAVE DEL ERP)
    # =========================
    tareas = Tarea.query.filter(
        Tarea.propiedad_id.in_(propiedad_ids)
    ).all()

    for t in tareas:
        color = "#0d6efd"  # azul
        if t.completada:
            color = "#6c757d"

        eventos.append({
            'title': f"Tarea · {t.tipo}",
            'start': t.fecha_asignada.isoformat() if t.fecha_asignada else None,
            'end': t.fecha_limite.isoformat() if t.fecha_limite else None,
            'url': url_for('tareas.editar', id=t.id),
            'backgroundColor': color,
            'borderColor': color,
            'textColor': 'white',
            'extendedProps': {
                'tipo': 'tarea',
                'estado': 'completada' if t.completada else 'pendiente',
                'descripcion': t.descripcion
            }
        })

    return jsonify(eventos)