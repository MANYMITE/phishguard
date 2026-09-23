"""PhishGuard entry point: python run.py"""
import os

from phishguard import create_app
from phishguard import db

app = create_app()


def _port(default: int = 5000) -> int:
    """Honour $PORT, but never bind to an invalid port (0/unset/garbage)."""
    try:
        p = int(os.environ.get("PORT", default))
    except (TypeError, ValueError):
        return default
    return p if p > 0 else default


if __name__ == "__main__":
    db.configure_audit_logging()  # file trail for real runs; tests skip it
    # Bind to localhost by default. If you expose this beyond your machine,
    # put it behind a real WSGI server + reverse proxy first (see README).
    app.run(host="127.0.0.1", port=_port())
