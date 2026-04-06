from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from datetime import datetime, timedelta

from models import db, User
from utils import log_audit
from licencias_utils import PLAN_PRESETS, aplicar_preset_licencia, normalizar_plan, plan_label

licencias_bp = Blueprint('licencias', __name__, url_prefix='/licencias')

PLAN_OPTIONS = [
    ('demo', 'Demo'),
    ('trial', 'Trial'),
    ('activa', 'Activa'),
    ('vitalicia', 'Vitalicia'),
]


def _solo_admin():
    if not current_user.is_authenticated:
        abort(403)
    if not current_user.es_admin():
        abort(403)


def _parse_fecha(valor):
    if not valor:
        return None
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except ValueError:
        return None


def _serializar_usuario(usuario):
    return {
        'plan': usuario.plan,
        'rol': usuario.rol,
        'max_propiedades': usuario.max_propiedades,
        'max_reservas': usuario.max_reservas,
        'licencia_expiracion': str(usuario.licencia_expiracion) if usuario.licencia_expiracion else None,
        'activo': usuario.activo,
        'puede_admin': usuario.puede_admin,
    }


def _aplicar_plan(usuario, plan):
    return aplicar_preset_licencia(usuario, plan)


@licencias_bp.route('/')
@login_required
def index():
    _solo_admin()

    q = (request.args.get('q') or '').strip()
    plan = normalizar_plan(request.args.get('plan')) if request.args.get('plan') else ''
    estado = (request.args.get('estado') or '').strip()

    query = User.query

    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                User.username.ilike(like),
                User.email.ilike(like),
                User.nombre.ilike(like),
                User.apellidos.ilike(like)
            )
        )

    if plan:
        if plan == 'activa':
            query = query.filter(User.plan.in_(['activa', 'pro', 'premium']))
        elif plan == 'demo':
            query = query.filter(User.plan.in_(['demo', 'gratis']))
        else:
            query = query.filter(User.plan == plan)

    if estado == 'activos':
        query = query.filter(User.activo.is_(True))
    elif estado == 'inactivos':
        query = query.filter(User.activo.is_(False))

    usuarios = query.order_by(User.fecha_registro.desc(), User.id.desc()).all()
    hoy = datetime.utcnow().date()

    return render_template(
        'licencias/index.html',
        usuarios=usuarios,
        q=q,
        plan=plan,
        estado=estado,
        hoy=hoy,
        plan_options=PLAN_OPTIONS,
        plan_label=plan_label,
    )


@licencias_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    _solo_admin()

    usuario = User.query.get_or_404(id)

    if request.method == 'POST':
        datos_antes = _serializar_usuario(usuario)

        usuario.plan = normalizar_plan(request.form.get('plan') or 'demo')
        usuario.rol = (request.form.get('rol') or 'demo').strip()

        try:
            usuario.max_propiedades = int(request.form.get('max_propiedades') or 0)
        except ValueError:
            usuario.max_propiedades = 0

        try:
            usuario.max_reservas = int(request.form.get('max_reservas') or 0)
        except ValueError:
            usuario.max_reservas = 0

        usuario.licencia_expiracion = _parse_fecha(request.form.get('licencia_expiracion'))
        usuario.activo = request.form.get('activo') == '1'
        usuario.puede_admin = request.form.get('puede_admin') == '1'

        if usuario.plan == 'vitalicia':
            usuario.licencia_expiracion = None
        elif usuario.plan in {'demo', 'trial', 'activa'} and not usuario.licencia_expiracion:
            preset = PLAN_PRESETS.get(usuario.plan, PLAN_PRESETS['demo'])
            if preset['duracion_dias']:
                usuario.licencia_expiracion = datetime.utcnow().date() + timedelta(days=preset['duracion_dias'])

        db.session.commit()

        datos_despues = _serializar_usuario(usuario)
        log_audit(current_user.id, 'editar', 'licencia', usuario.id, datos_antes, datos_despues)

        flash('Licencia actualizada correctamente.', 'success')
        return redirect(url_for('licencias.index'))

    return render_template('licencias/editar.html', usuario=usuario, plan_options=PLAN_OPTIONS)


@licencias_bp.route('/<int:id>/aplicar/<plan>', methods=['POST'])
@login_required
def aplicar_plan(id, plan):
    _solo_admin()

    usuario = User.query.get_or_404(id)
    plan = normalizar_plan(plan)
    if plan not in PLAN_PRESETS:
        flash('Plan de licencia no válido.', 'danger')
        return redirect(url_for('licencias.index'))

    datos_antes = _serializar_usuario(usuario)
    _aplicar_plan(usuario, plan)
    db.session.commit()

    datos_despues = _serializar_usuario(usuario)
    log_audit(current_user.id, 'editar', 'licencia', usuario.id, datos_antes, datos_despues)

    flash(f'Usuario convertido a licencia {plan_label(plan).lower()}.', 'success')
    return redirect(url_for('licencias.index'))


@licencias_bp.route('/<int:id>/demo', methods=['POST'])
@login_required
def convertir_demo(id):
    return aplicar_plan(id, 'demo')


@licencias_bp.route('/<int:id>/trial', methods=['POST'])
@login_required
def convertir_trial(id):
    return aplicar_plan(id, 'trial')


@licencias_bp.route('/<int:id>/pro', methods=['POST'])
@login_required
def convertir_pro(id):
    return aplicar_plan(id, 'activa')


@licencias_bp.route('/<int:id>/vitalicia', methods=['POST'])
@login_required
def convertir_vitalicia(id):
    return aplicar_plan(id, 'vitalicia')


@licencias_bp.route('/<int:id>/renovar', methods=['POST'])
@login_required
def renovar(id):
    _solo_admin()

    usuario = User.query.get_or_404(id)

    if normalizar_plan(usuario.plan) == 'vitalicia':
        flash('La licencia vitalicia no necesita renovación.', 'info')
        return redirect(url_for('licencias.index'))

    dias = request.form.get('dias', type=int) or 30
    if dias not in (15, 30, 90, 180, 365):
        dias = 30

    hoy = datetime.utcnow().date()
    base = usuario.licencia_expiracion if usuario.licencia_expiracion and usuario.licencia_expiracion > hoy else hoy
    nueva_fecha = base + timedelta(days=dias)

    datos_antes = {
        'licencia_expiracion': str(usuario.licencia_expiracion) if usuario.licencia_expiracion else None,
        'activo': usuario.activo,
    }

    usuario.licencia_expiracion = nueva_fecha
    usuario.activo = True
    if normalizar_plan(usuario.plan) == 'demo' and dias > 15:
        usuario.plan = 'trial'
        if not usuario.puede_admin:
            usuario.rol = 'cliente'
        usuario.max_propiedades = max(usuario.max_propiedades or 0, PLAN_PRESETS['trial']['max_propiedades'])
        usuario.max_reservas = max(usuario.max_reservas or 0, PLAN_PRESETS['trial']['max_reservas'])
    db.session.commit()

    datos_despues = {
        'licencia_expiracion': str(usuario.licencia_expiracion),
        'activo': usuario.activo,
        'plan': usuario.plan,
    }

    log_audit(current_user.id, 'editar', 'licencia', usuario.id, datos_antes, datos_despues)

    flash(f'Licencia renovada {dias} días.', 'success')
    return redirect(url_for('licencias.index'))
