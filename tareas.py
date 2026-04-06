from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, Tarea, Propiedad, Reserva, User
from forms import TareaForm
from datetime import datetime, date
from permisos import (
    usuario_tiene_permiso,
    tareas_visibles_query,
    tarea_es_visible,
    propiedades_visibles_query,
    usuarios_cuenta_actual_query
)

tareas_bp = Blueprint('tareas', __name__, url_prefix='/tareas')


def _puede_ver_tareas():
    return (
        current_user.es_admin()
        or current_user.es_principal
        or current_user.puede_gestionar_tareas
        or Tarea.query.filter_by(asignado_a_id=current_user.id).count() > 0
    )


def _tipos_disponibles():
    filas = (
        tareas_visibles_query()
        .with_entities(Tarea.tipo)
        .distinct()
        .all()
    )
    tipos = []
    for fila in filas:
        tipo = (fila[0] or '').strip()
        if tipo:
            tipos.append(tipo)
    return sorted(tipos)


def _ordenar_tareas_lista(tareas, orden='fecha_asignada', sentido='desc'):
    reverse = sentido == 'desc'

    if orden == 'fecha_limite':
        return sorted(
            tareas,
            key=lambda t: (
                t.fecha_limite is None,
                t.fecha_limite or date.max,
                t.id
            ),
            reverse=reverse
        )

    if orden == 'tipo':
        return sorted(
            tareas,
            key=lambda t: ((t.tipo or '').lower(), t.id),
            reverse=reverse
        )

    if orden == 'propiedad':
        return sorted(
            tareas,
            key=lambda t: ((t.propiedad.nombre if t.propiedad else '').lower(), t.id),
            reverse=reverse
        )

    if orden == 'asignado':
        return sorted(
            tareas,
            key=lambda t: (
                (
                    t.asignado_a.nombre_completo()
                    if getattr(t, 'asignado_a', None) and t.asignado_a.nombre_completo()
                    else (t.asignado_a.username if getattr(t, 'asignado_a', None) else '')
                ).lower(),
                t.id
            ),
            reverse=reverse
        )

    if orden == 'fecha_completada':
        return sorted(
            tareas,
            key=lambda t: (
                t.fecha_completada is None,
                t.fecha_completada or datetime.max,
                t.id
            ),
            reverse=reverse
        )

    return sorted(
        tareas,
        key=lambda t: (
            t.fecha_asignada is None,
            t.fecha_asignada or date.max,
            t.id
        ),
        reverse=reverse
    )


def _aplicar_filtros(query, estado='activas'):
    propiedad_id = request.args.get('propiedad_id', type=int)
    tipo = (request.args.get('tipo') or '').strip()
    asignado_a_id = request.args.get('asignado_a_id', type=int)

    if estado == 'activas':
        query = query.filter(Tarea.completada.is_(False))
    elif estado == 'completadas':
        query = query.filter(Tarea.completada.is_(True))

    if propiedad_id:
        query = query.filter(Tarea.propiedad_id == propiedad_id)

    if tipo:
        query = query.filter(Tarea.tipo == tipo)

    if asignado_a_id:
        query = query.filter(Tarea.asignado_a_id == asignado_a_id)

    return query


def _contexto_listado(tareas, es_historial=False):
    tareas_visibles = tareas_visibles_query().all()
    total_activas = sum(1 for t in tareas_visibles if not t.completada)
    total_completadas = sum(1 for t in tareas_visibles if t.completada)
    total_vencidas = sum(
        1 for t in tareas_visibles
        if not t.completada and t.fecha_limite and t.fecha_limite < date.today()
    )
    total_sin_asignar = sum(
        1 for t in tareas_visibles
        if not t.completada and not t.asignado_a_id
    )

    propiedades = propiedades_visibles_query().order_by(Propiedad.nombre.asc()).all()
    usuarios = (
        usuarios_cuenta_actual_query()
        .filter_by(activo=True)
        .order_by(User.nombre.asc(), User.username.asc())
        .all()
    )

    orden = request.args.get('orden', 'fecha_asignada')
    sentido = request.args.get('sentido', 'desc')
    tareas = _ordenar_tareas_lista(tareas, orden=orden, sentido=sentido)

    return {
        'tareas': tareas,
        'propiedades': propiedades,
        'usuarios': usuarios,
        'tipos_disponibles': _tipos_disponibles(),
        'total_activas': total_activas,
        'total_completadas': total_completadas,
        'total_vencidas': total_vencidas,
        'total_sin_asignar': total_sin_asignar,
        'es_historial': es_historial,
        'filtro_estado': request.args.get('estado', 'activas' if not es_historial else 'completadas'),
        'filtro_propiedad_id': request.args.get('propiedad_id', type=int),
        'filtro_tipo': (request.args.get('tipo') or '').strip(),
        'filtro_asignado_a_id': request.args.get('asignado_a_id', type=int),
        'orden_actual': orden,
        'sentido_actual': sentido,
        'hoy': date.today(),
    }


@tareas_bp.route('/')
@login_required
def index():
    if not _puede_ver_tareas():
        flash('No tienes acceso a tareas.', 'danger')
        return redirect(url_for('main.dashboard'))

    query = tareas_visibles_query()
    query = _aplicar_filtros(query, estado='activas')
    tareas = query.all()

    return render_template(
        'tareas/index.html',
        **_contexto_listado(tareas, es_historial=False)
    )


@tareas_bp.route('/historial')
@login_required
def historial():
    if not _puede_ver_tareas():
        flash('No tienes acceso al historial de tareas.', 'danger')
        return redirect(url_for('main.dashboard'))

    query = tareas_visibles_query()
    query = _aplicar_filtros(query, estado='completadas')
    tareas = query.all()

    return render_template(
        'tareas/index.html',
        **_contexto_listado(tareas, es_historial=True)
    )


@tareas_bp.route('/nueva', methods=['GET', 'POST'])
@login_required
def nueva():
    if not usuario_tiene_permiso('puede_gestionar_tareas'):
        flash('No tienes permisos para crear tareas.', 'danger')
        return redirect(url_for('tareas.index'))

    form = TareaForm()

    propiedades = propiedades_visibles_query().order_by(Propiedad.nombre.asc()).all()
    form.propiedad_id.choices = [(p.id, p.nombre) for p in propiedades]

    propiedades_ids = [p.id for p in propiedades]

    if propiedades_ids:
        reservas = Reserva.query.filter(
            Reserva.propiedad_id.in_(propiedades_ids),
            Reserva.fecha_salida >= datetime.today().date()
        ).all()
    else:
        reservas = []

    choices_reservas = [(0, 'Ninguna')]
    for r in reservas:
        primer_huesped = r.huespedes.first()
        if primer_huesped:
            nombre = f"{primer_huesped.nombre} {primer_huesped.apellidos}"
        else:
            nombre = "Huésped no registrado"

        choices_reservas.append(
            (r.id, f"{nombre} ({r.fecha_entrada} a {r.fecha_salida})")
        )

    form.reserva_id.choices = choices_reservas

    usuarios = usuarios_cuenta_actual_query().filter_by(activo=True).order_by(User.nombre.asc(), User.username.asc()).all()
    form.asignado_a_id.choices = [(0, 'Sin asignar')] + [(u.id, u.nombre_completo() or u.username) for u in usuarios]

    if form.validate_on_submit():
        tarea = Tarea(
            propiedad_id=form.propiedad_id.data,
            reserva_id=form.reserva_id.data if form.reserva_id.data != 0 else None,
            tipo=form.tipo.data,
            descripcion=form.descripcion.data,
            fecha_asignada=form.fecha_asignada.data,
            fecha_limite=form.fecha_limite.data,
            asignado_a_id=form.asignado_a_id.data if form.asignado_a_id.data != 0 else None,
            notas=form.notas.data,
            completada=form.completada.data,
            fecha_completada=datetime.utcnow() if form.completada.data else None
        )
        db.session.add(tarea)
        db.session.commit()
        flash('Tarea creada correctamente', 'success')
        return redirect(url_for('tareas.index'))

    return render_template('tareas/nueva.html', form=form)


@tareas_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    tarea = Tarea.query.get_or_404(id)

    if not tarea_es_visible(tarea) or not usuario_tiene_permiso('puede_gestionar_tareas'):
        flash('No tienes permiso para editar esta tarea', 'danger')
        return redirect(url_for('tareas.index'))

    form = TareaForm(obj=tarea)

    propiedades = propiedades_visibles_query().order_by(Propiedad.nombre.asc()).all()
    form.propiedad_id.choices = [(p.id, p.nombre) for p in propiedades]

    propiedades_ids = [p.id for p in propiedades]
    reservas = Reserva.query.filter(Reserva.propiedad_id.in_(propiedades_ids)).all() if propiedades_ids else []

    choices_reservas = [(0, 'Ninguna')]
    for r in reservas:
        primer_huesped = r.huespedes.first()
        if primer_huesped:
            nombre = f"{primer_huesped.nombre} {primer_huesped.apellidos}"
        else:
            nombre = "Huésped no registrado"

        choices_reservas.append(
            (r.id, f"{nombre} ({r.fecha_entrada} a {r.fecha_salida})")
        )

    form.reserva_id.choices = choices_reservas

    usuarios = usuarios_cuenta_actual_query().filter_by(activo=True).order_by(User.nombre.asc(), User.username.asc()).all()
    form.asignado_a_id.choices = [(0, 'Sin asignar')] + [(u.id, u.nombre_completo() or u.username) for u in usuarios]

    if form.validate_on_submit():
        estaba_completada = tarea.completada

        form.populate_obj(tarea)

        if form.reserva_id.data == 0:
            tarea.reserva_id = None
        if form.asignado_a_id.data == 0:
            tarea.asignado_a_id = None

        if tarea.completada and not estaba_completada:
            tarea.fecha_completada = datetime.utcnow()
        elif not tarea.completada:
            tarea.fecha_completada = None

        db.session.commit()
        flash('Tarea actualizada', 'success')
        return redirect(url_for('tareas.index' if not tarea.completada else 'tareas.historial'))

    return render_template('tareas/editar.html', form=form, tarea=tarea)


@tareas_bp.route('/completar/<int:id>', methods=['POST'])
@login_required
def completar(id):
    tarea = Tarea.query.get_or_404(id)

    if not tarea_es_visible(tarea):
        flash('No tienes permiso', 'danger')
        return redirect(url_for('tareas.index'))

    tarea.completada = True
    tarea.fecha_completada = datetime.utcnow()
    db.session.commit()
    flash('Tarea marcada como completada', 'success')
    return redirect(url_for('tareas.index'))


@tareas_bp.route('/reabrir/<int:id>', methods=['POST'])
@login_required
def reabrir(id):
    tarea = Tarea.query.get_or_404(id)

    if not tarea_es_visible(tarea):
        flash('No tienes permiso para reabrir esta tarea', 'danger')
        return redirect(url_for('tareas.historial'))

    tarea.completada = False
    tarea.fecha_completada = None
    db.session.commit()
    flash('Tarea reabierta correctamente', 'success')
    return redirect(url_for('tareas.historial'))


@tareas_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    tarea = Tarea.query.get_or_404(id)

    if not tarea_es_visible(tarea) or not usuario_tiene_permiso('puede_gestionar_tareas'):
        flash('No tienes permiso para eliminar esta tarea', 'danger')
        return redirect(url_for('tareas.index'))

    db.session.delete(tarea)
    db.session.commit()
    flash('Tarea eliminada correctamente', 'success')
    return redirect(url_for('tareas.index'))