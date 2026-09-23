"""PhishGuard — consent-based phishing-awareness training.

Application factory. See README.md for architecture and safety invariants.
"""
import os

from flask import Flask, jsonify, render_template, request

from . import db
from .admin import admin_bp
from .sim import TEMPLATES, sim_bp

# Honest default message shown by every simulation page. Templates carry
# their own copy; this is the fallback text if one is missing.
BANNER_TEXT = (
    "🛡️ Training exercise — this page is part of an authorised awareness "
    "simulation. Nothing you type here is saved or sent anywhere."
)

_CSP = (
    "default-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "  # inline <style> blocks in templates
    "img-src 'self' data:; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'"
)


def _fail_fast_template_check(app: Flask) -> None:
    """Refuse to start if a registered simulation template is missing."""
    template_dir = os.path.join(app.root_path, app.template_folder)
    for key, tpl in TEMPLATES.items():
        path = os.path.join(template_dir, tpl["file"])
        if not os.path.isfile(path):
            raise RuntimeError(
                f"Simulation template {key!r} points to missing file {path!r}"
            )


def create_app(config_overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get(
        "PHISHGUARD_SECRET_KEY", "dev-only-change-me"
    )
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # forms are tiny; reject abuse
    app.config["BEHIND_PROXY"] = os.environ.get(
        "PHISHGUARD_BEHIND_PROXY", "0"
    ).lower() in ("1", "true", "yes")
    app.config["FORCES_HTTPS"] = os.environ.get(
        "PHISHGUARD_FORCES_HTTPS", "0"
    ).lower() in ("1", "true", "yes")
    if config_overrides:
        app.config.update(config_overrides)

    if app.config["BEHIND_PROXY"]:
        # Running behind a tunnel/reverse proxy (cloudflared, ngrok, nginx…):
        # trust the forwarding headers so generated participant links carry
        # the public https host. Session cookies are marked Secure only when
        # the deployment actually serves HTTPS (tunnels do; plain-HTTP LAN
        # mode must not, or clients would drop the login cookie).
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
        if app.config["FORCES_HTTPS"]:
            app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if app.config["SECRET_KEY"] == "dev-only-change-me" and not app.config.get(
        "TESTING"
    ):
        app.logger.warning(
            "PHISHGUARD_SECRET_KEY is not set; using the development default. "
            "Set a real secret key before letting anyone else use this server."
        )

    db.init_app(app)
    _fail_fast_template_check(app)

    app.register_blueprint(admin_bp)
    app.register_blueprint(sim_bp)

    @app.route("/health")
    def health():
        return jsonify(status="ok", app="phishguard")

    @app.before_request
    def limit_body_size():
        """Deterministic body-size guard (works across Werkzeug versions)."""
        if (request.content_length or 0) > app.config["MAX_CONTENT_LENGTH"]:
            return render_template(
                "error.html", code=413,
                message="Request body too large. Nothing was stored."), 413

    @app.after_request
    def set_security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Content-Security-Policy", _CSP)
        return resp

    @app.errorhandler(400)
    @app.errorhandler(404)
    def not_found(_e):
        if request.accept_mimetypes.best == "application/json":
            return jsonify(error="not found"), 404
        return render_template("error.html", code=404,
                               message="That page doesn't exist."), 404

    @app.errorhandler(413)
    def too_large(_e):
        return render_template(
            "error.html", code=413,
            message="Request body too large. Nothing was stored."), 413

    @app.errorhandler(500)
    def server_error(_e):
        return render_template(
            "error.html", code=500,
            message="Something went wrong on our side. Nothing was stored."), 500

    return app
