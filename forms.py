from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TextAreaField, FloatField, IntegerField, SelectField, DateField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, Optional, NumberRange
from models import User
from datetime import datetime

# ============================================
# FORMULARIOS DE AUTENTICACIÓN
# ============================================

class LoginForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    remember_me = BooleanField('Recordarme')
    submit = SubmitField('Iniciar Sesión')


class RegistrationForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    password2 = PasswordField('Repetir Contraseña', validators=[DataRequired(), EqualTo('password')])
    nombre = StringField('Nombre')
    apellidos = StringField('Apellidos')
    submit = SubmitField('Registrarse')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Este nombre de usuario ya está en uso.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Este email ya está registrado.')


# ============================================
# FORMULARIOS DE PROPIEDAD
# ============================================

class PropiedadForm(FlaskForm):
    nombre = StringField('Nombre de la propiedad', validators=[DataRequired()])
    descripcion = TextAreaField('Descripción', validators=[Optional()])
    direccion = StringField('Dirección', validators=[Optional()])
    ciudad = StringField('Ciudad', validators=[Optional()])
    codigo_postal = StringField('Código Postal', validators=[Optional()])
    pais = StringField('País', validators=[Optional()])
    num_habitaciones = IntegerField('Número de habitaciones', validators=[Optional(), NumberRange(min=0)])
    num_banos = IntegerField('Número de baños', validators=[Optional(), NumberRange(min=0)])
    capacidad_max = IntegerField('Capacidad máxima', validators=[Optional(), NumberRange(min=1)])
    precio_noche = FloatField('Precio por noche (base)', validators=[DataRequired(), NumberRange(min=0)])
    moneda = SelectField('Moneda', choices=[('EUR', 'Euro'), ('USD', 'Dólar'), ('GBP', 'Libra')], default='EUR')
    activa = BooleanField('Activa', default=True)
    
    # Campos de impuestos y retenciones
    tipo_impuesto = SelectField('Tipo de impuesto', choices=[
        ('IVA', 'IVA'),
        ('IGIC', 'IGIC (Canarias)'),
        ('OTRO', 'Otro')
    ], default='IVA')
    porcentaje_impuesto = FloatField('Porcentaje de impuesto', validators=[DataRequired(), NumberRange(min=0, max=100)], default=7.0)
    aplicar_retencion = BooleanField('¿Aplicar retención? (IRPF)', default=False)
    porcentaje_retencion = FloatField('Porcentaje de retención', validators=[Optional(), NumberRange(min=0, max=100)], default=0.0)
    
    submit = SubmitField('Guardar propiedad')


# ============================================
# FORMULARIO DE HABITACIONES
# ============================================

class HabitacionForm(FlaskForm):
    nombre = StringField('Nombre de la habitación', validators=[DataRequired()])
    tipo = SelectField('Tipo', choices=[
        ('individual', 'Individual'),
        ('doble', 'Doble'),
        ('suite', 'Suite'),
        ('familiar', 'Familiar'),
        ('otro', 'Otro')
    ], default='doble')
    capacidad = IntegerField('Capacidad (personas)', validators=[DataRequired(), NumberRange(min=1)], default=2)
    tiene_bano_suite = BooleanField('¿Tiene baño suite?', default=False)
    camas = StringField('Tipo de camas (ej: 1 cama king, 2 individuales)', validators=[Optional()])
    precio_base = FloatField('Precio base por noche (sin impuestos)', validators=[DataRequired(), NumberRange(min=0)])
    activa = BooleanField('Activa', default=True)
    orden = IntegerField('Orden (para listados)', default=0)
    observaciones = TextAreaField('Observaciones', validators=[Optional()])
    submit = SubmitField('Guardar habitación')


# ============================================
# FORMULARIO DE RESERVAS
# ============================================

class ReservaForm(FlaskForm):
    propiedad_id = SelectField('Propiedad', coerce=int, validators=[DataRequired()])
    
    # Datos personales (obligatorios por ley)
    huesped_nombre = StringField('Nombre', validators=[DataRequired()])
    huesped_apellidos = StringField('Apellidos', validators=[DataRequired()])
    huesped_sexo = SelectField('Sexo', choices=[
        ('', '-- Selecciona --'),
        ('Hombre', 'Hombre'),
        ('Mujer', 'Mujer'),
        ('Otro', 'Otro')
    ], validators=[DataRequired()])
    huesped_fecha_nacimiento = DateField('Fecha de nacimiento', validators=[DataRequired()], format='%Y-%m-%d')
    huesped_nacionalidad = SelectField('Nacionalidad', choices=[], validators=[DataRequired()])
    
    # Documento de identidad
    huesped_tipo_documento = SelectField('Tipo de documento', choices=[
        ('', '-- Selecciona --'),
        ('DNI', 'DNI'),
        ('NIE', 'NIE'),
        ('Pasaporte', 'Pasaporte')
    ], validators=[DataRequired()])
    huesped_numero_documento = StringField('Número de documento', validators=[DataRequired()])
    huesped_numero_soporte = StringField('Número de soporte (IDESP/TIE)', validators=[Optional()])
    
    # Domicilio habitual
    huesped_domicilio = StringField('Domicilio (calle y número)', validators=[DataRequired()])
    huesped_ciudad = StringField('Ciudad', validators=[DataRequired()])
    huesped_codigo_postal = StringField('Código postal', validators=[DataRequired()])
    huesped_pais = StringField('País', validators=[DataRequired()])
    
    # Contacto
    huesped_telefono = StringField('Teléfono móvil', validators=[DataRequired()])
    huesped_email = StringField('Email', validators=[DataRequired(), Email()])
    
    # Composición del grupo
    num_huespedes = IntegerField('Número total de viajeros', validators=[DataRequired(), NumberRange(min=1)], default=1)
    num_menores = IntegerField('Número de menores (menos de 14 años)', validators=[Optional(), NumberRange(min=0)], default=0)
    relacion_parentesco = StringField('Relación/parentesco entre viajeros', validators=[Optional()])
    
    # Fechas
    fecha_entrada = DateField('Fecha de entrada', validators=[DataRequired()], format='%Y-%m-%d')
    fecha_salida = DateField('Fecha de salida', validators=[DataRequired()], format='%Y-%m-%d')
    
    # Otros
    estado = SelectField('Estado', choices=[
        ('confirmada', 'Confirmada'),
        ('pendiente', 'Pendiente'),
        ('cancelada', 'Cancelada')
    ], default='confirmada')
    notas = TextAreaField('Notas', validators=[Optional()])
    origen = SelectField('Origen', choices=[
        ('manual', 'Manual'),
        ('airbnb', 'Airbnb'),
        ('booking', 'Booking'),
        ('otro', 'Otro')
    ], default='manual')
    external_id = StringField('ID externo (Airbnb/Booking)', validators=[Optional()])
    
    submit = SubmitField('Guardar reserva')

    def __init__(self, *args, **kwargs):
        super(ReservaForm, self).__init__(*args, **kwargs)
        self.huesped_nacionalidad.choices = [
            ('', '-- Selecciona --'),
            ('ES', 'España'),
            ('FR', 'Francia'),
            ('IT', 'Italia'),
            ('DE', 'Alemania'),
            ('UK', 'Reino Unido'),
            ('US', 'Estados Unidos'),
            ('PT', 'Portugal'),
            ('OTRO', 'Otro')
        ]


# ============================================
# FORMULARIO DE PAGOS DE RESERVA
# ============================================

class PagoReservaForm(FlaskForm):
    fecha_pago = DateField('Fecha del pago', validators=[DataRequired()], format='%Y-%m-%d', default=datetime.today)
    monto = FloatField('Importe', validators=[DataRequired(), NumberRange(min=0.01)])
    metodo_pago = SelectField('Método de pago', choices=[
        ('transferencia', 'Transferencia bancaria'),
        ('visa', 'Tarjeta Visa/Mastercard'),
        ('bizum', 'Bizum'),
        ('efectivo', 'Efectivo'),
        ('paypal', 'PayPal'),
        ('otro', 'Otro')
    ], validators=[DataRequired()])
    
    concepto = SelectField('Concepto', choices=[
        ('señal', 'Señal / Reserva'),
        ('pago_parcial', 'Pago parcial'),
        ('pago_completo', 'Pago completo'),
        ('fianza', 'Fianza'),
        ('otro', 'Otro (especificar)')
    ], default='pago_parcial', validators=[DataRequired()])
    
    concepto_personalizado = StringField('Especificar concepto', validators=[Optional()])
    referencia = StringField('Nº de referencia / Justificante', validators=[Optional()])
    observaciones = TextAreaField('Observaciones', validators=[Optional()])
    
    submit = SubmitField('Registrar pago')
    
    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        
        if self.concepto.data == 'otro' and not self.concepto_personalizado.data:
            self.concepto_personalizado.errors.append('Debes especificar el concepto personalizado')
            return False
        
        return True


# ============================================
# FORMULARIO DE TAREAS
# ============================================

class TareaForm(FlaskForm):
    propiedad_id = SelectField('Propiedad', coerce=int, validators=[DataRequired()])
    reserva_id = SelectField('Asociada a reserva (opcional)', coerce=int, validators=[Optional()])
    tipo = SelectField('Tipo de tarea', choices=[
        ('limpieza', 'Limpieza'),
        ('mantenimiento', 'Mantenimiento'),
        ('revision', 'Revisión'),
        ('reparacion', 'Reparación'),
        ('otro', 'Otro')
    ], validators=[DataRequired()])
    descripcion = TextAreaField('Descripción', validators=[DataRequired()])
    fecha_asignada = DateField('Fecha asignada', validators=[DataRequired()], format='%Y-%m-%d')
    fecha_limite = DateField('Fecha límite', validators=[Optional()], format='%Y-%m-%d')
    asignado_a_id = SelectField('Asignado a', coerce=int, validators=[Optional()])
    notas = TextAreaField('Notas adicionales', validators=[Optional()])
    completada = BooleanField('¿Completada?', default=False)
    submit = SubmitField('Guardar tarea')


# ============================================
# FORMULARIO DE INGRESOS
# ============================================

class IngresoForm(FlaskForm):
    propiedad_id = SelectField('Propiedad', coerce=int, validators=[Optional()])
    reserva_id = SelectField('Reserva asociada', coerce=int, validators=[Optional()])
    fecha = DateField('Fecha', validators=[DataRequired()], format='%Y-%m-%d')
    concepto = StringField('Concepto', validators=[DataRequired()])
    cantidad = FloatField('Cantidad', validators=[DataRequired(), NumberRange(min=0)])
    moneda = SelectField('Moneda', choices=[('EUR', 'Euro'), ('USD', 'Dólar'), ('GBP', 'Libra')], default='EUR')
    metodo_pago = SelectField('Método de pago', choices=[
        ('transferencia', 'Transferencia'),
        ('visa', 'Visa'),
        ('bizum', 'Bizum'),
        ('efectivo', 'Efectivo'),
        ('paypal', 'PayPal'),
        ('otro', 'Otro')
    ], validators=[DataRequired()])
    observaciones = TextAreaField('Observaciones', validators=[Optional()])
    submit = SubmitField('Guardar ingreso')


# ============================================
# FORMULARIO DE GASTOS
# ============================================

class GastoForm(FlaskForm):
    propiedad_id = SelectField('Propiedad', coerce=int, validators=[Optional()])
    fecha = DateField('Fecha', validators=[DataRequired()], format='%Y-%m-%d')
    concepto = StringField('Concepto', validators=[DataRequired()])
    categoria = SelectField('Categoría', choices=[
        ('luz', 'Luz'),
        ('agua', 'Agua'),
        ('gas', 'Gas'),
        ('impuestos', 'Impuestos'),
        ('reparaciones', 'Reparaciones'),
        ('limpieza', 'Limpieza'),
        ('suministros', 'Suministros'),
        ('publicidad', 'Publicidad'),
        ('comisiones', 'Comisiones'),
        ('otros', 'Otros')
    ], validators=[DataRequired()])
    cantidad = FloatField('Cantidad', validators=[DataRequired(), NumberRange(min=0)])
    moneda = SelectField('Moneda', choices=[('EUR', 'Euro'), ('USD', 'Dólar'), ('GBP', 'Libra')], default='EUR')
    proveedor = StringField('Proveedor', validators=[Optional()])
    metodo_pago = SelectField('Método de pago', choices=[
        ('transferencia', 'Transferencia'),
        ('efectivo', 'Efectivo'),
        ('tarjeta', 'Tarjeta'),
        ('otro', 'Otro')
    ], validators=[Optional()])
    observaciones = TextAreaField('Observaciones', validators=[Optional()])
    # Nota: NO hay campo 'pagado' en gastos
    submit = SubmitField('Guardar gasto')

# ============================================
# FORMULARIO DE BLOQUEOS
# ============================================
class BloqueoForm(FlaskForm):
    fecha_inicio = DateField('Fecha de inicio', validators=[DataRequired()], format='%Y-%m-%d')
    fecha_fin = DateField('Fecha de fin', validators=[DataRequired()], format='%Y-%m-%d')
    motivo = SelectField('Motivo', choices=[
        ('mantenimiento', 'Mantenimiento / Reparación'),
        ('reforma', 'Reforma / Obras'),
        ('uso_propietario', 'Uso del propietario'),
        ('personal', 'Uso personal'),
        ('otros', 'Otros')
    ], validators=[DataRequired()])
    descripcion = TextAreaField('Descripción', validators=[Optional()])
    habitacion_id = SelectField('Afecta a', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Crear bloqueo')

        



# ============================================
# FORMULARIO DE PLATAFORMAS
# ============================================

class PlataformaForm(FlaskForm):
    nombre = SelectField('Plataforma', choices=[
        ('airbnb', 'Airbnb'),
        ('booking', 'Booking.com'),
        ('vbro', 'VRBO'),
        ('expedia', 'Expedia'),
        ('otros', 'Otras')
    ], validators=[DataRequired()])
    nombre_personalizado = StringField('Nombre personalizado (opcional)', validators=[Optional()])
    email_cuenta = StringField('Email de la cuenta', validators=[Optional(), Email()])
    submit = SubmitField('Conectar plataforma')


# ============================================
# FORMULARIO DE CALENDARIO ICAL
# ============================================

class IcalForm(FlaskForm):
    propiedad_id = SelectField('Propiedad', coerce=int, validators=[DataRequired()])
    nombre = StringField('Nombre (ej. Airbnb, Booking)', validators=[Optional()])
    url = StringField('URL del feed iCal', validators=[DataRequired()])
    plataforma = SelectField('Plataforma', choices=[
        ('airbnb', 'Airbnb'),
        ('booking', 'Booking'),
        ('vbro', 'VRBO'),
        ('otro', 'Otro')
    ], default='airbnb')
    activo = BooleanField('Activo', default=True)
    submit = SubmitField('Guardar feed')

class HuespedForm(FlaskForm):
    """Formulario para un huésped individual"""
    nombre = StringField('Nombre', validators=[DataRequired()])
    apellidos = StringField('Apellidos', validators=[DataRequired()])
    sexo = SelectField('Sexo', choices=[
        ('', '-- Selecciona --'),
        ('Hombre', 'Hombre'),
        ('Mujer', 'Mujer'),
        ('Otro', 'Otro')
    ], validators=[DataRequired()])
    fecha_nacimiento = DateField('Fecha de nacimiento', validators=[DataRequired()], format='%Y-%m-%d')
    nacionalidad = SelectField('Nacionalidad', choices=[], validators=[DataRequired()])
    
    tipo_documento = SelectField('Tipo de documento', choices=[
        ('', '-- Selecciona --'),
        ('DNI', 'DNI'),
        ('NIE', 'NIE'),
        ('Pasaporte', 'Pasaporte')
    ], validators=[DataRequired()])
    numero_documento = StringField('Número de documento', validators=[DataRequired()])
    numero_soporte = StringField('Número de soporte (IDESP/TIE)', validators=[Optional()])
    
    # Campos opcionales (si son diferentes del titular)
    mismo_domicilio = BooleanField('Mismo domicilio que el titular', default=True)
    domicilio = StringField('Domicilio', validators=[Optional()])
    ciudad = StringField('Ciudad', validators=[Optional()])
    codigo_postal = StringField('Código postal', validators=[Optional()])
    pais = StringField('País', validators=[Optional()])
    telefono = StringField('Teléfono', validators=[Optional()])
    email = StringField('Email', validators=[Optional(), Email()])
    
    submit = SubmitField('Añadir huésped')

class ReservaForm(FlaskForm):
    propiedad_id = SelectField('Propiedad', coerce=int, validators=[DataRequired()])
    
    # ✅ SOLO estos campos (SIN datos de huésped)
    num_huespedes = IntegerField('Número total de viajeros', validators=[DataRequired(), NumberRange(min=1)], default=1)
    num_menores = IntegerField('Número de menores (menos de 14 años)', validators=[Optional(), NumberRange(min=0)], default=0)
    relacion_parentesco = StringField('Relación/parentesco entre viajeros', validators=[Optional()])
    
    fecha_entrada = DateField('Fecha de entrada', validators=[DataRequired()], format='%Y-%m-%d')
    fecha_salida = DateField('Fecha de salida', validators=[DataRequired()], format='%Y-%m-%d')
    
    estado = SelectField('Estado', choices=[
        ('confirmada', 'Confirmada'),
        ('pendiente', 'Pendiente'),
        ('cancelada', 'Cancelada')
    ], default='confirmada')
    notas = TextAreaField('Notas', validators=[Optional()])
    origen = SelectField('Origen', choices=[
        ('manual', 'Manual'),
        ('airbnb', 'Airbnb'),
        ('booking', 'Booking'),
        ('otro', 'Otro')
    ], default='manual')
    external_id = StringField('ID externo (Airbnb/Booking)', validators=[Optional()])
    
    submit = SubmitField('Guardar reserva')