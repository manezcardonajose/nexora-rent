from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class Acceso(db.Model):
    __tablename__ = 'accesos'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    ip = db.Column(db.String(45))
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    exito = db.Column(db.Boolean, default=False)
    mensaje = db.Column(db.String(200))

    def __repr__(self):
        return f'<Acceso {self.usuario_id} - {self.exito}>'


class Cuenta(db.Model):
    __tablename__ = 'cuentas'

    id = db.Column(db.Integer, primary_key=True)
    tipo_titular = db.Column(db.String(20), default='persona')
    nombre_fiscal = db.Column(db.String(150), nullable=False)
    nif_cif = db.Column(db.String(30))
    direccion = db.Column(db.String(255))
    ciudad = db.Column(db.String(100))
    codigo_postal = db.Column(db.String(20))
    pais = db.Column(db.String(50), default='España')
    telefono = db.Column(db.String(30))
    email = db.Column(db.String(120))
    activa = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    usuarios = db.relationship('User', back_populates='cuenta', lazy='dynamic')
    propiedades = db.relationship('Propiedad', back_populates='cuenta', lazy='dynamic')
    representantes = db.relationship(
        'RepresentanteCuenta',
        back_populates='cuenta',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )


class RepresentanteCuenta(db.Model):
    __tablename__ = 'representantes_cuenta'

    id = db.Column(db.Integer, primary_key=True)
    cuenta_id = db.Column(db.Integer, db.ForeignKey('cuentas.id'), nullable=False)

    nombre = db.Column(db.String(150), nullable=False)
    dni = db.Column(db.String(30))
    cargo = db.Column(db.String(100))
    telefono = db.Column(db.String(30))
    email = db.Column(db.String(120))

    es_firmante = db.Column(db.Boolean, default=False)
    activo = db.Column(db.Boolean, default=True)
    firma_en_nombre_de = db.Column(db.String(150))

    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    cuenta = db.relationship('Cuenta', back_populates='representantes')


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    PLAN_LABELS = {
        'demo': 'Demo',
        'trial': 'Trial',
        'activa': 'Activa',
        'vitalicia': 'Vitalicia',
        'pro': 'Activa',
        'premium': 'Activa',
        'gratis': 'Demo',
    }

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))

    nombre = db.Column(db.String(64))
    apellidos = db.Column(db.String(128))

    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    activo = db.Column(db.Boolean, default=True)

    plan = db.Column(db.String(20), default='gratis')
    rol = db.Column(db.String(20), default='demo')

    max_propiedades = db.Column(db.Integer, default=3)
    max_reservas = db.Column(db.Integer, default=50)

    licencia_expiracion = db.Column(db.Date, nullable=True)
    licencia_clave = db.Column(db.String(100), unique=True, nullable=True)

    puede_admin = db.Column(db.Boolean, default=False)

    cuenta_id = db.Column(db.Integer, db.ForeignKey('cuentas.id'), nullable=True)

    es_principal = db.Column(db.Boolean, default=False)

    puede_gestionar_usuarios = db.Column(db.Boolean, default=False)
    puede_gestionar_propiedades = db.Column(db.Boolean, default=False)
    puede_gestionar_contratos = db.Column(db.Boolean, default=False)
    puede_gestionar_reservas = db.Column(db.Boolean, default=False)
    puede_gestionar_finanzas = db.Column(db.Boolean, default=False)
    puede_gestionar_tareas = db.Column(db.Boolean, default=False)
    puede_ver_informes = db.Column(db.Boolean, default=True)

    cuenta = db.relationship('Cuenta', back_populates='usuarios')

    propiedades = db.relationship('Propiedad', back_populates='propietario', lazy='dynamic')
    tareas_asignadas = db.relationship('Tarea', back_populates='asignado_a', lazy='dynamic')
    plataformas_usuario = db.relationship('PlataformaReserva', back_populates='usuario', lazy='dynamic')
    bloqueos_creados = db.relationship('BloqueoPropiedad', back_populates='usuario_creador', lazy='dynamic')

    def es_admin(self):
        return self.rol == 'admin' or self.puede_admin is True

    def plan_normalizado(self):
        plan = (self.plan or '').strip().lower()
        equivalencias = {
            'gratis': 'demo',
            'pro': 'activa',
            'premium': 'activa',
        }
        return equivalencias.get(plan, plan or 'demo')

    def plan_label(self):
        return self.PLAN_LABELS.get((self.plan or '').strip().lower(), (self.plan or 'Demo').title())

    def licencia_caducada(self):
        if self.es_admin() or not self.activo:
            return False
        if not self.licencia_expiracion:
            return False
        return self.licencia_expiracion < datetime.utcnow().date()

    def licencia_activa(self):
        if self.es_admin():
            return True
        if not self.activo:
            return False
        return not self.licencia_caducada()

    def en_modo_restringido(self):
        return self.activo and not self.es_admin() and self.licencia_caducada()

    def puede_crear_propiedad(self):
        if self.es_admin():
            return True
        if not self.licencia_activa():
            return False
        return self.propiedades.count() < (self.max_propiedades or 0)

    def total_reservas_usuario(self):
        total = 0
        for prop in self.propiedades.all():
            total += prop.reservas.count()
        return total

    def puede_crear_reserva(self):
        if self.es_admin():
            return True
        if not self.licencia_activa():
            return False
        return self.total_reservas_usuario() < (self.max_reservas or 0)

    def puede_firmar_contratos(self):
        return self.es_admin() or self.es_principal or self.puede_gestionar_contratos

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def nombre_completo(self):
        return f"{self.nombre or ''} {self.apellidos or ''}".strip()

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
    municipio = db.Column(db.String(100))
    codigo_postal = db.Column(db.String(20))
    pais = db.Column(db.String(50))

    referencia_catastral = db.Column(db.String(50))
    tipo_inmueble = db.Column(db.String(50))

    gastos_individuales_texto = db.Column(db.Text)
    suministros_incluidos_texto = db.Column(db.Text)
    caracteristicas_tecnicas_texto = db.Column(db.Text)
    contacto_administracion_texto = db.Column(db.Text)
    iban_cobro = db.Column(db.String(64))
    entidad_bancaria = db.Column(db.String(100))
    concepto_transferencia = db.Column(db.String(150))

    num_habitaciones = db.Column(db.Integer, default=1)
    num_banos = db.Column(db.Integer, default=1)
    capacidad_max = db.Column(db.Integer, default=2)

    precio_noche = db.Column(db.Float, nullable=False)
    moneda = db.Column(db.String(3), default='EUR')

    activa = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    cuenta_id = db.Column(db.Integer, db.ForeignKey('cuentas.id'), nullable=True)

    tipo_impuesto = db.Column(db.String(10), default='IVA')
    porcentaje_impuesto = db.Column(db.Float, default=7.0)

    aplicar_retencion = db.Column(db.Boolean, default=False)
    porcentaje_retencion = db.Column(db.Float, default=0.0)

    codigo_ses = db.Column(db.String(50))
    codigo_arrendador = db.Column(db.String(50))
    usuario_ses = db.Column(db.String(50))
    password_ses = db.Column(db.String(50))

    propietario = db.relationship('User', back_populates='propiedades')
    cuenta = db.relationship('Cuenta', back_populates='propiedades')

    reservas = db.relationship('Reserva', back_populates='propiedad', lazy='dynamic', cascade='all, delete-orphan')
    tareas = db.relationship('Tarea', back_populates='propiedad_rel', lazy='dynamic', cascade='all, delete-orphan')
    calendarios_ical = db.relationship('CalendarioIcal', back_populates='propiedad', lazy='dynamic', cascade='all, delete-orphan')
    habitaciones = db.relationship('Habitacion', back_populates='propiedad', lazy='dynamic', cascade='all, delete-orphan')
    ingresos = db.relationship('Ingreso', back_populates='propiedad', lazy='dynamic')
    gastos = db.relationship('Gasto', back_populates='propiedad', lazy='dynamic')
    bloqueos = db.relationship('BloqueoPropiedad', back_populates='propiedad', lazy='dynamic', cascade='all, delete-orphan')

    contadores = db.relationship('ContadorSuministro', back_populates='propiedad', lazy='dynamic', cascade='all, delete-orphan')
    contratos_larga = db.relationship('Contrato', back_populates='propiedad', lazy='dynamic', cascade='all, delete-orphan')
    recibos_generales = db.relationship('Recibo', back_populates='propiedad', lazy='dynamic', cascade='all, delete-orphan')

    def titular_nombre(self):
        if self.cuenta:
            return self.cuenta.nombre_fiscal
        if self.propietario:
            nombre = f"{self.propietario.nombre or ''} {self.propietario.apellidos or ''}".strip()
            return nombre or self.propietario.username
        return ''

    def titular_nif(self):
        if self.cuenta:
            return self.cuenta.nif_cif or ''
        return ''

    def direccion_completa(self):
        partes = [
            self.direccion,
            self.codigo_postal,
            self.municipio or self.ciudad,
            self.pais
        ]
        return ", ".join([p for p in partes if p])

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

    num_huespedes = db.Column(db.Integer, default=1)
    num_menores = db.Column(db.Integer, default=0)
    relacion_parentesco = db.Column(db.String(200), nullable=True)

    fecha_entrada = db.Column(db.Date, nullable=False)
    fecha_salida = db.Column(db.Date, nullable=False)

    subtotal_habitaciones = db.Column(db.Float, default=0)
    impuesto_aplicado = db.Column(db.Float, default=0)
    total_impuestos = db.Column(db.Float, default=0)
    retencion_aplicada = db.Column(db.Float, default=0)
    retencion_total = db.Column(db.Float, default=0)
    precio_total = db.Column(db.Float)

    deposito_pagado = db.Column(db.Float, default=0)
    saldo_pendiente = db.Column(db.Float, default=0)
    fecha_pago_total = db.Column(db.Date, nullable=True)

    estado = db.Column(db.String(20), default='confirmada')
    notas = db.Column(db.Text)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    origen = db.Column(db.String(50), default='manual')
    external_id = db.Column(db.String(100), unique=True, nullable=True)

    propiedad = db.relationship('Propiedad', back_populates='reservas')
    tareas = db.relationship('Tarea', back_populates='reserva_rel', lazy='dynamic')
    habitaciones_asignadas = db.relationship('ReservaHabitacion', back_populates='reserva', lazy='dynamic', cascade='all, delete-orphan')
    pagos = db.relationship('PagoReserva', back_populates='reserva', lazy='dynamic', cascade='all, delete-orphan')
    ingresos = db.relationship('Ingreso', back_populates='reserva', lazy='dynamic')
    huespedes = db.relationship('Huesped', back_populates='reserva', lazy='dynamic', cascade='all, delete-orphan')

    def calcular_totales(self):
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

    id = db.Column(db.Integer, primary_key=True)
    reserva_id = db.Column(db.Integer, db.ForeignKey('reservas.id'), nullable=False)

    nombre = db.Column(db.String(100), nullable=False)
    apellidos = db.Column(db.String(100), nullable=False)
    sexo = db.Column(db.String(10), nullable=False)
    fecha_nacimiento = db.Column(db.Date, nullable=False)
    nacionalidad = db.Column(db.String(50), nullable=False)

    tipo_documento = db.Column(db.String(20), nullable=False)
    numero_documento = db.Column(db.String(200))
    numero_soporte = db.Column(db.String(200))

    domicilio = db.Column(db.String(200))
    ciudad = db.Column(db.String(100))
    codigo_postal = db.Column(db.String(20))
    pais = db.Column(db.String(50))

    telefono = db.Column(db.String(20))
    email = db.Column(db.String(120))

    reserva = db.relationship('Reserva', back_populates='huespedes')

    def set_numero_documento(self, numero):
        self.numero_documento = numero

    def get_numero_documento(self):
        return self.numero_documento

    def set_numero_soporte(self, valor):
        self.numero_soporte = valor if valor else None

    def get_numero_soporte(self):
        return self.numero_soporte

    def __repr__(self):
        return f'<Huesped {self.nombre} {self.apellidos}>'


# ============================================
# MODELO RESERVA-HABITACION
# ============================================
class ReservaHabitacion(db.Model):
    __tablename__ = 'reserva_habitaciones'

    id = db.Column(db.Integer, primary_key=True)
    reserva_id = db.Column(db.Integer, db.ForeignKey('reservas.id'), nullable=False)
    habitacion_id = db.Column(db.Integer, db.ForeignKey('habitaciones.id'), nullable=False)
    precio_aplicado = db.Column(db.Float, nullable=False)
    fecha_asignacion = db.Column(db.DateTime, default=datetime.utcnow)

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
    fecha_pago = db.Column(db.Date, nullable=False, default=date.today)
    monto = db.Column(db.Float, nullable=False)
    metodo_pago = db.Column(db.String(50), nullable=False)
    concepto = db.Column(db.String(200))
    referencia = db.Column(db.String(100))
    observaciones = db.Column(db.Text)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    ingreso_id = db.Column(db.Integer, db.ForeignKey('ingresos.id'), nullable=True)

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

    propiedad_rel = db.relationship('Propiedad', back_populates='tareas')
    reserva_rel = db.relationship('Reserva', back_populates='tareas')
    asignado_a = db.relationship('User', back_populates='tareas_asignadas', foreign_keys=[asignado_a_id])

    def __repr__(self):
        return f'<Tarea {self.id} - {self.tipo}>'


# ============================================
# MODELO INQUILINO
# ============================================
class Inquilino(db.Model):
    __tablename__ = 'inquilinos'

    id = db.Column(db.Integer, primary_key=True)

    nombre = db.Column(db.String(100), nullable=False)
    apellidos = db.Column(db.String(150), nullable=False, default='')
    dni = db.Column(db.String(30))
    nacionalidad = db.Column(db.String(50))
    telefono = db.Column(db.String(30))
    email = db.Column(db.String(120))

    direccion = db.Column(db.String(255))
    codigo_postal = db.Column(db.String(20))
    municipio = db.Column(db.String(100))
    provincia = db.Column(db.String(100))

    fecha_nacimiento = db.Column(db.Date, nullable=True)
    estado_civil = db.Column(db.String(50))

    contratos = db.relationship('Contrato', back_populates='inquilino', lazy='dynamic')
    recibos_generales = db.relationship('Recibo', back_populates='inquilino', lazy='dynamic')

    def __repr__(self):
        return f'<Inquilino {self.nombre} {self.apellidos}>'

    @property
    def nombre_completo(self):
        return f"{self.nombre or ''} {self.apellidos or ''}".strip()

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
    observaciones = db.Column(db.Text)

    propiedad = db.relationship('Propiedad', back_populates='contratos_larga')
    inquilino = db.relationship('Inquilino', back_populates='contratos')

    ingresos_alquiler = db.relationship('Ingreso', back_populates='contrato', lazy='dynamic')
    recibos_generales = db.relationship('Recibo', back_populates='contrato', lazy='dynamic')

        # === FASE 3: señal / adelantados / devoluciones ===
    meses_adelantados = db.Column(db.Integer, default=0)
    importe_meses_adelantados = db.Column(db.Float, default=0)
    devolucion_fianza_texto = db.Column(db.Text)
    devolucion_adelantado_texto = db.Column(db.Text)
    inventario_texto = db.Column(db.Text)

    intervinientes = db.relationship(
        'ContratoInterviniente',
        back_populates='contrato',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    clausulas = db.relationship(
        'ContratoClausula',
        back_populates='contrato',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    fotos = db.relationship(
        'ContratoFoto',
        back_populates='contrato',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    anexos = db.relationship(
        'ContratoAnexo',
        back_populates='contrato',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    def arrendadores(self):
        return self.intervinientes.filter_by(rol='arrendador', activo=True).order_by(ContratoInterviniente.orden.asc()).all()

    def arrendatarios(self):
        return self.intervinientes.filter_by(rol='arrendatario', activo=True).order_by(ContratoInterviniente.orden.asc()).all()

    def avalistas(self):
        return self.intervinientes.filter_by(rol='avalista', activo=True).order_by(ContratoInterviniente.orden.asc()).all()

    def representantes(self):
        return self.intervinientes.filter_by(rol='representante', activo=True).order_by(ContratoInterviniente.orden.asc()).all()

    def clausulas_activas(self):
        return self.clausulas.filter_by(activa=True).order_by(ContratoClausula.orden.asc()).all()

    @property
    def activo(self):
        return self.estado == 'activo'

    @property
    def precio_mensual(self):
        return self.renta_mensual


    def __repr__(self):
        return f'<Contrato {self.id}>'

# ============================================
# PLANTILLAS DE CLÁUSULAS
# ============================================
class PlantillaClausula(db.Model):
    __tablename__ = 'plantillas_clausulas'

    id = db.Column(db.Integer, primary_key=True)

    codigo = db.Column(db.String(50), unique=True)
    tipo_contrato = db.Column(db.String(50), default='larga_duracion')  # larga_duracion, vacacional, otro

    titulo = db.Column(db.String(150), nullable=False)
    contenido = db.Column(db.Text, nullable=False)

    orden_defecto = db.Column(db.Integer, default=0)
    activa = db.Column(db.Boolean, default=True)
    editable = db.Column(db.Boolean, default=True)

    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<PlantillaClausula {self.titulo}>'

class ContratoFoto(db.Model):
    __tablename__ = 'contratos_fotos'

    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=False)
    habitacion_id = db.Column(db.Integer, db.ForeignKey('habitaciones.id'), nullable=True)

    titulo = db.Column(db.String(150))
    ruta = db.Column(db.String(255), nullable=False)
    descripcion = db.Column(db.Text)

    orden = db.Column(db.Integer, default=0)
    activa = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    contrato = db.relationship('Contrato', back_populates='fotos')
    habitacion = db.relationship('Habitacion')

    def __repr__(self):
        return f'<ContratoFoto {self.id} - {self.titulo or self.ruta}>'


class ContratoAnexo(db.Model):
    __tablename__ = 'contratos_anexos'

    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=False)
    habitacion_id = db.Column(db.Integer, db.ForeignKey('habitaciones.id'), nullable=True)

    titulo = db.Column(db.String(150), nullable=False)
    contenido = db.Column(db.Text)
    tipo = db.Column(db.String(50), default='inventario')  # inventario, normas, otro

    orden = db.Column(db.Integer, default=0)
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    contrato = db.relationship('Contrato', back_populates='anexos')
    habitacion = db.relationship('Habitacion')

    def __repr__(self):
        return f'<ContratoAnexo {self.id} - {self.titulo}>'
# ============================================
# INTERVINIENTES DEL CONTRATO
# ============================================
class ContratoInterviniente(db.Model):
    __tablename__ = 'contratos_intervinientes'

    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=False)

    rol = db.Column(db.String(30), nullable=False)
    # arrendador / arrendatario / avalista / representante

    nombre = db.Column(db.String(150), nullable=False)
    dni = db.Column(db.String(30))
    telefono = db.Column(db.String(30))
    email = db.Column(db.String(120))
    direccion = db.Column(db.String(255))

    firma_en_nombre_de = db.Column(db.String(150))
    observaciones = db.Column(db.Text)

    orden = db.Column(db.Integer, default=0)
    activo = db.Column(db.Boolean, default=True)

    contrato = db.relationship('Contrato', back_populates='intervinientes')

    def __repr__(self):
        return f'<ContratoInterviniente {self.rol} - {self.nombre}>'

class ContratoClausula(db.Model):
    __tablename__ = 'contratos_clausulas'

    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=False)
    plantilla_id = db.Column(db.Integer, db.ForeignKey('plantillas_clausulas.id'), nullable=True)

    titulo = db.Column(db.String(150), nullable=False)
    contenido = db.Column(db.Text, nullable=False)
    orden = db.Column(db.Integer, default=0)
    activa = db.Column(db.Boolean, default=True)
    editable = db.Column(db.Boolean, default=True)

    contrato = db.relationship('Contrato', back_populates='clausulas')
    plantilla = db.relationship('PlantillaClausula')

    def __repr__(self):
        return f'<ContratoClausula {self.titulo}>'


# ============================================
# MODELO RECIBO ALQUILER (LEGACY)
# ============================================
class ReciboAlquiler(db.Model):
    __tablename__ = 'recibos_alquiler'

    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=False)

    fecha_emision = db.Column(db.Date, nullable=False, default=date.today)
    periodo = db.Column(db.String(20), nullable=False)
    concepto = db.Column(db.String(200), nullable=False, default='Alquiler mensual')

    importe_base = db.Column(db.Float, nullable=False, default=0)
    importe_agua = db.Column(db.Float, nullable=False, default=0)
    importe_luz = db.Column(db.Float, nullable=False, default=0)
    otros_importes = db.Column(db.Float, nullable=False, default=0)
    total = db.Column(db.Float, nullable=False, default=0)

    estado = db.Column(db.String(20), default='pendiente')
    fecha_pago = db.Column(db.Date, nullable=True)
    metodo_pago = db.Column(db.String(50), nullable=True)
    observaciones = db.Column(db.Text)

    contrato = db.relationship('Contrato', backref='recibos')
    ingreso_generado = db.relationship('Ingreso', back_populates='recibo_alquiler', uselist=False)

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


# ============================================
# MODELO CONTADOR SUMINISTRO
# ============================================
class ContadorSuministro(db.Model):
    __tablename__ = 'contadores_suministro'

    id = db.Column(db.Integer, primary_key=True)
    propiedad_id = db.Column(db.Integer, db.ForeignKey('propiedades.id'), nullable=False)

    tipo = db.Column(db.String(20), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    numero_serie = db.Column(db.String(100))
    activo = db.Column(db.Boolean, default=True)

    propiedad = db.relationship('Propiedad', back_populates='contadores')
    lecturas = db.relationship('LecturaContador', back_populates='contador', lazy='dynamic', cascade='all, delete-orphan')

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

    fecha_lectura = db.Column(db.Date, nullable=False, default=date.today)
    lectura_anterior = db.Column(db.Float, nullable=False, default=0)
    lectura_actual = db.Column(db.Float, nullable=False, default=0)
    consumo = db.Column(db.Float, nullable=False, default=0)

    precio_unitario = db.Column(db.Float, nullable=False, default=0)
    importe_total = db.Column(db.Float, nullable=False, default=0)

    observaciones = db.Column(db.Text)

    contador = db.relationship('ContadorSuministro', back_populates='lecturas')
    contrato = db.relationship('Contrato', backref='lecturas_contador')

    def calcular_consumo(self):
        self.consumo = (self.lectura_actual or 0) - (self.lectura_anterior or 0)
        if self.consumo < 0:
            self.consumo = 0
        self.importe_total = self.consumo * (self.precio_unitario or 0)
        return self.importe_total

    def __repr__(self):
        return f'<LecturaContador {self.id}>'


# ============================================
# NUEVO SISTEMA DE RECIBOS (GENERAL)
# ============================================
class Recibo(db.Model):
    __tablename__ = 'recibos'

    id = db.Column(db.Integer, primary_key=True)

    propiedad_id = db.Column(db.Integer, db.ForeignKey('propiedades.id'), nullable=False)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=True)
    inquilino_id = db.Column(db.Integer, db.ForeignKey('inquilinos.id'), nullable=True)

    numero = db.Column(db.String(50), unique=True)
    fecha_emision = db.Column(db.Date, nullable=False, default=date.today)
    fecha_vencimiento = db.Column(db.Date, nullable=True)

    tipo = db.Column(db.String(50), nullable=False, default='manual')  # alquiler, suministro, manual, mixto
    estado = db.Column(db.String(20), nullable=False, default='pendiente')  # pendiente, pagado, vencido, anulado

    subtotal = db.Column(db.Float, nullable=False, default=0)
    impuestos = db.Column(db.Float, nullable=False, default=0)
    total = db.Column(db.Float, nullable=False, default=0)

    metodo_pago = db.Column(db.String(50), nullable=True)
    fecha_pago = db.Column(db.Date, nullable=True)

    observaciones = db.Column(db.Text, nullable=True)
    instrucciones_pago = db.Column(db.Text, nullable=True)
    leyenda_legal = db.Column(
        db.Text,
        nullable=False,
        default='La mera tenencia o recepción de este recibo no acredita su pago. Solo se considerará abonado cuando vaya acompañado del correspondiente justificante de pago.'
    )

    enviado_email = db.Column(db.Boolean, default=False)
    enviado_whatsapp = db.Column(db.Boolean, default=False)
    origen = db.Column(db.String(50), nullable=True)  # manual, lectura, contrato
    referencia_origen_id = db.Column(db.Integer, nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    propiedad = db.relationship('Propiedad', back_populates='recibos_generales')
    contrato = db.relationship('Contrato', back_populates='recibos_generales')
    inquilino = db.relationship('Inquilino', back_populates='recibos_generales')
    lineas = db.relationship('ReciboLinea', back_populates='recibo', cascade='all, delete-orphan', lazy='dynamic')
    ingreso_generado = db.relationship('Ingreso', back_populates='recibo_general', uselist=False)

    def recalcular(self):
        self.subtotal = sum((linea.importe or 0) for linea in self.lineas)
        self.total = (self.subtotal or 0) + (self.impuestos or 0)
        return self.total

    def __repr__(self):
        return f'<Recibo {self.numero or self.id}>'


class ReciboLinea(db.Model):
    __tablename__ = 'recibos_lineas'

    id = db.Column(db.Integer, primary_key=True)
    recibo_id = db.Column(db.Integer, db.ForeignKey('recibos.id'), nullable=False)

    tipo = db.Column(db.String(50), nullable=False, default='otro')  # alquiler, suministro, extra, ajuste
    concepto = db.Column(db.String(200), nullable=False)

    cantidad = db.Column(db.Float, nullable=False, default=1)
    precio_unitario = db.Column(db.Float, nullable=False, default=0)
    importe = db.Column(db.Float, nullable=False, default=0)

    observaciones = db.Column(db.Text, nullable=True)
    referencia_origen = db.Column(db.String(50), nullable=True)
    referencia_origen_id = db.Column(db.Integer, nullable=True)

    recibo = db.relationship('Recibo', back_populates='lineas')

    def calcular(self):
        self.importe = (self.cantidad or 0) * (self.precio_unitario or 0)
        return self.importe

    def __repr__(self):
        return f'<ReciboLinea {self.id}>'


# ============================================
# MODELO INGRESO
# ============================================
class Ingreso(db.Model):
    __tablename__ = 'ingresos'

    id = db.Column(db.Integer, primary_key=True)

    propiedad_id = db.Column(db.Integer, db.ForeignKey('propiedades.id'), nullable=True)
    reserva_id = db.Column(db.Integer, db.ForeignKey('reservas.id'), nullable=True)

    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=True)
    recibo_alquiler_id = db.Column(db.Integer, db.ForeignKey('recibos_alquiler.id'), nullable=True, unique=True)
    recibo_id = db.Column(db.Integer, db.ForeignKey('recibos.id'), nullable=True, unique=True)

    fecha = db.Column(db.Date, nullable=False, default=date.today)
    concepto = db.Column(db.String(200), nullable=False)
    cantidad = db.Column(db.Float, nullable=False)
    moneda = db.Column(db.String(3), default='EUR')
    metodo_pago = db.Column(db.String(50), nullable=False)
    observaciones = db.Column(db.Text)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    propiedad = db.relationship('Propiedad', back_populates='ingresos')
    reserva = db.relationship('Reserva', back_populates='ingresos')
    pago_asociado = db.relationship('PagoReserva', back_populates='ingreso', uselist=False)

    contrato = db.relationship('Contrato', back_populates='ingresos_alquiler')
    recibo_alquiler = db.relationship('ReciboAlquiler', back_populates='ingreso_generado')
    recibo_general = db.relationship('Recibo', back_populates='ingreso_generado')

    def __repr__(self):
        return f'<Ingreso {self.id} - {self.concepto}>'


# ============================================
# MODELO GASTO
# ============================================
class Gasto(db.Model):
    __tablename__ = 'gastos'

    id = db.Column(db.Integer, primary_key=True)
    propiedad_id = db.Column(db.Integer, db.ForeignKey('propiedades.id'), nullable=True)
    reserva_id = db.Column(db.Integer, db.ForeignKey('reservas.id'), nullable=True)

    fecha = db.Column(db.Date, nullable=False, default=date.today)
    concepto = db.Column(db.String(200), nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    cantidad = db.Column(db.Float, nullable=False)
    moneda = db.Column(db.String(3), default='EUR')
    proveedor = db.Column(db.String(100))
    metodo_pago = db.Column(db.String(50))
    factura_path = db.Column(db.String(200))
    observaciones = db.Column(db.Text)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    propiedad = db.relationship('Propiedad', back_populates='gastos')
    reserva = db.relationship('Reserva', backref='gastos_imputados')

    def __repr__(self):
        return f'<Gasto {self.id} - {self.concepto}>'


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
    nombre = db.Column(db.String(50), nullable=False)
    nombre_personalizado = db.Column(db.String(100))
    email_cuenta = db.Column(db.String(120))
    activa = db.Column(db.Boolean, default=True)
    fecha_conexion = db.Column(db.DateTime, default=datetime.utcnow)

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
    url = db.Column(db.String(500), nullable=False)
    plataforma_origen = db.Column(db.String(50))
    ultima_sincronizacion = db.Column(db.DateTime)
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    propiedad = db.relationship('Propiedad', back_populates='calendarios_ical')
    plataforma = db.relationship('PlataformaReserva', back_populates='calendarios_plataforma')

    def set_url(self, valor):
        self.url = valor if valor else None

    def get_url(self):
        return self.url

    def __repr__(self):
        return f'<CalendarioIcal {self.nombre or self.plataforma_origen}>'


class AuditLog(db.Model):
    __tablename__ = 'audit_log'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    usuario = db.relationship('User', foreign_keys=[usuario_id])
    accion = db.Column(db.String(100), nullable=False)
    entidad = db.Column(db.String(50), nullable=False)
    entidad_id = db.Column(db.Integer)
    datos_previos = db.Column(db.Text)
    datos_nuevos = db.Column(db.Text)
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


# Compatibilidad con módulos antiguos
Pago = PagoReserva
Cliente = Inquilino


class Incidencia(db.Model):
    __tablename__ = 'incidencias'

    id = db.Column(db.Integer, primary_key=True)
    propiedad_id = db.Column(db.Integer, db.ForeignKey('propiedades.id'), nullable=False)
    reserva_id = db.Column(db.Integer, db.ForeignKey('reservas.id'), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    titulo = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.Text)
    categoria = db.Column(db.String(100))
    prioridad = db.Column(db.String(50), default='media')
    estado = db.Column(db.String(50), default='abierta')
    coste = db.Column(db.Float, default=0.0)
    proveedor = db.Column(db.String(150))
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_resolucion = db.Column(db.DateTime, nullable=True)

    propiedad = db.relationship('Propiedad', backref='incidencias')
    reserva = db.relationship('Reserva', backref='incidencias')
    usuario = db.relationship('User', backref='incidencias')

    def __repr__(self):
        return f'<Incidencia {self.titulo}>'