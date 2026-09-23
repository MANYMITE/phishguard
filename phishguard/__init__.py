"""PhishGuard — consent-based phishing-awareness training.

Application factory. See README.md for architecture and safety invariants.
"""
import os

from flask import Flask, jsonify

from . import db
from .admin import admin_bp
from .sim import sim_bp


def create_app(config_overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get(
        "PHISHGUARD_SECRET_KEY", "dev-only-change-me"
    )
    if config_overrides:
        app.config.update(config_overrides)

    db.init_app(app)
    app.register_blueprint(admin_bp)
    app.register_blueprint(sim_bp)

    @app.route("/health")
    def health():
        return jsonify(status="ok", app="phishguard")

    return app
