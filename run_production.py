from app import app

if __name__ != '__main__':
    # Para servidores WSGI como Gunicorn
    application = app
else:
    # Para desarrollo local
    app.run(debug=False, host='0.0.0.0', port=5000)