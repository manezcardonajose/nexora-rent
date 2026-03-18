from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from urllib.parse import urlparse as url_parse
import faulthandler
faulthandler.enable()

# Importar db desde models
from models import db

app = Flask(__name__)
app.config.from_object(Config)

# Inicializar extensiones
db.init_app(app)
login = LoginManager(app)
login.login_view = 'auth.login'

# Importar modelos después de db y login
from models import User, Propiedad, Reserva, Tarea, CalendarioIcal

# 🔴 IMPORTANTE: IMPORTAR TODOS LOS BLUEPRINTS
from propiedades import propiedades_bp
from reservas import reservas_bp
from calendario import calendario_bp
from tareas import tareas_bp
from auth import auth_bp
from main import main_bp
from ingresos import ingresos_bp      # <-- DEBE ESTAR
from gastos import gastos_bp          # <-- DEBE ESTAR
from api import api_bp
from habitaciones import habitaciones_bp
from pagos import pagos_bp
from bloqueos import bloqueos_bp
from plataformas import plataformas_bp
from informes import informes_bp
from huespedes import huespedes_bp

# 🔴 IMPORTANTE: REGISTRAR TODOS LOS BLUEPRINTS
app.register_blueprint(propiedades_bp)
app.register_blueprint(reservas_bp)
app.register_blueprint(calendario_bp)
app.register_blueprint(tareas_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(ingresos_bp)   # <-- DEBE ESTAR
app.register_blueprint(gastos_bp)     # <-- DEBE ESTAR
app.register_blueprint(api_bp)
app.register_blueprint(habitaciones_bp)
app.register_blueprint(pagos_bp)
app.register_blueprint(bloqueos_bp)
app.register_blueprint(plataformas_bp)
app.register_blueprint(informes_bp)
app.register_blueprint(huespedes_bp)


@login.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

# ... (posiblemente más código)
# Al final de app.py, reemplaza el bloque existente con esto:
if __name__ != '__main__':
    # Cuando corre en Render (como módulo importado)
    import logging
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
else:
    # Cuando corre localmente
    with app.app_context():
        db.create_all()
    print("🌐 Servidor disponible en:")
    print("   • Local: http://192.168.8.5:5000")
    print("   • Red:   http://[TU-IP]:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)