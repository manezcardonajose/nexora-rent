from models import Reserva, Ingreso, Gasto, Contrato
from datetime import datetime


def calcular_rentabilidad_propiedad(propiedad_id):

    # VACACIONAL
    reservas = Reserva.query.filter_by(propiedad_id=propiedad_id).all()
    ingresos_vacacional = sum(r.precio_total or 0 for r in reservas)

    # LARGA DURACIÓN
    contratos = Contrato.query.filter_by(propiedad_id=propiedad_id).all()
    ingresos_ld = sum(c.renta_mensual or 0 for c in contratos)

    # GASTOS
    gastos = sum(g.cantidad or 0 for g in Gasto.query.filter_by(propiedad_id=propiedad_id))

    # RESULTADOS
    beneficio_vacacional = ingresos_vacacional - gastos
    beneficio_ld = ingresos_ld - gastos

    # RECOMENDACIÓN
    if beneficio_vacacional > beneficio_ld:
        recomendacion = "VACACIONAL"
    elif beneficio_ld > beneficio_vacacional:
        recomendacion = "LARGA DURACIÓN"
    else:
        recomendacion = "INDIFERENTE"

    return {
        "vacacional": beneficio_vacacional,
        "larga_duracion": beneficio_ld,
        "gastos": gastos,
        "recomendacion": recomendacion
    }