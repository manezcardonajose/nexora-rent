from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

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
    
    # Relaciones - Nombres ÚNICOS
    propiedades = db.relationship('Propiedad', back_populates='propietario', lazy='dynamic')
    tareas_asignadas = db.relationship('Tarea', back_populates='asignado_a', lazy='dynamic')
    plataformas_usuario = db.relationship('PlataformaReserva', back_populates='usuario', lazy='dynamic')  # Cambiado a 'plataformas_usuario'
    bloqueos_creados = db.relationship('BloqueoPropiedad', back_populates='usuario_creador', lazy='dynamic')  # Nueva relación

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


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
    
    # Relaciones - Nombres ÚNICOS y consistentes
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


class Reserva(db.Model):
    __tablename__ = 'reservas'
    id = db.Column(db.Integer, primary_key=True)
    propiedad_id = db.Column(db.Integer, db.ForeignKey('propiedades.id'), nullable=False)
    
    # Ya NO hay campos individuales del huésped principal aquí
    # Los huéspedes se gestionan en la tabla 'huespedes'
    
    # 📊 DATOS DEL GRUPO
    num_huespedes = db.Column(db.Integer, default=1)          # Número total de viajeros
    num_menores = db.Column(db.Integer, default=0)            # Menores de 14 años
    relacion_parentesco = db.Column(db.String(200), nullable=True)  # Relación entre viajeros
    
    # 📅 FECHAS
    fecha_entrada = db.Column(db.Date, nullable=False)
    fecha_salida = db.Column(db.Date, nullable=False)
    
    # 💰 ECONÓMICO
    subtotal_habitaciones = db.Column(db.Float, default=0)
    impuesto_aplicado = db.Column(db.Float, default=0)
    total_impuestos = db.Column(db.Float, default=0)
    retencion_aplicada = db.Column(db.Float, default=0)
    total_retencion = db.Column(db.Float, default=0)
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
   
    # ... otros campos ...
    external_id = db.Column(db.String(100), unique=True, nullable=True)  # nullable=True
    # ...
    
    # 🔗 RELACIONES
    propiedad = db.relationship('Propiedad', back_populates='reservas')
    tareas = db.relationship('Tarea', back_populates='reserva_rel', lazy='dynamic')
    habitaciones_asignadas = db.relationship('ReservaHabitacion', back_populates='reserva', lazy='dynamic', cascade='all, delete-orphan')
    pagos = db.relationship('PagoReserva', back_populates='reserva', lazy='dynamic', cascade='all, delete-orphan')
    ingresos = db.relationship('Ingreso', back_populates='reserva', lazy='dynamic')
    
    # 🆕 NUEVA RELACIÓN: Múltiples huéspedes
    huespedes = db.relationship('Huesped', back_populates='reserva', lazy='dynamic', cascade='all, delete-orphan')

    def calcular_totales(self):
        """Calcula subtotal, impuestos, retenciones y total de la reserva"""
        noches = (self.fecha_salida - self.fecha_entrada).days
        self.subtotal_habitaciones = sum(rh.precio_aplicado * noches for rh in self.habitaciones_asignadas)
        
        self.total_impuestos = self.subtotal_habitaciones * (self.propiedad.porcentaje_impuesto / 100)
        
        if self.propiedad.aplicar_retencion:
            self.total_retencion = self.subtotal_habitaciones * (self.propiedad.porcentaje_retencion / 100)
        else:
            self.total_retencion = 0
        
        self.precio_total = self.subtotal_habitaciones + self.total_impuestos - self.total_retencion
        self.saldo_pendiente = self.precio_total - self.deposito_pagado
        
        return self.precio_total

    def __repr__(self):
        # Mostrar el primer huésped como referencia
        primer_huesped = self.huespedes.first()
        if primer_huesped:
            return f'<Reserva {self.id} - {primer_huesped.nombre} {primer_huesped.apellidos} ({self.huespedes.count()} huespedes)>'
        else:
            return f'<Reserva {self.id} - Sin huéspedes>'

class Huesped(db.Model):
    """Modelo para cada huésped individual en una reserva"""
    __tablename__ = 'huespedes'
    id = db.Column(db.Integer, primary_key=True)
    reserva_id = db.Column(db.Integer, db.ForeignKey('reservas.id'), nullable=False)
    
    # Datos personales
    nombre = db.Column(db.String(100), nullable=False)
    apellidos = db.Column(db.String(100), nullable=False)
    sexo = db.Column(db.String(10), nullable=False)
    fecha_nacimiento = db.Column(db.Date, nullable=False)
    nacionalidad = db.Column(db.String(50), nullable=False)
    
    # Documento de identidad
    tipo_documento = db.Column(db.String(20), nullable=False)
    numero_documento = db.Column(db.String(20), nullable=False)
    numero_soporte = db.Column(db.String(20), nullable=True)
    
    # Domicilio habitual (opcional si es el mismo que el titular)
    domicilio = db.Column(db.String(200))
    ciudad = db.Column(db.String(100))
    codigo_postal = db.Column(db.String(20))
    pais = db.Column(db.String(50))
    
    # Contacto (opcional)
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(120))
    
    # Relaciones
    reserva = db.relationship('Reserva', back_populates='huespedes')
    
    def __repr__(self):
        return f'<Huesped {self.nombre} {self.apellidos}>'


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
    ingreso = db.relationship('Ingreso', back_populates='pago_asociado')
    
    def __repr__(self):
        return f'<PagoReserva {self.monto}€>'


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


class PlataformaReserva(db.Model):
    __tablename__ = 'plataformas'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    nombre = db.Column(db.String(50), nullable=False)
    nombre_personalizado = db.Column(db.String(100))
    email_cuenta = db.Column(db.String(120))
    activa = db.Column(db.Boolean, default=True)
    fecha_conexion = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones - Nombres ÚNICOS
    usuario = db.relationship('User', back_populates='plataformas_usuario')
    calendarios_plataforma = db.relationship('CalendarioIcal', back_populates='plataforma', lazy='dynamic')
    
    def __repr__(self):
        return f'<Plataforma {self.nombre_personalizado or self.nombre}>'


class CalendarioIcal(db.Model):
    __tablename__ = 'calendarios_ical'
    id = db.Column(db.Integer, primary_key=True)
    propiedad_id = db.Column(db.Integer, db.ForeignKey('propiedades.id'), nullable=False)
    plataforma_id = db.Column(db.Integer, db.ForeignKey('plataformas.id'), nullable=True)
    nombre = db.Column(db.String(100))
    url = db.Column(db.String(500), nullable=False)
    plataforma_origen = db.Column(db.String(50))  # airbnb, booking, etc.
    ultima_sincronizacion = db.Column(db.DateTime)
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones - Nombres ÚNICOS
    propiedad = db.relationship('Propiedad', back_populates='calendarios_ical')
    plataforma = db.relationship('PlataformaReserva', back_populates='calendarios_plataforma')
    
    def __repr__(self):
        return f'<CalendarioIcal {self.nombre or self.plataforma_origen}>'