#!/bin/bash
cd ~/alquiler
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install flask flask-sqlalchemy flask-login flask-wtf gunicorn email-validator requests python-dotenv
# Si no necesitas weasyprint, no lo instales.
# pip install weasyprint  # Opcional, puede fallar.