"""Admin blueprint: authentication, dashboard, campaigns, participants.

Production hardening in this module:

* Session-based admin login (single shared password, rate-limited).
* CSRF tokens on every admin form, verified on every POST.
* Input validation via safety.validate_* with friendly flash messages.
* Consent gates on every creation path — the DB layer double-checks them.
"""
import time

from flask import (
    Blueprint, current_app, flash, g, redirect, render_template, request,
    session, url_for,
)

from . import db
from .safety import (
    ValidationError,
    validate_campaign_name,
    validate_email,
    validate_participant_name,
)
from .sim import TEMPLATES

admin_bp = Blueprint("admin", __name__, url_prefix="/")

_SESSION_KEY = "phishguard_admin"
_LOGIN_WINDOW = 300.0   # seconds
_LOGIN_MAX = 5          # attempts per window per IP


def _attempts_store() -> dict:
    """Per-app attempt store — never shared across app instances/tests."""
    if "login_attempts" not in current_app.extensions:
        current_app.extensions["login_attempts"] = {}
    return current_app.extensions["login_attempts"]


def _login_limited(ip: str) -> bool:
    now = time.monotonic()
    store = _attempts_store()
    recent = [t for t in store.get(ip, []) if now - t < _LOGIN_WINDOW]
    store[ip] = recent
    return len(recent) >= _LOGIN_MAX


def _record_login_attempt(ip: str) -> None:
    _attempts_store().setdefault(ip, []).append(time.monotonic())


@admin_bp.before_app_request
def require_csrf():
    """Verify a CSRF token on every unsafe admin request.

    Simulation POSTs (/sim/...) are excluded: they are the one endpoint
    third parties must be able to hit from an emailed link in a drill.
    """
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        # Tests exercise POST handlers directly; CSRF has its own dedicated
        # tests that force it on via FORCE_CSRF.
        if current_app.config.get("TESTING") and not current_app.config.get(
            "FORCE_CSRF"
        ):
            return None
        if request.path.startswith("/sim/"):
            return None
        token = session.get("_csrf_token")
        supplied = request.form.get("csrf_token")
        if not token or not supplied or supplied != token:
            flash("Your session expired — please try again.", "error")
            return redirect(url_for("admin.dashboard"))
    return None


def _csrf_token() -> str:
    if "_csrf_token" not in session:
        import secrets
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return session["_csrf_token"]


@admin_bp.app_context_processor
def inject_csrf():
    return {"csrf_token": _csrf_token, "admin_signed_in": _is_signed_in}


def _is_signed_in() -> bool:
    return bool(session.get(_SESSION_KEY))


@admin_bp.before_request
def require_login():
    public = {"admin.login", "admin.logout"}
    if request.endpoint in public:
        return None
    if not _is_signed_in():
        return redirect(url_for("admin.login", next=request.path))
    g.admin = True
    return None


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        if _login_limited(ip):
            flash("Too many attempts — wait five minutes and try again.", "error")
            return render_template("login.html"), 429
        _record_login_attempt(ip)
        password = request.form.get("password") or ""
        import hmac
        expected = current_app.config["SECRET_KEY"]
        if hmac.compare_digest(password, expected):
            session.clear()  # prevent fixation
            session[_SESSION_KEY] = True
            _csrf_token()  # mint a fresh CSRF token for the new session
            db.audit("admin_login", f"ip={ip}")
            target = request.args.get("next") or url_for("admin.dashboard")
            if not target.startswith("/"):
                target = url_for("admin.dashboard")
            return redirect(target)
        db.audit("admin_login_failed", f"ip={ip}")
        flash("Wrong admin password.", "error")
    return render_template("login.html")


@admin_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


# ---------------------------------------------------------------------------
# Dashboard & campaigns
# ---------------------------------------------------------------------------

@admin_bp.get("/")
def dashboard():
    rows = []
    for c in db.list_campaigns():
        rows.append({"campaign": c, "stats": db.campaign_stats(c["id"])})
    from .sim import CATALOG
    return render_template("dashboard.html", campaigns=rows,
                           templates=CATALOG,
                           gstats=db.global_stats())


@admin_bp.post("/campaigns")
def create_campaign():
    try:
        name = validate_campaign_name(request.form.get("name"))
        template_key = request.form.get("template_key") or ""
        consent = request.form.get("consent") == "yes"

        if template_key not in TEMPLATES:
            raise ValidationError("Pick a valid simulation template.")
        if not consent:
            raise ValidationError(
                "Consent is required: only run simulations on people who "
                "have agreed to take part in awareness training."
            )
    except ValidationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.dashboard"))

    campaign_id = db.create_campaign(name, template_key, consent=True)
    flash(f"Campaign #{campaign_id} created. Add your participants.", "ok")
    return redirect(url_for("admin.campaign", campaign_id=campaign_id))


@admin_bp.get("/campaigns/<int:campaign_id>")
def campaign(campaign_id):
    c = db.get_campaign(campaign_id)
    if c is None:
        flash("No such campaign.", "error")
        return redirect(url_for("admin.dashboard"))
    participants = db.list_participants(campaign_id)
    links = {
        p["id"]: url_for("sim.landing", campaign_id=campaign_id,
                         participant_id=p["id"], sim_token=p["sim_token"],
                         _external=True)
        for p in participants
    }
    return render_template(
        "campaign.html", campaign=c, participants=participants, links=links,
        stats=db.campaign_stats(campaign_id),
        events=db.participant_events(campaign_id),
    )


@admin_bp.post("/campaigns/<int:campaign_id>/participants")
def add_participant(campaign_id):
    if db.get_campaign(campaign_id) is None:
        flash("No such campaign.", "error")
        return redirect(url_for("admin.dashboard"))
    try:
        name = validate_participant_name(request.form.get("name"))
        email = validate_email(request.form.get("email"))
        consent = request.form.get("consent") == "yes"
        if not consent:
            raise ValidationError(
                "Each participant must have consented before being added."
            )
    except ValidationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.campaign", campaign_id=campaign_id))

    try:
        db.create_participant(campaign_id, name, email, consent=True)
    except ValidationError as exc:  # duplicate email
        flash(str(exc), "error")
        return redirect(url_for("admin.campaign", campaign_id=campaign_id))

    flash(f"Added {name}. Copy their unique simulation link below.", "ok")
    return redirect(url_for("admin.campaign", campaign_id=campaign_id))
