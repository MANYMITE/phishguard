"""PhishGuard entry point: python run.py"""
import os

from phishguard import create_app
from phishguard import db

app = create_app()


def _int_env(name: str, default: int) -> int:
    try:
        p = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return p if p > 0 else default


if __name__ == "__main__":
    db.configure_audit_logging()  # file trail for real runs; tests skip it
    host = os.environ.get("PHISHGUARD_HOST", "127.0.0.1")
    port = _int_env("PORT", 5000)
    if host != "127.0.0.1":
        print(f"⚠ Listening on {host}:{port} — anyone on that network can "
              f"reach this server. Prefer a tunnel: bash scripts/share.sh")
    app.run(host=host, port=port)
