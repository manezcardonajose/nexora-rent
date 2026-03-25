from app import app, db
from models import User

username = input("Usuario: ")
new_password = input("Nueva contraseña: ")

with app.app_context():
    user = User.query.filter_by(username=username).first()
    if user:
        user.set_password(new_password)
        db.session.commit()
        print(f"✅ Contraseña de {username} cambiada correctamente")
    else:
        print(f"❌ Usuario {username} no encontrado")