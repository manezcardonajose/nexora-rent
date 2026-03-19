from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from urllib.parse import urlparse as url_parse
import faulthandler
faulthandler.enable()
from flask_mail import Mail
import os  # <-- AÑADIDO para leer variables de entorno

# Importar db desde models
from models import db

app = Flask(__name__)
app.config.from_object(Config)

# Inicializar extensiones
db.init_app(app)
login = LoginManager(app)
login.login_view = 'auth.login'
mail = Mail(app)

# Importar modelos después de db y login
from models import User, Propiedad, Reserva, Tarea, CalendarioIcal

# Importar todos los blueprints
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

# Registrar todos los blueprints
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

@login.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# 🔴 CONFIGURACIÓN PARA PRODUCCIÓN (Render)
if __name__ != '__main__':
    # Cuando corre en Render (como módulo importado)
    import logging
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
    print("🚀 Aplicación iniciada en modo producción (Render)")
else:
    # Cuando corre localmente
    with app.app_context():
        db.create_all()
    
    # Obtener IP local para mostrar
    import socket
    try:
        hostname = socket.gethostname()
        ip_local = socket.gethostbyname(hostname)
    except:
        ip_local = "192.168.x.x"
    
    print("\n" + "="*50)
    print("🌐 SERVIDOR INICIADO CORRECTAMENTE")
    print("="*50)
    print(f"📍 Acceso LOCAL:    http://127.0.0.1:5000")
    print(f"📍 Acceso RED:       http://{ip_local}:5000")
    print("="*50)
    print("📱 Para acceder desde el móvil:")
    print(f"   • Misma WiFi: http://{ip_local}:5000")
    print("="*50 + "\n")
    
    # Usar puerto de entorno o 5000 por defecto
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)