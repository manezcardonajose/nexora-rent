from flask import Flask
from config import Config
from flask_login import LoginManager
from flask_mail import Mail
import faulthandler
import logging
import os
import socket

from models import db, User
from licencias import licencias_bp
from licencias_utils import SAFE_METHODS, licencia_en_modo_restringido

faulthandler.enable()

app = Flask(__name__)
app.config.from_object(Config)

from datetime import datetime

@app.context_processor
def inject_now():
    return dict(now=datetime.now)

# =========================
# EXTENSIONES
# =========================
db.init_app(app)

login = LoginManager()
login.init_app(app)
login.login_view = 'auth.login'

mail = Mail()
mail.init_app(app)

# =========================
# BLUEPRINTS
# =========================
from propiedades import propiedades_bp
from reservas import reservas_bp
from calendario import calendario_bp
from tareas import tareas_bp
from auth import auth_bp
from main import main_bp
from ingresos import ingresos_bp
from gastos import gastos_bp
from api import api_bp
from habitaciones import habitaciones_bp
from pagos import pagos_bp
from bloqueos import bloqueos_bp
from plataformas import plataformas_bp
from informes import informes_bp
from huespedes import huespedes_bp
from alquileres import alquileres_bp
from recibos import recibos_bp
from finanzas import finanzas_bp
from contratos import contratos_bp
from blueprints.simulador import simulador_bp
from ia import ia_bp


app.register_blueprint(propiedades_bp)
app.register_blueprint(reservas_bp)
app.register_blueprint(calendario_bp)
app.register_blueprint(tareas_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(ingresos_bp)
app.register_blueprint(gastos_bp)
app.register_blueprint(api_bp)
app.register_blueprint(habitaciones_bp)
app.register_blueprint(pagos_bp)
app.register_blueprint(bloqueos_bp)
app.register_blueprint(plataformas_bp)
app.register_blueprint(informes_bp)
app.register_blueprint(huespedes_bp)
app.register_blueprint(alquileres_bp)
app.register_blueprint(recibos_bp)
app.register_blueprint(finanzas_bp)
app.register_blueprint(contratos_bp)
app.register_blueprint(simulador_bp)
app.register_blueprint(licencias_bp)
app.register_blueprint(ia_bp)

# =========================
# LOGIN
# =========================
@login.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except Exception:
        return None
    
from flask import redirect, url_for, flash, request
from flask_login import current_user

@app.before_request
def verificar_licencia():
    if not current_user.is_authenticated:
        return None

    if not current_user.activo:
        flash('Cuenta inactiva', 'danger')
        return redirect(url_for('auth.logout'))

    if current_user.es_admin() or not licencia_en_modo_restringido(current_user):
        return None

    endpoint = request.endpoint or ''
    if endpoint.startswith('static'):
        return None

    if request.method in SAFE_METHODS:
        return None

    if endpoint in {'auth.logout'}:
        return None

    flash('Licencia caducada: estás en modo restringido y no puedes guardar cambios hasta renovar.', 'warning')
    return redirect(url_for('main.dashboard'))

# =========================
# LOGS EN PRODUCCIÓN (RENDER / GUNICORN)
# =========================
if __name__ != '__main__':
    gunicorn_logger = logging.getLogger('gunicorn.error')
    if gunicorn_logger.handlers:
        app.logger.handlers = gunicorn_logger.handlers
        app.logger.setLevel(gunicorn_logger.level)

    app.logger.info("🚀 Aplicación iniciada en modo producción")
else:
    # Solo para desarrollo local
    with app.app_context():
        db.create_all()

    try:
        hostname = socket.gethostname()
        ip_local = socket.gethostbyname(hostname)
    except Exception:
        ip_local = "192.168.x.x"

    port = int(os.environ.get('PORT', 5000))

    print("\n" + "=" * 50)
    print("🌐 SERVIDOR INICIADO CORRECTAMENTE")
    print("=" * 50)
    print(f"📍 Acceso LOCAL: http://127.0.0.1:{port}")
    print(f"📍 Acceso RED:   http://{ip_local}:{port}")
    print("=" * 50)
    print("📱 Para acceder desde el móvil:")
    print(f"   • Misma WiFi: http://{ip_local}:{port}")
    print("=" * 50 + "\n")

    app.run(debug=True, host='0.0.0.0', port=port)