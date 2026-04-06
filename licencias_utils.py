from datetime import datetime

SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}

PLAN_PRESETS = {
    'demo': {
        'plan': 'demo',
        'rol': 'demo',
        'max_propiedades': 3,
        'max_reservas': 50,
        'duracion_dias': 15,
        'requiere_expiracion': True,
    },
    'trial': {
        'plan': 'trial',
        'rol': 'cliente',
        'max_propiedades': 999,
        'max_reservas': 9999,
        'duracion_dias': 30,
        'requiere_expiracion': True,
    },
    'activa': {
        'plan': 'activa',
        'rol': 'cliente',
        'max_propiedades': 999,
        'max_reservas': 9999,
        'duracion_dias': 365,
        'requiere_expiracion': True,
    },
    'vitalicia': {
        'plan': 'vitalicia',
        'rol': 'cliente',
        'max_propiedades': 999,
        'max_reservas': 9999,
        'duracion_dias': None,
        'requiere_expiracion': False,
    },
}

LEGACY_PLAN_MAP = {
    'gratis': 'demo',
    'pro': 'activa',
    'premium': 'activa',
}


def normalizar_plan(plan):
    valor = (plan or '').strip().lower()
    return LEGACY_PLAN_MAP.get(valor, valor or 'demo')


def plan_label(plan):
    labels = {
        'demo': 'Demo',
        'trial': 'Trial',
        'activa': 'Activa',
        'vitalicia': 'Vitalicia',
        'pro': 'Activa',
        'premium': 'Activa',
        'gratis': 'Demo',
    }
    return labels.get((plan or '').strip().lower(), (plan or 'Demo').title())


def licencia_vigente(user):
    if not user:
        return False
    if getattr(user, 'es_admin', lambda: False)():
        return True
    if not user.activo:
        return False
    if user.licencia_expiracion and user.licencia_expiracion < datetime.utcnow().date():
        return False
    return True


def licencia_en_modo_restringido(user):
    if not user or getattr(user, 'es_admin', lambda: False)():
        return False
    if not user.activo:
        return False
    return bool(user.licencia_expiracion and user.licencia_expiracion < datetime.utcnow().date())


def puede_acceder_sistema(user):
    if not user:
        return False
    if getattr(user, 'es_admin', lambda: False)():
        return True
    return user.activo


def aplicar_preset_licencia(user, plan):
    plan_normalizado = normalizar_plan(plan)
    preset = PLAN_PRESETS.get(plan_normalizado, PLAN_PRESETS['demo'])

    user.plan = preset['plan']
    if not getattr(user, 'puede_admin', False):
        user.rol = preset['rol']
    user.max_propiedades = preset['max_propiedades']
    user.max_reservas = preset['max_reservas']
    user.activo = True

    if preset['requiere_expiracion']:
        user.licencia_expiracion = datetime.utcnow().date()
        if preset['duracion_dias']:
            from datetime import timedelta
            user.licencia_expiracion = datetime.utcnow().date() + timedelta(days=preset['duracion_dias'])
    else:
        user.licencia_expiracion = None

    return preset


def puede_usar_modulo(user, modulo):
    if user.es_admin():
        return True

    if not user.activo:
        return False

    if licencia_en_modo_restringido(user):
        return modulo != 'simulador'

    plan = normalizar_plan(getattr(user, 'plan', 'demo'))

    permisos = {
        'vacacional': True,
        'larga_duracion': True,
        'informes': getattr(user, 'puede_ver_informes', True),
        'contratos': True,
        'simulador': plan in {'demo', 'trial'},
    }

    return permisos.get(modulo, False)


def puede_crear_propiedad(user):
    if user.es_admin():
        return True
    if not licencia_vigente(user):
        return False
    return user.propiedades.count() < (user.max_propiedades or 0)


def total_reservas_usuario(user):
    total = 0
    for prop in user.propiedades.all():
        total += prop.reservas.count()
    return total


def puede_crear_reserva(user):
    if user.es_admin():
        return True
    if not licencia_vigente(user):
        return False
    return total_reservas_usuario(user) < (user.max_reservas or 0)
