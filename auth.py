from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_user, logout_user, current_user, login_required
from urllib.parse import urlparse as url_parse
from models import db, User, Consentimiento, Acceso
from forms import LoginForm, RegistrationForm
from utils import log_audit
from datetime import datetime
from io import BytesIO
import json

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


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
        else:
            login_user(user, remember=form.remember_me.data)
            exito = True
            mensaje = 'Login correcto'
            next_page = request.args.get('next')
            if not next_page or url_parse(next_page).netloc != '':
                next_page = url_for('main.dashboard')
            flash('Has iniciado sesión correctamente', 'success')
            
            # Registrar acceso exitoso
            acceso = Acceso(
                usuario_id=user.id,
                ip=request.remote_addr,
                exito=True,
                mensaje=mensaje
            )
            db.session.add(acceso)
            db.session.commit()
            
            return redirect(next_page)
    
    # Registrar intento fallido si no hubo éxito
    if not exito and form.validate_on_submit():
        acceso = Acceso(
            usuario_id=user.id if user else None,
            ip=request.remote_addr,
            exito=False,
            mensaje=mensaje or 'Login fallido'
        )
        db.session.add(acceso)
        db.session.commit()
    
    return render_template('login.html', form=form)


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
        # Verificar consentimiento
        if not request.form.get('consentimiento'):
            flash('Debes aceptar la Política de Privacidad para registrarte', 'danger')
            return render_template('register.html', form=form)
        
        user = User(
            username=form.username.data,
            email=form.email.data,
            nombre=form.nombre.data,
            apellidos=form.apellidos.data
        )
        user.set_password(form.password.data)
        
        db.session.add(user)
        db.session.flush()
        
        # Registrar consentimiento
        consentimiento = Consentimiento(
            usuario_id=user.id,
            version_politica='1.0',
            ip=request.remote_addr,
            aceptado=True
        )
        db.session.add(consentimiento)
        
        # Registrar acceso de registro
        acceso = Acceso(
            usuario_id=user.id,
            ip=request.remote_addr,
            exito=True,
            mensaje='Registro de usuario'
        )
        db.session.add(acceso)
        
        db.session.commit()
        
        flash('¡Registro exitoso! Ya puedes iniciar sesión.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('register.html', form=form)


@auth_bp.route('/perfil')
@login_required
def perfil():
    """Página de perfil de usuario"""
    return render_template('auth/perfil.html')


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
            'fecha_registro': str(current_user.fecha_registro)
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
    
    # LOG: Exportación de datos
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
    # LOG: Eliminación de cuenta
    log_audit(current_user.id, 'eliminar', 'usuario', current_user.id, 
              {'username': current_user.username, 'email': current_user.email}, None)
    
    db.session.delete(current_user)
    db.session.commit()
    
    logout_user()
    flash('Tu cuenta y todos tus datos han sido eliminados permanentemente.', 'success')
    return redirect(url_for('main.index'))