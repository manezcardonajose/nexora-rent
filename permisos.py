from flask_login import current_user
from sqlalchemy import or_

from models import Propiedad, Tarea, User


def usuario_tiene_permiso(nombre_permiso):
    if not getattr(current_user, 'is_authenticated', False):
        return False

    if current_user.es_admin() or current_user.es_principal:
        return True

    return bool(getattr(current_user, nombre_permiso, False))


def ids_usuarios_cuenta_actual():
    if not getattr(current_user, 'is_authenticated', False):
        return []

    if current_user.cuenta_id:
        usuarios = User.query.filter_by(cuenta_id=current_user.cuenta_id).all()
        return [u.id for u in usuarios]

    return [current_user.id]


def usuarios_cuenta_actual_query():
    if not getattr(current_user, 'is_authenticated', False):
        return User.query.filter(User.id == 0)

    if current_user.cuenta_id:
        return User.query.filter_by(cuenta_id=current_user.cuenta_id)

    return User.query.filter_by(id=current_user.id)


def propiedades_visibles_query():
    if not getattr(current_user, 'is_authenticated', False):
        return Propiedad.query.filter(Propiedad.id == 0)

    ids_usuarios = ids_usuarios_cuenta_actual()

    if current_user.cuenta_id:
        return Propiedad.query.filter(
            or_(
                Propiedad.cuenta_id == current_user.cuenta_id,
                Propiedad.usuario_id.in_(ids_usuarios)
            )
        )

    return Propiedad.query.filter_by(usuario_id=current_user.id)


def propiedad_es_visible(propiedad):
    if not getattr(current_user, 'is_authenticated', False):
        return False

    if current_user.es_admin() or current_user.es_principal:
        return True

    if current_user.cuenta_id and propiedad.cuenta_id == current_user.cuenta_id:
        return True

    if propiedad.usuario_id in ids_usuarios_cuenta_actual():
        return True

    return False


def propiedad_es_editable(propiedad):
    if not propiedad_es_visible(propiedad):
        return False

    return usuario_tiene_permiso('puede_gestionar_propiedades')


def tareas_visibles_query():
    if not getattr(current_user, 'is_authenticated', False):
        return Tarea.query.filter(Tarea.id == 0)

    ids_propiedades = [p.id for p in propiedades_visibles_query().all()]

    if current_user.es_admin() or current_user.es_principal or current_user.puede_gestionar_tareas:
        if ids_propiedades:
            return Tarea.query.filter(
                or_(
                    Tarea.asignado_a_id == current_user.id,
                    Tarea.propiedad_id.in_(ids_propiedades)
                )
            )
        return Tarea.query.filter(Tarea.asignado_a_id == current_user.id)

    return Tarea.query.filter(Tarea.asignado_a_id == current_user.id)


def tarea_es_visible(tarea):
    if not getattr(current_user, 'is_authenticated', False):
        return False

    if current_user.es_admin() or current_user.es_principal:
        return True

    if tarea.asignado_a_id == current_user.id:
        return True

    if current_user.puede_gestionar_tareas and tarea.propiedad_id:
        ids_propiedades = [p.id for p in propiedades_visibles_query().all()]
        return tarea.propiedad_id in ids_propiedades

    return False