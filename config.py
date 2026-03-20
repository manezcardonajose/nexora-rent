import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env (si existe)
load_dotenv()

class Config:
    # Clave secreta para sesiones
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'clave-secreta-para-desarrollo-cambiar-en-produccion'
    
    # URI de la base de datos (obligatorio)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///app.db'
    
    # Desactivar seguimiento de modificaciones (mejor rendimiento)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
     # Para Render, a veces la URL de PostgreSQL viene con "postgres://" en lugar de "postgresql://"
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)

    
    # Configuración de email (para más adelante)
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() in ['true', '1', 't']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or 'restelraco@gmail.com'
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or 'muzm dban tsiq qgvy'
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or ('Gestor Alquiler', 'noreply@gestor.com')