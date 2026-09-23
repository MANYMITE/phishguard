"""WSGI entry point for production servers (Render, gunicorn, uwsgi…).

    gunicorn -w 2 -b 0.0.0.0:$PORT wsgi:app

Keeps run.py for local dev; this module exposes the configured app.
"""
from phishguard import create_app
from phishguard import db

app = create_app()
db.configure_audit_logging()  # file trail for real deployments
