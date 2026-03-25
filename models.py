from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# ============================================
# MODELO USUARIO
# ============================================
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    nombre = db.Column(db.String(64))
    apellidos = db.Column(db.String(128))
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    activo = db.Column(db.Boolean, default=True)
    
    # Campos para licencias/planes
    plan = db.Column(db.String(20), default='gratis')
    max_propiedades = db.Column(db.Integer, default=3)
    max_reservas = db.Column(db.Integer, default=50)
    licencia_expiracion = db.Column(db.Date, nullable=True)
    
    # Relaciones
    propiedades = db.relationship('Propiedad', back_populates='propietario', lazy='dynamic')
    tareas_asignadas = db.relationship('Tarea', back_populates='asignado_a', lazy='dynamic')
    plataformas_usuario = db.relationship('PlataformaReserva', back_populates='usuario', lazy='dynamic')
    bloqueos_creados = db.relationship('BloqueoPropiedad', back_populates='usuario_creador', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def tiene_licencia_activa(self):
        if not self.licencia_expiracion:
            return True  # Licencia ilimitada
        return self.licencia_expiracion >= datetime.now().date()

    def __repr__(self):
        return f'<User {self.username}>'


# ============================================
# MODELO PROPIEDAD
# ============================================
class Propiedad(db.Model):
    __tablename__ = 'propiedades'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    direccion = db.Column(db.String(200))
    ciudad = db.Column(db.String(100))
    codigo_postal = db.Column(db.String(20))
    pais = db.Column(db.String(50))
    num_habitaciones = db.Column(db.Integer, default=1)
    num_banos = db.Column(db.Integer, default=1)
    capacidad_max = db.Column(db.Integer, default=2)
    precio_noche = db.Column(db.Float, nullable=False)
    moneda = db.Column(db.String(3), default='EUR')
    activa = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Campos de impuestos y retenciones
    tipo_impuesto = db.Column(db.String(10), default='IVA')
    porcentaje_impuesto = db.Column(db.Float, default=7.0)
    aplicar_retencion = db.Column(db.Boolean, default=False)
    porcentaje_retencion = db.Column(db.Float, default=0.0)
    
    # Campos para SES.Hospedajes
    codigo_ses = db.Column(db.String(50))  # Código de establecimiento
    codigo_arrendador = db.Column(db.String(50))  # Código de arrendador
    usuario_ses = db.Column(db.String(50))  # Usuario WS
    password_ses = db.Column(db.String(50))  # Contraseña WS
    
    # Relaciones
    propietario = db.relationship('User', back_populates='propiedades')
    reservas = db.relationship('Reserva', back_populates='propiedad', lazy='dynamic', cascade='all, delete-orphan')
    tareas = db.relationship('Tarea', back_populates='propiedad_rel', lazy='dynamic', cascade='all, delete-orphan')
    calendarios_ical = db.relationship('CalendarioIcal', back_populates='propiedad', lazy='dynamic', cascade='all, delete-orphan')
    habitaciones = db.relationship('Habitacion', back_populates='propiedad', lazy='dynamic', cascade='all, delete-orphan')
    ingresos = db.relationship('Ingreso', back_populates='propiedad', lazy='dynamic')
    gastos = db.relationship('Gasto', back_populates='propiedad', lazy='dynamic')
    bloqueos = db.relationship('BloqueoPropiedad', back_populates='propiedad', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Propiedad {self.nombre}>'


# ============================================
# MODELO HABITACION
# ============================================
class Habitacion(db.Model):
    __tablename__ = 'habitaciones'
    id = db.Column(db.Integer, primary_key=True)
    propiedad_id = db.Column(db.Integer, db.ForeignKey('propiedades.id'), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(50))
    capacidad = db.Column(db.Integer, default=2)
    tiene_bano_suite = db.Column(db.Boolean, default=False)
    camas = db.Column(db.String(100))
    precio_base = db.Column(db.Float, nullable=False)
    activa = db.Column(db.Boolean, default=True)
    orden = db.Column(db.Integer, default=0)
    observaciones = db.Column(db.Text)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones
    propiedad = db.relationship('Propiedad', back_populates='habitaciones')
    reservas = db.relationship('ReservaHabitacion', back_populates='habitacion', lazy='dynamic')
    bloqueos = db.relationship('BloqueoPropiedad', back_populates='habitacion', lazy='dynamic')
    
    def __repr__(self):
        return f'<Habitacion {self.nombre}>'


# ============================================
# MODELO RESERVA
# ============================================
class Reserva(db.Model):
    __tablename__ = 'reservas'
    id = db.Column(db.Integer, primary_key=True)
    propiedad_id = db.Column(db.Integer, db.ForeignKey('propiedades.id'), nullable=False)
    
    # 📊 DATOS DEL GRUPO
    num_huespedes = db.Column(db.Integer, default=1)
    num_menores = db.Column(db.Integer, default=0)
    relacion_parentesco = db.Column(db.String(200), nullable=True)
    
    # 📅 FECHAS
    fecha_entrada = db.Column(db.Date, nullable=False)
    fecha_salida = db.Column(db.Date, nullable=False)
    
    # 💰 ECONÓMICO
    subtotal_habitaciones = db.Column(db.Float, default=0)
    impuesto_aplicado = db.Column(db.Float, default=0)
    total_impuestos = db.Column(db.Float, default=0)
    retencion_aplicada = db.Column(db.Float, default=0)
    retencion_total = db.Column(db.Float, default=0)  # Nota: en tu error aparece 'retención_total'
    precio_total = db.Column(db.Float)
    
    # 💵 PAGOS
    deposito_pagado = db.Column(db.Float, default=0)
    saldo_pendiente = db.Column(db.Float, default=0)
    fecha_pago_total = db.Column(db.Date, nullable=True)
    
    # 📋 ESTADO Y OTROS
    estado = db.Column(db.String(20), default='confirmada')
    notas = db.Column(db.Text)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    origen = db.Column(db.String(50), default='manual')
    external_id = db.Column(db.String(100), unique=True, nullable=True)
    
    # 🔗 RELACIONES
    propiedad = db.relationship('Propiedad', back_populates='reservas')
    tareas = db.relationship('Tarea', back_populates='reserva_rel', lazy='dynamic')
    habitaciones_asignadas = db.relationship('ReservaHabitacion', back_populates='reserva', lazy='dynamic', cascade='all, delete-orphan')
    pagos = db.relationship('PagoReserva', back_populates='reserva', lazy='dynamic', cascade='all, delete-orphan')
    ingresos = db.relationship('Ingreso', back_populates='reserva', lazy='dynamic')
    huespedes = db.relationship('Huesped', back_populates='reserva', lazy='dynamic', cascade='all, delete-orphan')

    def calcular_totales(self):
        """Calcula subtotal, impuestos, retenciones y total de la reserva"""
        noches = (self.fecha_salida - self.fecha_entrada).days
        self.subtotal_habitaciones = sum(rh.precio_aplicado * noches for rh in self.habitaciones_asignadas)
        
        self.total_impuestos = self.subtotal_habitaciones * (self.propiedad.porcentaje_impuesto / 100)
        
        if self.propiedad.aplicar_retencion:
            self.retencion_total = self.subtotal_habitaciones * (self.propiedad.porcentaje_retencion / 100)
        else:
            self.retencion_total = 0
        
        self.precio_total = self.subtotal_habitaciones + self.total_impuestos - self.retencion_total
        self.saldo_pendiente = self.precio_total - self.deposito_pagado
        
        return self.precio_total

    def __repr__(self):
        primer_huesped = self.huespedes.first()
        if primer_huesped:
            return f'<Reserva {self.id} - {primer_huesped.nombre} {primer_huesped.apellidos}>'
        return f'<Reserva {self.id}>'


# ============================================
# MODELO HUÉSPED
# ============================================
class Huesped(db.Model):
    __tablename__ = 'huespedes'
    id = db.Column(db.Integer, primary_key=True)  # 🔴 ESTA LÍNEA ES LA QUE FALTA
    reserva_id = db.Column(db.Integer, db.ForeignKey('reservas.id'), nullable=False)
    
    # Datos personales
    nombre = db.Column(db.String(100), nullable=False)
    apellidos = db.Column(db.String(100), nullable=False)
    sexo = db.Column(db.String(10), nullable=False)
    fecha_nacimiento = db.Column(db.Date, nullable=False)
    nacionalidad = db.Column(db.String(50), nullable=False)
    
    # Documento de identidad (cifrados)
    tipo_documento = db.Column(db.String(20), nullable=False)
    numero_documento = db.Column(db.String(200))   # almacenado cifrado
    numero_soporte = db.Column(db.String(200))     # almacenado cifrado
    
    # Domicilio habitual
    domicilio = db.Column(db.String(200))
    ciudad = db.Column(db.String(100))
    codigo_postal = db.Column(db.String(20))
    pais = db.Column(db.String(50))
    
    # Contacto
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(120))
    
    # Relaciones
    reserva = db.relationship('Reserva', back_populates='huespedes')
    
    # 🔐 Métodos para cifrado/descifrado
    def set_numero_documento(self, valor):
        from utils import encrypt_data
        self.numero_documento = encrypt_data(valor) if valor else None
    
    def get_numero_documento(self):
        from utils import decrypt_data
        return decrypt_data(self.numero_documento)
    
    def set_numero_soporte(self, valor):
        from utils import encrypt_data
        self.numero_soporte = encrypt_data(valor) if valor else None
    
    def get_numero_soporte(self):
        from utils import decrypt_data
        return decrypt_data(self.numero_soporte)
    
    def __repr__(self):
        return f'<Huesped {self.nombre} {self.apellidos}>'

# ============================================
# MODELO RESERVA-HABITACION (ASIGNACIÓN)
# ============================================
class ReservaHabitacion(db.Model):
    __tablename__ = 'reserva_habitaciones'
    id = db.Column(db.Integer, primary_key=True)
    reserva_id = db.Column(db.Integer, db.ForeignKey('reservas.id'), nullable=False)
    habitacion_id = db.Column(db.Integer, db.ForeignKey('habitaciones.id'), nullable=False)
    precio_aplicado = db.Column(db.Float, nullable=False)
    fecha_asignacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones
    reserva = db.relationship('Reserva', back_populates='habitaciones_asignadas')
    habitacion = db.relationship('Habitacion', back_populates='reservas')
    
    def __repr__(self):
        return f'<ReservaHabitacion {self.id}>'


# ============================================
# MODELO PAGO RESERVA
# ============================================
class PagoReserva(db.Model):
    __tablename__ = 'pagos_reserva'
    id = db.Column(db.Integer, primary_key=True)
    reserva_id = db.Column(db.Integer, db.ForeignKey('reservas.id'), nullable=False)
    fecha_pago = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    monto = db.Column(db.Float, nullable=False)
    metodo_pago = db.Column(db.String(50), nullable=False)
    concepto = db.Column(db.String(200))
    referencia = db.Column(db.String(100))
    observaciones = db.Column(db.Text)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    ingreso_id = db.Column(db.Integer, db.ForeignKey('ingresos.id'), nullable=True)
    
    # Relaciones
    reserva = db.relationship('Reserva', back_populates='pagos')
    ingreso = db.relationship('Ingreso', back_populates='pago_asociado', uselist=False)
    
    def __repr__(self):
        return f'<PagoReserva {self.monto}€>'


# ============================================
# MODELO TAREA
# ============================================
class Tarea(db.Model):
    __tablename__ = 'tareas'
    id = db.Column(db.Integer, primary_key=True)
    propiedad_id = db.Column(db.Integer, db.ForeignKey('propiedades.id'), nullable=False)
    reserva_id = db.Column(db.Integer, db.ForeignKey('reservas.id'), nullable=True)
    tipo = db.Column(db.String(50), nullable=False)
    descripcion = db.Column(db.Text)
    fecha_asignada = db.Column(db.Date, nullable=False)
    fecha_limite = db.Column(db.Date)
    completada = db.Column(db.Boolean, default=False)
    fecha_completada = db.Column(db.DateTime)
    asignado_a_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    notas = db.Column(db.Text)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    # Relaciones
    propiedad_rel = db.relationship('Propiedad', back_populates='tareas')
    reserva_rel = db.relationship('Reserva', back_populates='tareas')
    asignado_a = db.relationship('User', back_populates='tareas_asignadas', foreign_keys=[asignado_a_id])

    def __repr__(self):
        return f'<Tarea {self.id} - {self.tipo}>'


# ============================================
# MODELO INGRESO
# ============================================
class Ingreso(db.Model):
    __tablename__ = 'ingresos'
    id = db.Column(db.Integer, primary_key=True)
    propiedad_id = db.Column(db.Integer, db.ForeignKey('propiedades.id'), nullable=True)
    reserva_id = db.Column(db.Integer, db.ForeignKey('reservas.id'), nullable=True)
    fecha = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    concepto = db.Column(db.String(200), nullable=False)
    cantidad = db.Column(db.Float, nullable=False)
    moneda = db.Column(db.String(3), default='EUR')
    metodo_pago = db.Column(db.String(50), nullable=False)
    observaciones = db.Column(db.Text)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    # Relaciones
    propiedad = db.relationship('Propiedad', back_populates='ingresos')
    reserva = db.relationship('Reserva', back_populates='ingresos')
    pago_asociado = db.relationship('PagoReserva', back_populates='ingreso', uselist=False)


# ============================================
# MODELO GASTO
# ============================================
class Gasto(db.Model):
    __tablename__ = 'gastos'
    id = db.Column(db.Integer, primary_key=True)
    propiedad_id = db.Column(db.Integer, db.ForeignKey('propiedades.id'), nullable=True)
    fecha = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    concepto = db.Column(db.String(200), nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    cantidad = db.Column(db.Float, nullable=False)
    moneda = db.Column(db.String(3), default='EUR')
    proveedor = db.Column(db.String(100))
    metodo_pago = db.Column(db.String(50))
    factura_path = db.Column(db.String(200))
    observaciones = db.Column(db.Text)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    # Relaciones
    propiedad = db.relationship('Propiedad', back_populates='gastos')


# ============================================
# MODELO BLOQUEO PROPIEDAD
# ============================================
class BloqueoPropiedad(db.Model):
    __tablename__ = 'bloqueos'
    id = db.Column(db.Integer, primary_key=True)
    propiedad_id = db.Column(db.Integer, db.ForeignKey('propiedades.id'), nullable=False)
    habitacion_id = db.Column(db.Integer, db.ForeignKey('habitaciones.id'), nullable=True)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date, nullable=False)
    motivo = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True)
    creado_por_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones
    propiedad = db.relationship('Propiedad', back_populates='bloqueos')
    habitacion = db.relationship('Habitacion', back_populates='bloqueos')
    usuario_creador = db.relationship('User', back_populates='bloqueos_creados', foreign_keys=[creado_por_id])
    
    def __repr__(self):
        return f'<Bloqueo {self.id} - {self.motivo}>'


# ============================================
# MODELO PLATAFORMA RESERVA
# ============================================
class PlataformaReserva(db.Model):
    __tablename__ = 'plataformas'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    nombre = db.Column(db.String(50), nullable=False)  # airbnb, booking, etc.
    nombre_personalizado = db.Column(db.String(100))
    email_cuenta = db.Column(db.String(120))
    activa = db.Column(db.Boolean, default=True)
    fecha_conexion = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones
    usuario = db.relationship('User', back_populates='plataformas_usuario')
    calendarios_plataforma = db.relationship('CalendarioIcal', back_populates='plataforma', lazy='dynamic')
    
    def __repr__(self):
        return f'<Plataforma {self.nombre_personalizado or self.nombre}>'


# ============================================
# MODELO CALENDARIO ICAL
# ============================================
class CalendarioIcal(db.Model):
    __tablename__ = 'calendarios_ical'
    id = db.Column(db.Integer, primary_key=True)
    propiedad_id = db.Column(db.Integer, db.ForeignKey('propiedades.id'), nullable=False)
    plataforma_id = db.Column(db.Integer, db.ForeignKey('plataformas.id'), nullable=True)
    nombre = db.Column(db.String(100))
    url = db.Column(db.String(500), nullable=False)           # Almacenado cifrado
    plataforma_origen = db.Column(db.String(50))
    ultima_sincronizacion = db.Column(db.DateTime)
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones
    propiedad = db.relationship('Propiedad', back_populates='calendarios_ical')
    plataforma = db.relationship('PlataformaReserva', back_populates='calendarios_plataforma')
    
    # 🔐 Métodos para cifrado/descifrado de URL
    def set_url(self, valor):
        """Guarda la URL cifrada"""
        from utils import encrypt_data
        self.url = encrypt_data(valor) if valor else None
    
    def get_url(self):
        """Obtiene la URL descifrada"""
        from utils import decrypt_data
        return decrypt_data(self.url)
    
    def __repr__(self):
        return f'<CalendarioIcal {self.nombre or self.plataforma_origen}>'
# Añade al final del archivo, pero antes de las relaciones si hay dependencias
class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    usuario = db.relationship('User', foreign_keys=[usuario_id])
    accion = db.Column(db.String(100), nullable=False)      # 'crear', 'ver', 'editar', 'eliminar', 'exportar'
    entidad = db.Column(db.String(50), nullable=False)      # 'reserva', 'huesped', 'propiedad', etc.
    entidad_id = db.Column(db.Integer)
    datos_previos = db.Column(db.Text)                     # JSON con los datos antes del cambio
    datos_nuevos = db.Column(db.Text)                      # JSON con los datos después del cambio
    ip = db.Column(db.String(45))
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

class Consentimiento(db.Model):
    __tablename__ = 'consentimientos'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    huesped_id = db.Column(db.Integer, db.ForeignKey('huespedes.id'), nullable=True)
    version_politica = db.Column(db.String(10), default='1.0')
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    ip = db.Column(db.String(45))
    aceptado = db.Column(db.Boolean, default=True)

# ============================================
# MODELO INQUILINO
# ============================================
class Inquilino(db.Model):
    __tablename__ = 'inquilinos'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellidos = db.Column(db.String(100), nullable=False)
    dni = db.Column(db.String(20))
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(120))

    contratos = db.relationship('Contrato', back_populates='inquilino')

    def __repr__(self):
        return f'<Inquilino {self.nombre} {self.apellidos}>'

# ============================================
# MODELO CONTRATO
# ============================================
class Contrato(db.Model):
    __tablename__ = 'contratos'

    id = db.Column(db.Integer, primary_key=True)
    
    propiedad_id = db.Column(db.Integer, db.ForeignKey('propiedades.id'), nullable=False)
    inquilino_id = db.Column(db.Integer, db.ForeignKey('inquilinos.id'), nullable=False)

    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date)

    renta_mensual = db.Column(db.Float, nullable=False)
    fianza = db.Column(db.Float, default=0)

    estado = db.Column(db.String(20), default='activo')

    propiedad = db.relationship('Propiedad')
    inquilino = db.relationship('Inquilino', back_populates='contratos')

    def __repr__(self):
        return f'<Contrato {self.id}>'

class Acceso(db.Model):
    __tablename__ = 'accesos'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    ip = db.Column(db.String(45))
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    exito = db.Column(db.Boolean, default=False)
    mensaje = db.Column(db.String(200))

# ============================================
# MODELO INQUILINO
# ============================================
class Inquilino(db.Model):
    __tablename__ = 'inquilinos'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellidos = db.Column(db.String(100), nullable=False)
    dni = db.Column(db.String(20))
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(120))

    contratos = db.relationship('Contrato', back_populates='inquilino')

    def __repr__(self):
        return f'<Inquilino {self.nombre} {self.apellidos}>'

# ============================================
# MODELO CONTRATO
# ============================================
class Contrato(db.Model):
    __tablename__ = 'contratos'

    id = db.Column(db.Integer, primary_key=True)
    
    propiedad_id = db.Column(db.Integer, db.ForeignKey('propiedades.id'), nullable=False)
    inquilino_id = db.Column(db.Integer, db.ForeignKey('inquilinos.id'), nullable=False)

    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date)

    renta_mensual = db.Column(db.Float, nullable=False)
    fianza = db.Column(db.Float, default=0)

    estado = db.Column(db.String(20), default='activo')

    propiedad = db.relationship('Propiedad')
    inquilino = db.relationship('Inquilino', back_populates='contratos')

    def __repr__(self):
        return f'<Contrato {self.id}>'

# ============================================
# MODELO RECIBO ALQUILER
# ============================================
class ReciboAlquiler(db.Model):
    __tablename__ = 'recibos_alquiler'

    id = db.Column(db.Integer, primary_key=True)

    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=False)

    fecha_emision = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    periodo = db.Column(db.String(20), nullable=False)  # ej: 2026-03
    concepto = db.Column(db.String(200), nullable=False, default='Alquiler mensual')

    importe_base = db.Column(db.Float, nullable=False, default=0)
    importe_agua = db.Column(db.Float, nullable=False, default=0)
    importe_luz = db.Column(db.Float, nullable=False, default=0)
    otros_importes = db.Column(db.Float, nullable=False, default=0)

    total = db.Column(db.Float, nullable=False, default=0)

    estado = db.Column(db.String(20), default='pendiente')  # pendiente, pagado, parcial
    fecha_pago = db.Column(db.Date, nullable=True)
    metodo_pago = db.Column(db.String(50), nullable=True)
    observaciones = db.Column(db.Text)

    contrato = db.relationship('Contrato', backref='recibos')

    def calcular_total(self):
        self.total = (
            (self.importe_base or 0) +
            (self.importe_agua or 0) +
            (self.importe_luz or 0) +
            (self.otros_importes or 0)
        )
        return self.total

    def __repr__(self):
        return f'<ReciboAlquiler {self.id} - {self.periodo}>'
    cd 'alquiler'
class Recibo(db.Model):
    __tablename__ = "recibos"

    id = db.Column(db.Integer, primary_key=True)
    fecha_emision = db.Column(db.Date, nullable=False)
    fecha_vencimiento = db.Column(db.Date, nullable=False)
    importe_total = db.Column(db.Float, nullable=False)

    estado = db.Column(db.String(20), nullable=False, default="pendiente")  
    # pendiente / pagado / vencido

    fecha_pago = db.Column(db.Date, nullable=True)

    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=False)

    ingreso = db.relationship("Ingreso", back_populates="recibo", uselist=False)

# ============================================
# MODELO CONTADOR SUMINISTRO
# ============================================
class ContadorSuministro(db.Model):
    __tablename__ = 'contadores_suministro'

    id = db.Column(db.Integer, primary_key=True)
    propiedad_id = db.Column(db.Integer, db.ForeignKey('propiedades.id'), nullable=False)

    tipo = db.Column(db.String(20), nullable=False)  # agua, luz, gas
    nombre = db.Column(db.String(100), nullable=False)
    numero_serie = db.Column(db.String(100))
    activo = db.Column(db.Boolean, default=True)

    propiedad = db.relationship('Propiedad', backref='contadores')

    def __repr__(self):
        return f'<Contador {self.tipo} - {self.nombre}>'

# ============================================
# MODELO LECTURA CONTADOR
# ============================================
class LecturaContador(db.Model):
    __tablename__ = 'lecturas_contador'

    id = db.Column(db.Integer, primary_key=True)

    contador_id = db.Column(db.Integer, db.ForeignKey('contadores_suministro.id'), nullable=False)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=True)

    fecha_lectura = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    lectura_anterior = db.Column(db.Float, nullable=False, default=0)
    lectura_actual = db.Column(db.Float, nullable=False, default=0)
    consumo = db.Column(db.Float, nullable=False, default=0)

    precio_unitario = db.Column(db.Float, nullable=False, default=0)
    importe_total = db.Column(db.Float, nullable=False, default=0)

    observaciones = db.Column(db.Text)

    contador = db.relationship('ContadorSuministro', backref='lecturas')
    contrato = db.relationship('Contrato', backref='lecturas_contador')

    def calcular_consumo(self):
        self.consumo = (self.lectura_actual or 0) - (self.lectura_anterior or 0)
        if self.consumo < 0:
            self.consumo = 0
        self.importe_total = self.consumo * (self.precio_unitario or 0)
        return self.importe_total

    def __repr__(self):
        return f'<LecturaContador {self.id}>'

from datetime import date
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Ingreso(db.Model):
    __tablename__ = "ingresos"

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False, default=date.today)
    concepto = db.Column(db.String(255), nullable=False)
    importe = db.Column(db.Float, nullable=False)
    tipo = db.Column(db.String(50), nullable=False, default="alquiler")

    # Relación opcional con recibo para trazabilidad
    recibo_id = db.Column(db.Integer, db.ForeignKey("recibos.id"), nullable=True, unique=True)

    creado_en = db.Column(db.DateTime, server_default=db.func.now())

    recibo = db.relationship("Recibo", back_populates="ingreso")
