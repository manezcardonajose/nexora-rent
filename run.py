import os
import sys
import time
import socket
import threading
import webbrowser

# Crear streams reales hacia el "sumidero" del sistema
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")

if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from app import app

HOST = "127.0.0.1"
PORT = 5000


def wait_for_server(host: str, port: int, timeout: int = 15) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.4)
    return False


def open_browser():
    url = f"http://{HOST}:{PORT}"
    if wait_for_server(HOST, PORT):
        webbrowser.open(url)


def run_app():
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    run_app()