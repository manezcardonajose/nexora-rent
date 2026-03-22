from datetime import datetime, timedelta
from models import Tarea, Reserva, db, ReservaHabitacion, BloqueoPropiedad
import requests
from icalendar import Calendar
from urllib.parse import urlparse
import os
from flask import render_template

# ============================================
# FUNCIONES DE TAREAS
# ============================================

def generar_tareas_limpieza(reserva_id):
    """
    Genera automáticamente una tarea de limpieza para una reserva
    una vez que esta finaliza (fecha de salida).
    """
    from models import Reserva, Tarea
    from datetime import timedelta
    
    reserva = Reserva.query.get(reserva_id)
    if not reserva:
        return None
    
    # Obtener el primer huésped (titular) para el nombre
    primer_huesped = reserva.huespedes.first()
    if primer_huesped:
        nombre_huesped = f"{primer_huesped.nombre} {primer_huesped.apellidos}"
    else:
        nombre_huesped = "Huésped no registrado"
    
    # Crear tarea de limpieza para el día de salida
    tarea = Tarea(
        propiedad_id=reserva.propiedad_id,
        reserva_id=reserva.id,
        tipo='limpieza',
        descripcion=f"Limpieza completa para reserva de {nombre_huesped} (salida {reserva.fecha_salida})",
        fecha_asignada=reserva.fecha_salida,
        fecha_limite=reserva.fecha_salida + timedelta(days=1),
        completada=False
    )
    db.session.add(tarea)
    db.session.commit()
    return tarea


# ============================================
# FUNCIONES DE DISPONIBILIDAD
# ============================================

def check_disponibilidad(propiedad_id, fecha_entrada, fecha_salida, reserva_id_excluir=None):
    """Versión legacy: verifica disponibilidad de toda la propiedad"""
    from models import Reserva
    
    # Asegurar que las fechas son objetos date
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
    
    # Asegurar tipos de fecha
    if isinstance(fecha_entrada, str):
        fecha_entrada = datetime.strptime(fecha_entrada, '%Y-%m-%d').date()
    if isinstance(fecha_salida, str):
        fecha_salida = datetime.strptime(fecha_salida, '%Y-%m-%d').date()
    
    habitaciones_conflictivas = []
    
    for hab_id in habitaciones_ids:
        # 1️⃣ Verificar reservas existentes
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
        
        # 2️⃣ Verificar bloqueos manuales para esta habitación
        query_bloqueos_hab = BloqueoPropiedad.query.filter(
            BloqueoPropiedad.habitacion_id == hab_id,
            BloqueoPropiedad.activo == True,
            BloqueoPropiedad.fecha_inicio < fecha_salida,
            BloqueoPropiedad.fecha_fin > fecha_entrada
        )
        
        if query_bloqueos_hab.first():
            habitaciones_conflictivas.append(hab_id)
            continue
        
        # 3️⃣ Verificar bloqueos de toda la propiedad
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
    Importa eventos desde un feed iCal y crea reservas bloqueadas
    para una propiedad específica.
    Retorna el número de eventos importados.
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
                
                # Buscar si ya existe una reserva con ese uid
                existing = Reserva.query.filter_by(external_id=uid, propiedad_id=propiedad_id).first()
                if existing:
                    continue
                
                # Crear reserva de bloqueo
                reserva = Reserva(
                    propiedad_id=propiedad_id,
                    huesped_nombre="Reserva iCal",
                    huesped_apellidos="Sincronizada",
                    huesped_email="",
                    huesped_telefono="",
                    huesped_nif="",
                    huesped_sexo="No especificado",
                    huesped_fecha_nacimiento=datetime.now().date(),
                    huesped_nacionalidad="OTRO",
                    huesped_tipo_documento="OTRO",
                    huesped_numero_documento="",
                    huesped_domicilio="",
                    huesped_ciudad="",
                    huesped_codigo_postal="",
                    huesped_pais="",
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
    Genera un feed iCal con todas las reservas de una propiedad.
    Retorna el contenido del calendario en formato iCal.
    """
    from icalendar import Calendar, Event
    
    cal = Calendar()
    cal.add('prodid', '-//Gestor Alquiler Vacacional//es')
    cal.add('version', '2.0')
    
    reservas = Reserva.query.filter_by(propiedad_id=propiedad_id, estado='confirmada').all()
    
    for reserva in reservas:
        event = Event()
        event.add('summary', f'Reservado: {reserva.huesped_nombre} {reserva.huesped_apellidos}')
        event.add('dtstart', reserva.fecha_entrada)
        event.add('dtend', reserva.fecha_salida)
        event.add('dtstamp', datetime.utcnow())
        event.add('uid', f"reserva-{reserva.id}@gestor.local")
        event.add('description', f"Reserva de {reserva.huesped_nombre} - {reserva.num_huespedes} personas")
        cal.add_component(event)
    
    return cal.to_ical()


# ============================================
# FUNCIÓN DE GENERACIÓN DE PDF
# ============================================

import pdfkit
import traceback
from flask import render_template
from datetime import datetime
from models import Reserva

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

        # Obtener habitaciones asignadas
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

        # Opciones para pdfkit
        options = {
            'page-size': 'A4',
            'margin-top': '0.75in',
            'margin-right': '0.75in',
            'margin-bottom': '0.75in',
            'margin-left': '0.75in',
            'encoding': "UTF-8",
            'enable-local-file-access': None
        }

        # 🔴 ¡¡IMPORTANTE!! Configura la ruta donde tienes wkhtmltopdf.exe
        path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'  # <--- CAMBIA ESTO SI ES NECESARIO
        config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)

        # Generar PDF pasando la configuración
        pdf = pdfkit.from_string(html, False, options=options, configuration=config)
        print(f"🟢 [PDF] PDF generado con pdfkit, tamaño: {len(pdf)} bytes")
        return pdf

    except Exception as e:
        print(f"🔴 [PDF] Error general: {e}")
        print(traceback.format_exc())
        return None

from cryptography.fernet import Fernet
import os

def get_cipher():
    key = os.environ.get('CIPHER_KEY')
    if not key:
        # En desarrollo, podrías generar una temporal (no recomendado para producción)
        key = 'F6_8tqQw-lFq3dG7xYzZJkNmPqRsTuVwXyZ123456789='  # ejemplo, no usar en producción
    return Fernet(key.encode())

def encrypt_data(data):
    if not data:
        return None
    cipher = get_cipher()
    return cipher.encrypt(data.encode()).decode()

def decrypt_data(encrypted):
    if not encrypted:
        return None
    cipher = get_cipher()
    return cipher.decrypt(encrypted.encode()).decode()

import json
from models import AuditLog
from flask import request

def log_audit(usuario_id, accion, entidad, entidad_id, datos_previos=None, datos_nuevos=None):
    log = AuditLog(
        usuario_id=usuario_id,
        accion=accion,
        entidad=entidad,
        entidad_id=entidad_id,
        datos_previos=json.dumps(datos_previos, default=str) if datos_previos else None,
        datos_nuevos=json.dumps(datos_nuevos, default=str) if datos_nuevos else None,
        ip=request.remote_addr
    )

# Añadir al final del archivo utils.py
import json
from models import AuditLog
from flask import request
from datetime import datetime

def log_audit(usuario_id, accion, entidad, entidad_id, datos_previos=None, datos_nuevos=None):
    """
    Registra una acción en el log de auditoría.
    - usuario_id: ID del usuario que realiza la acción (current_user.id)
    - accion: 'crear', 'ver', 'editar', 'eliminar', 'exportar', 'sincronizar'
    - entidad: 'propiedad', 'habitacion', 'reserva', 'huesped', 'pago', 'plataforma'
    - entidad_id: ID del objeto afectado
    - datos_previos: dict con datos antes del cambio (para ediciones)
    - datos_nuevos: dict con datos después del cambio
    """
    from models import db
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
        # Si falla el log, no debe detener la aplicación
        print(f"Error al registrar auditoría: {e}")
    db.session.add(log)
    db.session.commit()