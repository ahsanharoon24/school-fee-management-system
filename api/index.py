"""Vercel serverless entry point (WSGI)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import app, init_db, seed_admin  # noqa: E402

try:
    init_db()
    seed_admin()
except Exception as exc:  # pragma: no cover - diagnostics only
    print('startup init warning:', exc)

# Vercel's Python runtime looks for a WSGI/ASGI callable named `app`.
handler = app
