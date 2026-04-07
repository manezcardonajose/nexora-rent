from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_user, logout_user, current_user, login_required
from urllib.parse import urlparse as url_parse
from models import db, User, Consentimiento, Acceso, Cuenta, Propiedad
from forms import LoginForm, RegistrationForm
from utils import log_audit
from email_config import get_email_settings_for_user, save_email_settings_for_user, send_test_email_for_user
from permisos import usuarios_cuenta_actual_query
from datetime import datetime, timedelta
from io import BytesIO
import json

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


def licencia_activa(user):
    if not user.activo:
        return False

    if user.licencia_expiracion:
        return user.licencia_expiracion >= datetime.utcnow().date()

    return True


def puede_gestionar_usuarios_actual():
    if not current_user.is_authenticated:
        return False
    return current_user.es_admin() or current_user.es_principal or current_user.puede_gestionar_usuarios


def asegurar_cuenta_principal(user):
    """
    Adaptación para instalaciones ya existentes.
    Si el usuario aún no tiene cuenta, se le crea una automáticamente
    y se vinculan sus propiedades actuales.
    """
    if user.cuenta_id:
        return

    nombre_fiscal = user.nombre_completo() or user.username

    cuenta = Cuenta(
        tipo_titular='persona',
        nombre_fiscal=nombre_fiscal,
        email=user.email,
        activa=True
    )
    db.session.add(cuenta)
    db.session.flush()

    user.cuenta_id = cuenta.id
    user.es_principal = True
    user.puede_gestionar_usuarios = True
    user.puede_gestionar_propiedades = True
    user.puede_gestionar_contratos = True
    user.puede_gestionar_reservas = True
    user.puede_gestionar_finanzas = True
    user.puede_gestionar_tareas = True
    user.puede_ver_informes = True

    propiedades_usuario = Propiedad.query.filter_by(usuario_id=user.id, cuenta_id=None).all()
    for propiedad in propiedades_usuario:
        propiedad.cuenta_id = cuenta.id

    db.session.commit()


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Inicio de sesión"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = LoginForm()
    user = None
    exito = False
    mensaje = ''

    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()

        if user is None or not user.check_password(form.password.data):
            flash('Usuario o contraseña inválidos', 'danger')
            mensaje = 'Credenciales inválidas'
        elif not user.activo:
            flash('Tu cuenta está inactiva.', 'danger')
            mensaje = 'Cuenta inactiva'
        else:
            asegurar_cuenta_principal(user)

            login_user(user, remember=form.remember_me.data)
            exito = True
            mensaje = 'Login correcto'

            next_page = request.args.get('next')
            if not next_page or url_parse(next_page).netloc != '':
                next_page = url_for('main.dashboard')

            flash('Has iniciado sesión correctamente', 'success')

            acceso = Acceso(
                usuario_id=user.id,
                ip=request.remote_addr,
                exito=True,
                mensaje=mensaje
            )
            db.session.add(acceso)
            db.session.commit()

            return redirect(next_page)

    if not exito and form.validate_on_submit():
        acceso = Acceso(
            usuario_id=user.id if user else None,
            ip=request.remote_addr,
            exito=False,
            mensaje=mensaje or 'Login fallido'
        )
        db.session.add(acceso)
        db.session.commit()

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
def logout():
    """Cerrar sesión"""
    logout_user()
    flash('Has cerrado sesión', 'info')
    return redirect(url_for('main.index'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Registro de nuevos usuarios"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = RegistrationForm()

    if form.validate_on_submit():
        if not request.form.get('consentimiento'):
            flash('Debes aceptar la Política de Privacidad para registrarte', 'danger')
            return render_template('auth/register.html', form=form)

        nombre_fiscal = f"{form.nombre.data or ''} {form.apellidos.data or ''}".strip()
        if not nombre_fiscal:
            nombre_fiscal = form.username.data

        cuenta = Cuenta(
            tipo_titular='persona',
            nombre_fiscal=nombre_fiscal,
            email=form.email.data,
            activa=True
        )
        db.session.add(cuenta)
        db.session.flush()

        es_superadmin_inicial = (
            (form.email.data or '').strip().lower() == 'restetelraco@gmail.com'
            or (form.username.data or '').strip().lower() == 'jose'
        )

        user = User(
            username=form.username.data,
            email=form.email.data,
            nombre=form.nombre.data,
            apellidos=form.apellidos.data,
            plan='vitalicia' if es_superadmin_inicial else 'demo',
            rol='admin' if es_superadmin_inicial else 'demo',
            activo=True,
            max_propiedades=9999 if es_superadmin_inicial else 3,
            max_reservas=999999 if es_superadmin_inicial else 50,
            licencia_expiracion=None if es_superadmin_inicial else datetime.utcnow().date() + timedelta(days=15),
            cuenta_id=cuenta.id,
            es_principal=True,
            puede_admin=True if es_superadmin_inicial else False,
            puede_gestionar_usuarios=True,
            puede_gestionar_propiedades=True,
            puede_gestionar_contratos=True,
            puede_gestionar_reservas=True,
            puede_gestionar_finanzas=True,
            puede_gestionar_tareas=True,
            puede_ver_informes=True
        )
        user.set_password(form.password.data)

        db.session.add(user)
        db.session.flush()

        consentimiento = Consentimiento(
            usuario_id=user.id,
            version_politica='1.0',
            ip=request.remote_addr,
            aceptado=True
        )
        db.session.add(consentimiento)

        acceso = Acceso(
            usuario_id=user.id,
            ip=request.remote_addr,
            exito=True,
            mensaje='Registro de usuario'
        )
        db.session.add(acceso)

        db.session.commit()

        if es_superadmin_inicial:
            flash('Registro de administrador completado correctamente.', 'success')
        else:
            flash('¡Registro exitoso! Ya puedes iniciar sesión.', 'success')

        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', form=form)


@auth_bp.route('/perfil/email', methods=['POST'])
@login_required
def guardar_email_cliente():
    puerto = request.form.get('port', type=int) or 587
    settings = {
        'enabled': bool(request.form.get('enabled')),
        'host': (request.form.get('host') or '').strip(),
        'port': puerto,
        'use_tls': bool(request.form.get('use_tls')),
        'use_ssl': bool(request.form.get('use_ssl')),
        'username': (request.form.get('username') or '').strip(),
        'password': request.form.get('password') or '',
        'sender_name': (request.form.get('sender_name') or '').strip(),
        'sender_email': (request.form.get('sender_email') or '').strip(),
    }

    if settings['use_ssl']:
        settings['use_tls'] = False

    save_email_settings_for_user(current_user, settings)
    flash('Configuración de email guardada correctamente.', 'success')
    return redirect(url_for('auth.perfil'))


@auth_bp.route('/perfil/email/prueba', methods=['POST'])
@login_required
def probar_email_cliente():
    destinatario = (request.form.get('test_recipient') or current_user.email or '').strip()
    if not destinatario:
        flash('Indica un email de destino para la prueba.', 'warning')
        return redirect(url_for('auth.perfil'))

    try:
        send_test_email_for_user(current_user, destinatario)
        flash(f'Correo de prueba enviado a {destinatario}.', 'success')
    except Exception as e:
        flash(f'No se pudo enviar la prueba de email: {e}', 'danger')

    return redirect(url_for('auth.perfil'))


@auth_bp.route('/perfil')
@login_required
def perfil():
    asegurar_cuenta_principal(current_user)
    return render_template('auth/perfil.html')


@auth_bp.route('/usuarios')
@login_required
def usuarios():
    asegurar_cuenta_principal(current_user)

    if not puede_gestionar_usuarios_actual():
        flash('No tienes permisos para gestionar usuarios.', 'danger')
        return redirect(url_for('main.dashboard'))

    usuarios = usuarios_cuenta_actual_query().order_by(
        User.es_principal.desc(),
        User.activo.desc(),
        User.nombre.asc(),
        User.username.asc()
    ).all()

    return render_template('auth/usuarios.html', usuarios=usuarios)


@auth_bp.route('/usuarios/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_usuario():
    asegurar_cuenta_principal(current_user)

    if not puede_gestionar_usuarios_actual():
        flash('No tienes permisos para crear usuarios.', 'danger')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        nombre = (request.form.get('nombre') or '').strip()
        apellidos = (request.form.get('apellidos') or '').strip()
        rol = (request.form.get('rol') or 'empleado').strip()

        if not username or not email or not password:
            flash('Usuario, email y contraseña son obligatorios.', 'danger')
            return render_template('auth/usuario_form.html', usuario=None)

        if User.query.filter_by(username=username).first():
            flash('Ese nombre de usuario ya existe.', 'danger')
            return render_template('auth/usuario_form.html', usuario=None)

        if User.query.filter_by(email=email).first():
            flash('Ese email ya está registrado.', 'danger')
            return render_template('auth/usuario_form.html', usuario=None)

        nuevo = User(
            username=username,
            email=email,
            nombre=nombre,
            apellidos=apellidos,
            rol=rol,
            activo=True,
            plan=current_user.plan,
            max_propiedades=current_user.max_propiedades,
            max_reservas=current_user.max_reservas,
            licencia_expiracion=current_user.licencia_expiracion,
            cuenta_id=current_user.cuenta_id,
            es_principal=False,
            puede_gestionar_usuarios=bool(request.form.get('puede_gestionar_usuarios')),
            puede_gestionar_propiedades=bool(request.form.get('puede_gestionar_propiedades')),
            puede_gestionar_contratos=bool(request.form.get('puede_gestionar_contratos')),
            puede_gestionar_reservas=bool(request.form.get('puede_gestionar_reservas')),
            puede_gestionar_finanzas=bool(request.form.get('puede_gestionar_finanzas')),
            puede_gestionar_tareas=bool(request.form.get('puede_gestionar_tareas')),
            puede_ver_informes=bool(request.form.get('puede_ver_informes'))
        )
        nuevo.set_password(password)

        db.session.add(nuevo)
        db.session.commit()

        log_audit(
            current_user.id,
            'crear',
            'usuario',
            nuevo.id,
            None,
            {
                'username': nuevo.username,
                'email': nuevo.email,
                'rol': nuevo.rol,
                'cuenta_id': nuevo.cuenta_id
            }
        )

        flash('Usuario creado correctamente.', 'success')
        return redirect(url_for('auth.usuarios'))

    return render_template('auth/usuario_form.html', usuario=None)


@auth_bp.route('/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_usuario(id):
    asegurar_cuenta_principal(current_user)

    if not puede_gestionar_usuarios_actual():
        flash('No tienes permisos para editar usuarios.', 'danger')
        return redirect(url_for('main.dashboard'))

    usuario = User.query.get_or_404(id)

    if usuario.cuenta_id != current_user.cuenta_id:
        flash('No puedes editar usuarios de otra cuenta.', 'danger')
        return redirect(url_for('auth.usuarios'))

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip().lower()

        if not username or not email:
            flash('Usuario y email son obligatorios.', 'danger')
            return render_template('auth/usuario_form.html', usuario=usuario)

        otro_username = User.query.filter(User.username == username, User.id != usuario.id).first()
        if otro_username:
            flash('Ese nombre de usuario ya está en uso.', 'danger')
            return render_template('auth/usuario_form.html', usuario=usuario)

        otro_email = User.query.filter(User.email == email, User.id != usuario.id).first()
        if otro_email:
            flash('Ese email ya está registrado.', 'danger')
            return render_template('auth/usuario_form.html', usuario=usuario)

        datos_antes = {
            'username': usuario.username,
            'email': usuario.email,
            'rol': usuario.rol,
            'activo': usuario.activo,
            'puede_gestionar_usuarios': usuario.puede_gestionar_usuarios,
            'puede_gestionar_propiedades': usuario.puede_gestionar_propiedades,
            'puede_gestionar_contratos': usuario.puede_gestionar_contratos,
            'puede_gestionar_reservas': usuario.puede_gestionar_reservas,
            'puede_gestionar_finanzas': usuario.puede_gestionar_finanzas,
            'puede_gestionar_tareas': usuario.puede_gestionar_tareas,
            'puede_ver_informes': usuario.puede_ver_informes
        }

        usuario.username = username
        usuario.email = email
        usuario.nombre = (request.form.get('nombre') or '').strip()
        usuario.apellidos = (request.form.get('apellidos') or '').strip()
        usuario.rol = (request.form.get('rol') or usuario.rol).strip()

        nueva_password = request.form.get('password') or ''
        if nueva_password:
            usuario.set_password(nueva_password)

        if not usuario.es_principal:
            usuario.puede_gestionar_usuarios = bool(request.form.get('puede_gestionar_usuarios'))
            usuario.puede_gestionar_propiedades = bool(request.form.get('puede_gestionar_propiedades'))
            usuario.puede_gestionar_contratos = bool(request.form.get('puede_gestionar_contratos'))
            usuario.puede_gestionar_reservas = bool(request.form.get('puede_gestionar_reservas'))
            usuario.puede_gestionar_finanzas = bool(request.form.get('puede_gestionar_finanzas'))
            usuario.puede_gestionar_tareas = bool(request.form.get('puede_gestionar_tareas'))
            usuario.puede_ver_informes = bool(request.form.get('puede_ver_informes'))

        db.session.commit()

        datos_despues = {
            'username': usuario.username,
            'email': usuario.email,
            'rol': usuario.rol,
            'activo': usuario.activo,
            'puede_gestionar_usuarios': usuario.puede_gestionar_usuarios,
            'puede_gestionar_propiedades': usuario.puede_gestionar_propiedades,
            'puede_gestionar_contratos': usuario.puede_gestionar_contratos,
            'puede_gestionar_reservas': usuario.puede_gestionar_reservas,
            'puede_gestionar_finanzas': usuario.puede_gestionar_finanzas,
            'puede_gestionar_tareas': usuario.puede_gestionar_tareas,
            'puede_ver_informes': usuario.puede_ver_informes
        }

        log_audit(current_user.id, 'editar', 'usuario', usuario.id, datos_antes, datos_despues)

        flash('Usuario actualizado correctamente.', 'success')
        return redirect(url_for('auth.usuarios'))

    return render_template('auth/usuario_form.html', usuario=usuario)


@auth_bp.route('/usuarios/toggle/<int:id>', methods=['POST'])
@login_required
def toggle_usuario(id):
    asegurar_cuenta_principal(current_user)

    if not puede_gestionar_usuarios_actual():
        flash('No tienes permisos para cambiar el estado de usuarios.', 'danger')
        return redirect(url_for('main.dashboard'))

    usuario = User.query.get_or_404(id)

    if usuario.cuenta_id != current_user.cuenta_id:
        flash('No puedes modificar usuarios de otra cuenta.', 'danger')
        return redirect(url_for('auth.usuarios'))

    if usuario.id == current_user.id:
        flash('No puedes desactivar tu propio usuario desde aquí.', 'danger')
        return redirect(url_for('auth.usuarios'))

    if usuario.es_principal:
        flash('No se puede desactivar el usuario principal desde esta pantalla.', 'danger')
        return redirect(url_for('auth.usuarios'))

    estado_anterior = usuario.activo
    usuario.activo = not usuario.activo
    db.session.commit()

    log_audit(
        current_user.id,
        'editar',
        'usuario',
        usuario.id,
        {'activo': estado_anterior},
        {'activo': usuario.activo}
    )

    flash('Estado del usuario actualizado correctamente.', 'success')
    return redirect(url_for('auth.usuarios'))


@auth_bp.route('/perfil/exportar')
@login_required
def exportar_datos():
    """Exportar todos los datos del usuario en formato JSON"""
    datos = {
        'usuario': {
            'username': current_user.username,
            'email': current_user.email,
            'nombre': current_user.nombre,
            'apellidos': current_user.apellidos,
            'fecha_registro': str(current_user.fecha_registro),
            'plan': current_user.plan,
            'max_propiedades': current_user.max_propiedades,
            'max_reservas': current_user.max_reservas,
            'licencia_expiracion': str(current_user.licencia_expiracion) if current_user.licencia_expiracion else None,
        },
        'propiedades': []
    }

    for prop in current_user.propiedades.all():
        prop_data = {
            'id': prop.id,
            'nombre': prop.nombre,
            'direccion': prop.direccion,
            'ciudad': prop.ciudad,
            'pais': prop.pais,
            'precio_noche': prop.precio_noche,
            'reservas': []
        }

        for reserva in prop.reservas:
            reserva_data = {
                'id': reserva.id,
                'fecha_entrada': str(reserva.fecha_entrada),
                'fecha_salida': str(reserva.fecha_salida),
                'precio_total': reserva.precio_total,
                'huespedes': []
            }

            for huesped in reserva.huespedes:
                reserva_data['huespedes'].append({
                    'nombre': huesped.nombre,
                    'apellidos': huesped.apellidos,
                    'nacionalidad': huesped.nacionalidad,
                    'numero_documento': huesped.get_numero_documento() if hasattr(huesped, 'get_numero_documento') else None,
                    'telefono': huesped.telefono,
                    'email': huesped.email
                })

            prop_data['reservas'].append(reserva_data)

        datos['propiedades'].append(prop_data)

    log_audit(current_user.id, 'exportar', 'usuario', current_user.id, None, {'tipo': 'todos_datos'})

    json_str = json.dumps(datos, indent=2, default=str, ensure_ascii=False)
    return send_file(
        BytesIO(json_str.encode('utf-8')),
        as_attachment=True,
        download_name=f'datos_{current_user.username}_{datetime.now().strftime("%Y%m%d")}.json',
        mimetype='application/json'
    )


@auth_bp.route('/perfil/eliminar', methods=['POST'])
@login_required
def eliminar_cuenta():
    """Eliminar permanentemente la cuenta del usuario y todos sus datos"""
    log_audit(
        current_user.id,
        'eliminar',
        'usuario',
        current_user.id,
        {'username': current_user.username, 'email': current_user.email},
        None
    )

    db.session.delete(current_user)
    db.session.commit()

    logout_user()
    flash('Tu cuenta y todos tus datos han sido eliminados permanentemente.', 'success')
    return redirect(url_for('main.index'))
