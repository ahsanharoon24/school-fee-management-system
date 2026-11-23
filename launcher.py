"""Launcher — server start karta hai aur browser mein app khol deta hai."""
import os
import sys
import threading
import time
import urllib.request
import webbrowser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

from app import app, init_db, seed_admin

init_db()
seed_admin()


def _run_server():
    app.run(host='0.0.0.0', port=5002, debug=False, use_reloader=False)


threading.Thread(target=_run_server, daemon=True).start()

for _ in range(80):
    try:
        urllib.request.urlopen('http://localhost:5002/login', timeout=1)
        break
    except Exception:
        time.sleep(0.25)

webbrowser.open('http://localhost:5002')

print('=' * 56)
print('  School Fee Management System')
print('  Opening in your browser: http://localhost:5002')
print('  To stop the server, close this window.')
print('=' * 56)

try:
    while True:
        time.sleep(3600)
except KeyboardInterrupt:
    pass
