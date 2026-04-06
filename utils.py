from datetime import datetime, timedelta
from models import Tarea, Reserva, db, ReservaHabitacion, BloqueoPropiedad
import requests
from icalendar import Calendar
from urllib.parse import urlparse
import os
from flask import render_template, request
import pdfkit
import traceback
import json

# ============================================
# FUNCIONES DE TAREAS
# ============================================

def generar_tareas_limpieza(reserva_id):
    """
    Genera automáticamente tareas operativas para una reserva:
    - Preparación / revisión de entrada
    - Limpieza de salida

    Evita duplicados si ya existen tareas automáticas para esa reserva.
    """
    from models import Reserva, Tarea

    reserva = Reserva.query.get(reserva_id)
    if not reserva:
        return []

    # Obtener titular
    primer_huesped = reserva.huespedes.first()
    if primer_huesped:
        nombre_huesped = f"{primer_huesped.nombre} {primer_huesped.apellidos}"
    else:
        nombre_huesped = "Huésped no registrado"

    tareas_creadas = []

    # 1) Preparación de entrada
    descripcion_entrada = f"Preparar entrada para reserva de {nombre_huesped} (entrada {reserva.fecha_entrada})"
    existente_entrada = Tarea.query.filter_by(
        propiedad_id=reserva.propiedad_id,
        reserva_id=reserva.id,
        tipo='entrada',
        descripcion=descripcion_entrada
    ).first()

    if not existente_entrada:
        tarea_entrada = Tarea(
            propiedad_id=reserva.propiedad_id,
            reserva_id=reserva.id,
            tipo='entrada',
            descripcion=descripcion_entrada,
            fecha_asignada=reserva.fecha_entrada,
            fecha_limite=reserva.fecha_entrada,
            completada=False,
            notas='Tarea automática generada desde la reserva'
        )
        db.session.add(tarea_entrada)
        tareas_creadas.append(tarea_entrada)

    # 2) Limpieza de salida
    descripcion_salida = f"Limpieza completa para reserva de {nombre_huesped} (salida {reserva.fecha_salida})"
    existente_salida = Tarea.query.filter_by(
        propiedad_id=reserva.propiedad_id,
        reserva_id=reserva.id,
        tipo='limpieza',
        descripcion=descripcion_salida
    ).first()

    if not existente_salida:
        tarea_salida = Tarea(
            propiedad_id=reserva.propiedad_id,
            reserva_id=reserva.id,
            tipo='limpieza',
            descripcion=descripcion_salida,
            fecha_asignada=reserva.fecha_salida,
            fecha_limite=reserva.fecha_salida + timedelta(days=1),
            completada=False,
            notas='Tarea automática generada desde la reserva'
        )
        db.session.add(tarea_salida)
        tareas_creadas.append(tarea_salida)

    # 3) Cambio de sábanas si la estancia es larga
    try:
        noches = (reserva.fecha_salida - reserva.fecha_entrada).days
    except Exception:
        noches = 0

    if noches >= 7:
        fecha_sabanas = reserva.fecha_entrada + timedelta(days=3)
        descripcion_sabanas = f"Cambio de sábanas para reserva de {nombre_huesped}"

        existente_sabanas = Tarea.query.filter_by(
            propiedad_id=reserva.propiedad_id,
            reserva_id=reserva.id,
            tipo='sabanas',
            descripcion=descripcion_sabanas
        ).first()

        if not existente_sabanas:
            tarea_sabanas = Tarea(
                propiedad_id=reserva.propiedad_id,
                reserva_id=reserva.id,
                tipo='sabanas',
                descripcion=descripcion_sabanas,
                fecha_asignada=fecha_sabanas,
                fecha_limite=fecha_sabanas,
                completada=False,
                notas='Tarea automática por estancia larga'
            )
            db.session.add(tarea_sabanas)
            tareas_creadas.append(tarea_sabanas)

    if tareas_creadas:
        db.session.commit()

    return tareas_creadas


# ============================================
# FUNCIONES DE DISPONIBILIDAD
# ============================================

def check_disponibilidad(propiedad_id, fecha_entrada, fecha_salida, reserva_id_excluir=None):
    """Versión legacy: verifica disponibilidad de toda la propiedad"""
    from models import Reserva

    if isinstance(fecha_entrada, str):
        fecha_entrada = datetime.strptime(fecha_entrada, '%Y-%m-%d').date()
    if isinstance(fecha_salida, str):
        fecha_salida = datetime.strptime(fecha_salida, '%Y-%m-%d').date()

    query = Reserva.query.filter(
        Reserva.propiedad_id == propiedad_id,
        Reserva.estado.in_(['confirmada', 'pendiente']),
        Reserva.fecha_entrada < fecha_salida,
        Reserva.fecha_salida > fecha_entrada
    )

    if reserva_id_excluir:
        query = query.filter(Reserva.id != reserva_id_excluir)

    conflicto = query.first()
    return conflicto is None


def check_disponibilidad_habitaciones(propiedad_id, fecha_entrada, fecha_salida, habitaciones_ids, reserva_id_excluir=None):
    """
    Verifica disponibilidad considerando:
    - Reservas existentes
    - Bloqueos manuales (mantenimiento, reformas, etc.)
    Retorna (disponible, habitaciones_conflictivas)
    """
    from models import ReservaHabitacion, Reserva, BloqueoPropiedad

    if isinstance(fecha_entrada, str):
        fecha_entrada = datetime.strptime(fecha_entrada, '%Y-%m-%d').date()
    if isinstance(fecha_salida, str):
        fecha_salida = datetime.strptime(fecha_salida, '%Y-%m-%d').date()

    habitaciones_conflictivas = []

    for hab_id in habitaciones_ids:
        query_reservas = db.session.query(ReservaHabitacion).join(Reserva).filter(
            ReservaHabitacion.habitacion_id == hab_id,
            Reserva.estado.in_(['confirmada', 'pendiente']),
            Reserva.fecha_entrada < fecha_salida,
            Reserva.fecha_salida > fecha_entrada
        )

        if reserva_id_excluir:
            query_reservas = query_reservas.filter(Reserva.id != reserva_id_excluir)

        if query_reservas.first():
            habitaciones_conflictivas.append(hab_id)
            continue

        query_bloqueos_hab = BloqueoPropiedad.query.filter(
            BloqueoPropiedad.habitacion_id == hab_id,
            BloqueoPropiedad.activo == True,
            BloqueoPropiedad.fecha_inicio < fecha_salida,
            BloqueoPropiedad.fecha_fin > fecha_entrada
        )

        if query_bloqueos_hab.first():
            habitaciones_conflictivas.append(hab_id)
            continue

        query_bloqueos_prop = BloqueoPropiedad.query.filter(
            BloqueoPropiedad.propiedad_id == propiedad_id,
            BloqueoPropiedad.habitacion_id == None,
            BloqueoPropiedad.activo == True,
            BloqueoPropiedad.fecha_inicio < fecha_salida,
            BloqueoPropiedad.fecha_fin > fecha_entrada
        )

        if query_bloqueos_prop.first():
            habitaciones_conflictivas.append(hab_id)

    disponible = len(habitaciones_conflictivas) == 0
    return disponible, habitaciones_conflictivas


# ============================================
# FUNCIONES DE ICAL
# ============================================

def importar_ical(url, propiedad_id):
    """
    Importa eventos desde un feed iCal.
    Conservada como legacy para no romper lo existente.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        cal = Calendar.from_ical(response.text)

        contador = 0
        for component in cal.walk():
            if component.name == "VEVENT":
                start = component.get('dtstart').dt
                end = component.get('dtend').dt
                summary = str(component.get('summary', 'Reserva bloqueada'))
                uid = str(component.get('uid', ''))

                existing = Reserva.query.filter_by(external_id=uid, propiedad_id=propiedad_id).first()
                if existing:
                    continue

                reserva = Reserva(
                    propiedad_id=propiedad_id,
                    fecha_entrada=start.date() if hasattr(start, 'date') else start,
                    fecha_salida=end.date() if hasattr(end, 'date') else end,
                    num_huespedes=1,
                    num_menores=0,
                    precio_total=0,
                    estado='confirmada',
                    origen='ical',
                    external_id=uid,
                    notas=f"Importado desde iCal: {summary}"
                )
                db.session.add(reserva)
                contador += 1

        db.session.commit()
        return contador
    except Exception as e:
        print(f"Error importando iCal: {e}")
        return 0


def exportar_ical(propiedad_id):
    """
    Genera un feed iCal con todas las reservas confirmadas de una propiedad.
    """
    from icalendar import Calendar, Event

    cal = Calendar()
    cal.add('prodid', '-//Gestor Alquiler Vacacional//es')
    cal.add('version', '2.0')

    reservas = Reserva.query.filter_by(propiedad_id=propiedad_id, estado='confirmada').all()

    for reserva in reservas:
        primer_huesped = reserva.huespedes.first()
        nombre_huesped = f"{primer_huesped.nombre} {primer_huesped.apellidos}" if primer_huesped else "Reserva"

        event = Event()
        event.add('summary', f'Reservado: {nombre_huesped}')
        event.add('dtstart', reserva.fecha_entrada)
        event.add('dtend', reserva.fecha_salida)
        event.add('dtstamp', datetime.utcnow())
        event.add('uid', f"reserva-{reserva.id}@gestor.local")
        event.add('description', f"Reserva - {reserva.num_huespedes} personas")
        cal.add_component(event)

    return cal.to_ical()


# ============================================
# FUNCIÓN DE GENERACIÓN DE PDF
# ============================================

def generar_pdf_reserva(reserva_id):
    """
    Genera un PDF con los detalles de la reserva usando pdfkit.
    """
    print(f"🔵 [PDF] Intentando generar PDF para reserva ID: {reserva_id}")

    try:
        reserva = Reserva.query.get(reserva_id)
        if not reserva:
            print(f"🔴 [PDF] Error: Reserva {reserva_id} no encontrada")
            return None

        noches = (reserva.fecha_salida - reserva.fecha_entrada).days

        habitaciones = []
        for rh in reserva.habitaciones_asignadas:
            habitaciones.append({
                'nombre': rh.habitacion.nombre,
                'tipo': rh.habitacion.tipo,
                'precio': rh.precio_aplicado
            })

        html = render_template(
            'documentos/reserva.html',
            reserva=reserva,
            noches=noches,
            habitaciones=habitaciones,
            now=datetime.now
        )

        options = {
            'page-size': 'A4',
            'margin-top': '0.75in',
            'margin-right': '0.75in',
            'margin-bottom': '0.75in',
            'margin-left': '0.75in',
            'encoding': "UTF-8",
            'enable-local-file-access': None
        }

        path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
        config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)

        pdf = pdfkit.from_string(html, False, options=options, configuration=config)
        print(f"🟢 [PDF] PDF generado con pdfkit, tamaño: {len(pdf)} bytes")
        return pdf

    except Exception as e:
        print(f"🔴 [PDF] Error general: {e}")
        print(traceback.format_exc())
        return None


# ============================================
# AUDITORÍA
# ============================================

def log_audit(usuario_id, accion, entidad, entidad_id, datos_previos=None, datos_nuevos=None):
    """
    Registra una acción en el log de auditoría.
    """
    from models import AuditLog

    try:
        log = AuditLog(
            usuario_id=usuario_id,
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            datos_previos=json.dumps(datos_previos, default=str) if datos_previos else None,
            datos_nuevos=json.dumps(datos_nuevos, default=str) if datos_nuevos else None,
            ip=request.remote_addr,
            fecha=datetime.utcnow()
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        print(f"Error al registrar auditoría: {e}")