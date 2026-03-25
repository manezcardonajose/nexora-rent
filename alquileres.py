from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, Inquilino, Contrato, Propiedad
from datetime import datetime

alquileres_bp = Blueprint('alquileres', __name__, url_prefix='/alquileres')

# ============================================
# LISTADO CONTRATOS
# ============================================
@alquileres_bp.route('/')
def index():
    contratos = Contrato.query.all()
    return render_template('alquileres/index.html', contratos=contratos)

# ============================================
# NUEVO INQUILINO
# ============================================
@alquileres_bp.route('/inquilino/nuevo', methods=['GET', 'POST'])
def nuevo_inquilino():
    if request.method == 'POST':
        inquilino = Inquilino(
            nombre=request.form.get('nombre'),
            apellidos=request.form.get('apellidos'),
            dni=request.form.get('dni'),
            telefono=request.form.get('telefono'),
            email=request.form.get('email')
        )

        db.session.add(inquilino)
        db.session.commit()

        flash('Inquilino creado correctamente')
        return redirect(url_for('alquileres.index'))

    return render_template('alquileres/nuevo_inquilino.html')

# ============================================
# NUEVO CONTRATO
# ============================================
@alquileres_bp.route('/contrato/nuevo', methods=['GET', 'POST'])
def nuevo_contrato():
    propiedades = Propiedad.query.all()
    inquilinos = Inquilino.query.all()

    if request.method == 'POST':
        contrato = Contrato(
            propiedad_id=request.form.get('propiedad_id'),
            inquilino_id=request.form.get('inquilino_id'),
            fecha_inicio=datetime.strptime(request.form.get('fecha_inicio'), '%Y-%m-%d'),
            fecha_fin=datetime.strptime(request.form.get('fecha_fin'), '%Y-%m-%d') if request.form.get('fecha_fin') else None,
            renta_mensual=float(request.form.get('renta_mensual')),
            fianza=float(request.form.get('fianza') or 0)
        )

        db.session.add(contrato)
        db.session.commit()

        flash('Contrato creado correctamente')
        return redirect(url_for('alquileres.index'))

    return render_template('alquileres/nuevo_contrato.html', propiedades=propiedades, inquilinos=inquilinos)
