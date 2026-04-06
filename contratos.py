from flask import Blueprint, render_template, abort, request, redirect, url_for, flash
from flask_login import login_required, current_user
from jinja2 import Template

from models import (
    db,
    Contrato,
    RepresentanteCuenta,
    PlantillaClausula,
    ContratoClausula,
    ContratoInterviniente,
    ContratoFoto,
    ContratoAnexo,
    Habitacion,
)
from licencias_utils import puede_usar_modulo
from permisos import propiedad_es_visible, usuario_tiene_permiso

contratos_bp = Blueprint("contratos", __name__, url_prefix="/contratos")


# =========================================================
# TEXTOS BASE PROFESIONALES
# =========================================================

def texto_base_devolucion_fianza():
    return (
        "La fianza será devuelta dentro del plazo pactado entre las partes, y en su defecto dentro "
        "de un plazo razonable desde la entrega efectiva de llaves, una vez comprobado el estado "
        "del inmueble, mobiliario, enseres e instalaciones, así como la inexistencia de daños, "
        "desperfectos, consumos pendientes, suministros impagados o cantidades adeudadas por la parte "
        "arrendataria. En caso de existir importes pendientes o daños imputables a la parte arrendataria, "
        "la parte arrendadora podrá descontarlos de la fianza, previa justificación."
    )


def texto_base_devolucion_adelantados():
    return (
        "Las cantidades entregadas por adelantado, distintas de la fianza, se imputarán al pago de las "
        "mensualidades o conceptos pactados. En caso de extinción anticipada del contrato, su devolución, "
        "compensación o pérdida dependerá del cumplimiento de las obligaciones contractuales, de la causa "
        "de resolución y de los importes pendientes que, en su caso, existan a cargo de la parte arrendataria."
    )


# =========================================================
# PLANTILLAS BASE
# =========================================================

def sembrar_plantillas_clausulas():
    base = [
        {
            "codigo": "objeto",
            "titulo": "Objeto del contrato",
            "contenido": """
Es objeto del presente contrato el arrendamiento de la vivienda identificada en este documento, incluyendo, en su caso, los muebles, enseres y anejos que formen parte del inmueble arrendado.

Datos del inmueble:
- Vivienda: {{ propiedad.nombre or 'No indicada' }}
- Dirección: {{ propiedad.direccion_completa() or 'No indicada' }}
- Referencia catastral: {{ propiedad.referencia_catastral or 'No informada' }}
- Municipio: {{ propiedad.municipio or propiedad.ciudad or 'No indicado' }}
- Tipo de inmueble: {{ propiedad.tipo_inmueble or 'No indicado' }}
- Nº de habitaciones: {{ propiedad.num_habitaciones or 'No indicado' }}
""",
            "orden_defecto": 1,
        },
        {
            "codigo": "especificaciones_basicas",
            "titulo": "Especificaciones básicas del contrato",
            "contenido": """
1) Fecha de inicio: {{ contrato.fecha_inicio.strftime('%d/%m/%Y') if contrato.fecha_inicio else 'No indicada' }}
2) Fecha de finalización: {{ contrato.fecha_fin.strftime('%d/%m/%Y') if contrato.fecha_fin else 'No indicada' }}
3) Renta mensual: {{ '%.2f'|format(contrato.renta_mensual or 0) }} €
4) Fianza: {{ '%.2f'|format(contrato.fianza or 0) }} €
5) Meses adelantados: {{ contrato.meses_adelantados or 0 }}
6) Importe entregado por adelantado: {{ '%.2f'|format(contrato.importe_meses_adelantados or 0) }} €
7) Gastos individuales: {{ propiedad.gastos_individuales_texto or 'No especificados' }}
8) Suministros incluidos: {{ propiedad.suministros_incluidos_texto or 'No especificados' }}
9) Información de administración / autorizada: {{ propiedad.contacto_administracion_texto or 'No especificada' }}
""",
            "orden_defecto": 2,
        },
        {
            "codigo": "destino",
            "titulo": "Destino",
            "contenido": """
La vivienda arrendada se destinará exclusivamente a vivienda habitual de la parte arrendataria, quedando prohibido darle uso distinto sin autorización expresa y escrita de la parte arrendadora.
""",
            "orden_defecto": 3,
        },
        {
            "codigo": "duracion",
            "titulo": "Duración del contrato",
            "contenido": """
El presente contrato tendrá la duración pactada entre las partes, comenzando el {{ contrato.fecha_inicio.strftime('%d/%m/%Y') if contrato.fecha_inicio else 'No indicada' }} y finalizando el {{ contrato.fecha_fin.strftime('%d/%m/%Y') if contrato.fecha_fin else 'No indicada' }}.
""",
            "orden_defecto": 4,
        },
        {
            "codigo": "pago_renta",
            "titulo": "Pago de la renta",
            "contenido": """
La renta mensual pactada asciende a {{ '%.2f'|format(contrato.renta_mensual or 0) }} € y deberá abonarse mensualmente por adelantado.

El pago se realizará mediante transferencia bancaria a:
- IBAN: {{ propiedad.iban_cobro or 'NO INFORMADO' }}
- Entidad bancaria: {{ propiedad.entidad_bancaria or 'NO INFORMADA' }}
- Concepto de transferencia: {{ propiedad.concepto_transferencia or 'NO INFORMADO' }}
""",
            "orden_defecto": 5,
        },
        {
            "codigo": "fianza",
            "titulo": "Fianza y cantidades adelantadas",
            "contenido": """
La parte arrendataria entrega la cantidad de {{ '%.2f'|format(contrato.fianza or 0) }} € en concepto de fianza.

Además, entrega por adelantado:
- Nº de meses adelantados: {{ contrato.meses_adelantados or 0 }}
- Importe total adelantado: {{ '%.2f'|format(contrato.importe_meses_adelantados or 0) }} €

Condiciones de devolución de la fianza:
{{ contrato.devolucion_fianza_texto or 'Se estará a lo pactado y a la normativa aplicable.' }}

Condiciones de devolución o compensación de cantidades adelantadas:
{{ contrato.devolucion_adelantado_texto or 'Se estará a lo pactado y a la normativa aplicable.' }}
""",
            "orden_defecto": 6,
        },
        {
            "codigo": "gastos_individuales",
            "titulo": "Gastos individuales y suministros",
            "contenido": """
Gastos individuales:
{{ propiedad.gastos_individuales_texto or 'No especificados' }}

Suministros incluidos:
{{ propiedad.suministros_incluidos_texto or 'No especificados' }}
""",
            "orden_defecto": 7,
        },
        {
            "codigo": "prohibiciones",
            "titulo": "Prohibiciones",
            "contenido": """
Queda prohibido subarrendar, ceder total o parcialmente la vivienda, realizar obras sin autorización, cambiar cerraduras sin consentimiento expreso, así como desarrollar actividades molestas, insalubres, peligrosas o ilícitas.
""",
            "orden_defecto": 8,
        },
        {
            "codigo": "conservacion",
            "titulo": "Conservación de la vivienda",
            "contenido": """
La parte arrendataria se obliga a conservar la vivienda en buen estado y devolverla al término del contrato en condiciones adecuadas de uso, limpieza y conservación, respondiendo de los daños o desperfectos causados por mal uso o negligencia.
""",
            "orden_defecto": 9,
        },
        {
            "codigo": "resolucion",
            "titulo": "Causas de resolución contractual",
            "contenido": """
Además de las causas previstas en el artículo 27 de la LAU, el contrato podrá resolverse por incumplimiento de cualquiera de las obligaciones esenciales pactadas.
""",
            "orden_defecto": 10,
        },
        {
            "codigo": "comunicaciones",
            "titulo": "Comunicaciones y mediación previa",
            "contenido": """
Las comunicaciones entre las partes podrán realizarse por teléfono, correo electrónico, WhatsApp o cualquier otro medio facilitado en el contrato.

Antes de acudir a la vía judicial, las partes intentarán resolver amistosamente cualquier discrepancia y, en su caso, acudir a mediación o conciliación previa.
""",
            "orden_defecto": 11,
        },
        {
            "codigo": "jurisdiccion",
            "titulo": "Jurisdicción",
            "contenido": """
Para cualquier cuestión relativa a la interpretación, cumplimiento o ejecución del presente contrato, las partes se someten a los juzgados y tribunales del lugar donde radica el inmueble, salvo norma imperativa en contrario.
""",
            "orden_defecto": 12,
        },
        {
            "codigo": "avalista",
            "titulo": "Avalista solidario",
            "contenido": """
La persona avalista o fiadora solidaria que firme este contrato se obliga al cumplimiento y pago de todas las obligaciones asumidas por la parte arrendataria.
""",
            "orden_defecto": 13,
        },
    ]

    for item in base:
        existe = PlantillaClausula.query.filter_by(codigo=item["codigo"]).first()
        if not existe:
            db.session.add(
                PlantillaClausula(
                    codigo=item["codigo"],
                    tipo_contrato="larga_duracion",
                    titulo=item["titulo"],
                    contenido=item["contenido"].strip(),
                    orden_defecto=item["orden_defecto"],
                    activa=True,
                    editable=True,
                )
            )
    db.session.commit()


# =========================================================
# INICIALIZADORES
# =========================================================

def inicializar_intervinientes_contrato(contrato):
    if contrato.intervinientes.count() > 0:
        return

    if contrato.propiedad and contrato.propiedad.cuenta:
        cuenta = contrato.propiedad.cuenta
        db.session.add(
            ContratoInterviniente(
                contrato_id=contrato.id,
                rol="arrendador",
                nombre=cuenta.nombre_fiscal,
                dni=cuenta.nif_cif,
                telefono=cuenta.telefono,
                email=cuenta.email,
                direccion=cuenta.direccion,
                orden=1,
                activo=True,
            )
        )

        firmante = cuenta.representantes.filter_by(es_firmante=True, activo=True).first()
        if firmante:
            db.session.add(
                ContratoInterviniente(
                    contrato_id=contrato.id,
                    rol="representante",
                    nombre=firmante.nombre,
                    dni=firmante.dni,
                    telefono=firmante.telefono,
                    email=firmante.email,
                    firma_en_nombre_de=cuenta.nombre_fiscal,
                    observaciones=firmante.cargo,
                    orden=1,
                    activo=True,
                )
            )

    elif contrato.propiedad and contrato.propiedad.propietario:
        user = contrato.propiedad.propietario
        db.session.add(
            ContratoInterviniente(
                contrato_id=contrato.id,
                rol="arrendador",
                nombre=f"{user.nombre or ''} {user.apellidos or ''}".strip() or user.username,
                email=user.email,
                orden=1,
                activo=True,
            )
        )

    if contrato.inquilino:
        inq = contrato.inquilino
        db.session.add(
            ContratoInterviniente(
                contrato_id=contrato.id,
                rol="arrendatario",
                nombre=f"{inq.nombre or ''} {inq.apellidos or ''}".strip(),
                dni=inq.dni,
                telefono=inq.telefono,
                email=inq.email,
                direccion=getattr(inq, "direccion", None),
                orden=1,
                activo=True,
            )
        )


def inicializar_clausulas_contrato(contrato, tipo_contrato="larga_duracion"):
    if contrato.clausulas.count() > 0:
        return

    plantillas = PlantillaClausula.query.filter_by(
        tipo_contrato=tipo_contrato,
        activa=True
    ).order_by(PlantillaClausula.orden_defecto.asc()).all()

    orden = 1
    for p in plantillas:
        db.session.add(
            ContratoClausula(
                contrato_id=contrato.id,
                plantilla_id=p.id,
                titulo=p.titulo,
                contenido=p.contenido,
                orden=orden,
                activa=True,
                editable=p.editable,
            )
        )
        orden += 1


# =========================================================
# PERMISOS / RENDER
# =========================================================

def _contrato_permitido(contrato):
    if not contrato or not contrato.propiedad:
        return False

    if not propiedad_es_visible(contrato.propiedad):
        return False

    if not usuario_tiene_permiso('puede_gestionar_contratos') and not current_user.es_admin() and not current_user.es_principal:
        return False

    return True


def _render_clausulas(contrato):
    resultado = []
    for clausula in contrato.clausulas.filter_by(activa=True).order_by(ContratoClausula.orden.asc()).all():
        texto = Template(clausula.contenido).render(
            contrato=contrato,
            propiedad=contrato.propiedad,
            inquilino=contrato.inquilino,
            arrendadores=contrato.arrendadores(),
            arrendatarios=contrato.arrendatarios(),
            avalistas=contrato.avalistas(),
            representantes=contrato.representantes(),
        )
        resultado.append({
            "titulo": clausula.titulo,
            "contenido": texto.strip(),
            "orden": clausula.orden,
            "id": clausula.id,
        })
    return resultado


# =========================================================
# DOCUMENTO
# =========================================================

@contratos_bp.route("/<int:contrato_id>/documento")
@login_required
def documento_contrato(contrato_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    propiedad = contrato.propiedad

    if propiedad is None:
        abort(404)

    if not _contrato_permitido(contrato):
        abort(403)

    sembrar_plantillas_clausulas()
    inicializar_intervinientes_contrato(contrato)
    inicializar_clausulas_contrato(contrato)
    db.session.commit()

    firmante_id = request.args.get("firmante_id", type=int)
    firmante = None
    representantes = []

    if propiedad.cuenta_id:
        representantes = RepresentanteCuenta.query.filter_by(
            cuenta_id=propiedad.cuenta_id,
            activo=True
        ).order_by(RepresentanteCuenta.nombre.asc()).all()

        if firmante_id:
            firmante = RepresentanteCuenta.query.filter_by(
                id=firmante_id,
                cuenta_id=propiedad.cuenta_id,
                activo=True
            ).first()

        if firmante is None:
            firmante = RepresentanteCuenta.query.filter_by(
                cuenta_id=propiedad.cuenta_id,
                es_firmante=True,
                activo=True
            ).first()

    clausulas_renderizadas = _render_clausulas(contrato)
    fotos = contrato.fotos.filter_by(activa=True).order_by(ContratoFoto.orden.asc()).all()
    anexos = contrato.anexos.filter_by(activo=True).order_by(ContratoAnexo.orden.asc()).all()

    return render_template(
        "contratos/contrato_base.html",
        contrato=contrato,
        propiedad=propiedad,
        inquilino=contrato.inquilino,
        firmante=firmante,
        representantes=representantes,
        clausulas_renderizadas=clausulas_renderizadas,
        fotos=fotos,
        anexos=anexos,
    )


# =========================================================
# EDITAR DOCUMENTACIÓN CONTRACTUAL
# =========================================================

@contratos_bp.route("/<int:contrato_id>/editar", methods=["GET", "POST"])
@login_required
def editar_contrato(contrato_id):
    if not puede_usar_modulo(current_user, "contratos"):
        flash("Tu plan no permite gestionar contratos.", "warning")
        return redirect(url_for("main.dashboard"))

    if not usuario_tiene_permiso('puede_gestionar_contratos'):
        flash("No tienes permisos para gestionar contratos.", "danger")
        return redirect(url_for("main.dashboard"))

    contrato = Contrato.query.get_or_404(contrato_id)

    if not _contrato_permitido(contrato):
        abort(403)

    sembrar_plantillas_clausulas()
    inicializar_intervinientes_contrato(contrato)
    inicializar_clausulas_contrato(contrato)

    if not contrato.devolucion_fianza_texto:
        contrato.devolucion_fianza_texto = texto_base_devolucion_fianza()

    if not contrato.devolucion_adelantado_texto:
        contrato.devolucion_adelantado_texto = texto_base_devolucion_adelantados()

    db.session.commit()

    if request.method == "POST":
        contrato.devolucion_fianza_texto = request.form.get("devolucion_fianza_texto")
        contrato.devolucion_adelantado_texto = request.form.get("devolucion_adelantado_texto")
        contrato.inventario_texto = request.form.get("inventario_texto")

        for interviniente in contrato.intervinientes.order_by(ContratoInterviniente.orden.asc()).all():
            pref = f"interviniente_{interviniente.id}_"
            interviniente.rol = request.form.get(pref + "rol", interviniente.rol)
            interviniente.nombre = request.form.get(pref + "nombre", interviniente.nombre)
            interviniente.dni = request.form.get(pref + "dni")
            interviniente.telefono = request.form.get(pref + "telefono")
            interviniente.email = request.form.get(pref + "email")
            interviniente.direccion = request.form.get(pref + "direccion")
            interviniente.firma_en_nombre_de = request.form.get(pref + "firma_en_nombre_de")
            interviniente.observaciones = request.form.get(pref + "observaciones")
            interviniente.orden = int(request.form.get(pref + "orden") or 0)
            interviniente.activo = True if request.form.get(pref + "activo") == "on" else False

        nuevo_nombre = (request.form.get("nuevo_interviniente_nombre") or "").strip()
        if nuevo_nombre:
            db.session.add(
                ContratoInterviniente(
                    contrato_id=contrato.id,
                    rol=request.form.get("nuevo_interviniente_rol") or "avalista",
                    nombre=nuevo_nombre,
                    dni=request.form.get("nuevo_interviniente_dni"),
                    telefono=request.form.get("nuevo_interviniente_telefono"),
                    email=request.form.get("nuevo_interviniente_email"),
                    direccion=request.form.get("nuevo_interviniente_direccion"),
                    firma_en_nombre_de=request.form.get("nuevo_interviniente_firma_en_nombre_de"),
                    observaciones=request.form.get("nuevo_interviniente_observaciones"),
                    orden=int(request.form.get("nuevo_interviniente_orden") or 99),
                    activo=True,
                )
            )

        for clausula in contrato.clausulas.order_by(ContratoClausula.orden.asc()).all():
            pref = f"clausula_{clausula.id}_"
            clausula.titulo = request.form.get(pref + "titulo", clausula.titulo)
            clausula.contenido = request.form.get(pref + "contenido", clausula.contenido)
            clausula.orden = int(request.form.get(pref + "orden") or 0)
            clausula.activa = True if request.form.get(pref + "activa") == "on" else False

        nuevos_titulos = request.form.getlist("nueva_clausula_titulo[]")
        nuevos_contenidos = request.form.getlist("nueva_clausula_contenido[]")
        nuevos_ordenes = request.form.getlist("nueva_clausula_orden[]")

        total = max(len(nuevos_titulos), len(nuevos_contenidos), len(nuevos_ordenes))
        for i in range(total):
            titulo = (nuevos_titulos[i] if i < len(nuevos_titulos) else "").strip()
            contenido = (nuevos_contenidos[i] if i < len(nuevos_contenidos) else "").strip()
            orden_txt = (nuevos_ordenes[i] if i < len(nuevos_ordenes) else "").strip()

            if titulo and contenido:
                db.session.add(
                    ContratoClausula(
                        contrato_id=contrato.id,
                        titulo=titulo,
                        contenido=contenido,
                        orden=int(orden_txt or 99),
                        activa=True,
                        editable=True,
                    )
                )

        plantilla_insertar_id = request.form.get("plantilla_existente_id")
        if plantilla_insertar_id:
            plantilla = PlantillaClausula.query.get(int(plantilla_insertar_id))
            if plantilla:
                max_orden = db.session.query(db.func.max(ContratoClausula.orden)).filter_by(
                    contrato_id=contrato.id
                ).scalar() or 0
                db.session.add(
                    ContratoClausula(
                        contrato_id=contrato.id,
                        plantilla_id=plantilla.id,
                        titulo=plantilla.titulo,
                        contenido=plantilla.contenido,
                        orden=max_orden + 1,
                        activa=True,
                        editable=True,
                    )
                )

        nuevos_titulos_foto = request.form.getlist("nueva_foto_titulo[]")
        nuevas_rutas_foto = request.form.getlist("nueva_foto_ruta[]")
        nuevas_desc_foto = request.form.getlist("nueva_foto_descripcion[]")
        nuevos_ordenes_foto = request.form.getlist("nueva_foto_orden[]")
        nuevas_habitaciones_foto = request.form.getlist("nueva_foto_habitacion_id[]")

        total_fotos = max(
            len(nuevos_titulos_foto),
            len(nuevas_rutas_foto),
            len(nuevas_desc_foto),
            len(nuevos_ordenes_foto),
            len(nuevas_habitaciones_foto)
        )

        for i in range(total_fotos):
            ruta = (nuevas_rutas_foto[i] if i < len(nuevas_rutas_foto) else "").strip()
            if ruta:
                habitacion_txt = (nuevas_habitaciones_foto[i] if i < len(nuevas_habitaciones_foto) else "").strip()
                db.session.add(
                    ContratoFoto(
                        contrato_id=contrato.id,
                        habitacion_id=int(habitacion_txt) if habitacion_txt else None,
                        titulo=(nuevos_titulos_foto[i] if i < len(nuevos_titulos_foto) else "").strip(),
                        ruta=ruta,
                        descripcion=(nuevas_desc_foto[i] if i < len(nuevas_desc_foto) else "").strip(),
                        orden=int((nuevos_ordenes_foto[i] if i < len(nuevos_ordenes_foto) else "99") or 99),
                        activa=True,
                    )
                )

        nuevo_anexo_titulo = (request.form.get("nuevo_anexo_titulo") or "").strip()
        nuevo_anexo_contenido = (request.form.get("nuevo_anexo_contenido") or "").strip()
        nuevo_anexo_habitacion_id = (request.form.get("nuevo_anexo_habitacion_id") or "").strip()

        if nuevo_anexo_titulo and nuevo_anexo_contenido:
            db.session.add(
                ContratoAnexo(
                    contrato_id=contrato.id,
                    habitacion_id=int(nuevo_anexo_habitacion_id) if nuevo_anexo_habitacion_id else None,
                    titulo=nuevo_anexo_titulo,
                    contenido=nuevo_anexo_contenido,
                    tipo="inventario",
                    orden=int(request.form.get("nuevo_anexo_orden") or 99),
                    activo=True,
                )
            )

        guardar_como_plantilla = request.form.get("guardar_clausula_como_plantilla") == "on"
        if guardar_como_plantilla:
            plantilla_titulo = (request.form.get("nueva_clausula_titulo_plantilla") or "").strip()
            plantilla_contenido = (request.form.get("nueva_clausula_contenido_plantilla") or "").strip()
            plantilla_codigo = (request.form.get("nueva_clausula_codigo_plantilla") or "").strip()

            if plantilla_titulo and plantilla_contenido and plantilla_codigo:
                existe = PlantillaClausula.query.filter_by(codigo=plantilla_codigo).first()
                if not existe:
                    db.session.add(
                        PlantillaClausula(
                            codigo=plantilla_codigo,
                            tipo_contrato="larga_duracion",
                            titulo=plantilla_titulo,
                            contenido=plantilla_contenido,
                            orden_defecto=99,
                            activa=True,
                            editable=True,
                        )
                    )

        db.session.commit()

        accion = request.form.get("accion", "guardar")
        if accion == "vista_previa":
            return redirect(url_for("contratos.documento_contrato", contrato_id=contrato.id))

        flash("Contrato documental actualizado correctamente.", "success")
        return redirect(url_for("contratos.editar_contrato", contrato_id=contrato.id))

    fotos = contrato.fotos.order_by(ContratoFoto.orden.asc()).all()
    anexos = contrato.anexos.order_by(ContratoAnexo.orden.asc()).all()
    habitaciones = Habitacion.query.filter_by(
        propiedad_id=contrato.propiedad_id
    ).order_by(Habitacion.orden.asc()).all()
    plantillas_existentes = PlantillaClausula.query.filter_by(
        tipo_contrato="larga_duracion",
        activa=True
    ).order_by(PlantillaClausula.titulo.asc()).all()

    return render_template(
        "contratos/editar_contrato.html",
        contrato=contrato,
        propiedad=contrato.propiedad,
        inquilino=contrato.inquilino,
        intervinientes=contrato.intervinientes.order_by(ContratoInterviniente.orden.asc()).all(),
        clausulas=contrato.clausulas.order_by(ContratoClausula.orden.asc()).all(),
        fotos=fotos,
        anexos=anexos,
        habitaciones=habitaciones,
        plantillas_existentes=plantillas_existentes,
    )


# =========================================================
# ELIMINAR
# =========================================================

@contratos_bp.route("/<int:contrato_id>/interviniente/<int:interviniente_id>/eliminar", methods=["POST"])
@login_required
def eliminar_interviniente_contrato(contrato_id, interviniente_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    interviniente = ContratoInterviniente.query.get_or_404(interviniente_id)

    if not _contrato_permitido(contrato) or interviniente.contrato_id != contrato.id:
        abort(403)

    db.session.delete(interviniente)
    db.session.commit()
    flash("Interviniente eliminado.", "info")
    return redirect(url_for("contratos.editar_contrato", contrato_id=contrato.id))


@contratos_bp.route("/<int:contrato_id>/clausula/<int:clausula_id>/eliminar", methods=["POST"])
@login_required
def eliminar_clausula_contrato(contrato_id, clausula_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    clausula = ContratoClausula.query.get_or_404(clausula_id)

    if not _contrato_permitido(contrato) or clausula.contrato_id != contrato.id:
        abort(403)

    db.session.delete(clausula)
    db.session.commit()
    flash("Cláusula eliminada.", "info")
    return redirect(url_for("contratos.editar_contrato", contrato_id=contrato.id))


@contratos_bp.route("/<int:contrato_id>/foto/<int:foto_id>/eliminar", methods=["POST"])
@login_required
def eliminar_foto_contrato(contrato_id, foto_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    foto = ContratoFoto.query.get_or_404(foto_id)

    if not _contrato_permitido(contrato) or foto.contrato_id != contrato.id:
        abort(403)

    db.session.delete(foto)
    db.session.commit()
    flash("Foto eliminada.", "info")
    return redirect(url_for("contratos.editar_contrato", contrato_id=contrato.id))


@contratos_bp.route("/<int:contrato_id>/anexo/<int:anexo_id>/eliminar", methods=["POST"])
@login_required
def eliminar_anexo_contrato(contrato_id, anexo_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    anexo = ContratoAnexo.query.get_or_404(anexo_id)

    if not _contrato_permitido(contrato) or anexo.contrato_id != contrato.id:
        abort(403)

    db.session.delete(anexo)
    db.session.commit()
    flash("Anexo eliminado.", "info")
    return redirect(url_for("contratos.editar_contrato", contrato_id=contrato.id))


# =========================================================
# SUBIR / BAJAR CLÁUSULAS
# =========================================================

@contratos_bp.route("/<int:contrato_id>/clausula/<int:clausula_id>/subir", methods=["POST"])
@login_required
def subir_clausula_contrato(contrato_id, clausula_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    clausula = ContratoClausula.query.get_or_404(clausula_id)

    if not _contrato_permitido(contrato) or clausula.contrato_id != contrato.id:
        abort(403)

    anterior = ContratoClausula.query.filter(
        ContratoClausula.contrato_id == contrato.id,
        ContratoClausula.orden < clausula.orden
    ).order_by(ContratoClausula.orden.desc()).first()

    if anterior:
        orden_actual = clausula.orden
        clausula.orden = anterior.orden
        anterior.orden = orden_actual
        db.session.commit()

    return redirect(url_for("contratos.editar_contrato", contrato_id=contrato.id))


@contratos_bp.route("/<int:contrato_id>/clausula/<int:clausula_id>/bajar", methods=["POST"])
@login_required
def bajar_clausula_contrato(contrato_id, clausula_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    clausula = ContratoClausula.query.get_or_404(clausula_id)

    if not _contrato_permitido(contrato) or clausula.contrato_id != contrato.id:
        abort(403)

    siguiente = ContratoClausula.query.filter(
        ContratoClausula.contrato_id == contrato.id,
        ContratoClausula.orden > clausula.orden
    ).order_by(ContratoClausula.orden.asc()).first()

    if siguiente:
        orden_actual = clausula.orden
        clausula.orden = siguiente.orden
        siguiente.orden = orden_actual
        db.session.commit()

    return redirect(url_for("contratos.editar_contrato", contrato_id=contrato.id))