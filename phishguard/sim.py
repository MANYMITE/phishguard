"""Simulation blueprint: the participant-facing side of a campaign.

Every simulation route requires the participant's personal random token,
so links cannot be guessed or enumerated — important because these pages
are meant to be *delivered* to a specific person, not discovered.

The heart of PhishGuard's safety model lives in `submit()`:

* The handler never reads the password field. Flask parses the form, the
  password value is dropped with the rest of `request.form` the moment the
  function returns, and the only things recorded are `clicked`/`submitted`
  events plus a hashed user agent. Tests assert a canary password never
  reaches the database file.
"""
import hashlib

from flask import Blueprint, abort, redirect, render_template, request, url_for

from . import db

sim_bp = Blueprint("sim", __name__, url_prefix="/sim")


# The template catalog — fictional portals, deliberately clones of nothing.
# Every entry renders through sim_portal.html with its own theme, keeps the
# honest "Training exercise" banner, and posts to the same credential-
# discarding handler. Keys are stable identifiers used by campaigns.
CATALOG: list[dict] = [
    {
        "key": "acme_webmail",
        "title": "Acme Webmail",
        "description": "Generic corporate webmail portal",
        "icon": "\u2709\ufe0f",
        "field_label": "Email address",
        "tagline": "Sign in to continue to your mailbox",
        "accent": "#1c5fae",
        "accent_dark": "#174f92",
        "text_dark": "#1c3a5e",
        "file": "sim_portal.html",
    },
    {
        "key": "corpnet_vpn",
        "title": "CorpNet VPN",
        "description": "Corporate VPN gateway login",
        "icon": "\U0001f510",
        "field_label": "Username",
        "tagline": "Secure remote access portal",
        "accent": "#14532d",
        "accent_dark": "#0f3d22",
        "text_dark": "#1a3c2a",
        "file": "sim_portal.html",
    },
    {
        "key": "meridian_bank",
        "title": "Meridian Bank",
        "description": "Online banking sign-in",
        "icon": "\U0001f3e6",
        "field_label": "Customer ID",
        "tagline": "Welcome back — sign in to your accounts",
        "accent": "#7a1f1f",
        "accent_dark": "#5f1717",
        "text_dark": "#4a1414",
        "file": "sim_portal.html",
    },
    {
        "key": "cloudvault_drive",
        "title": "CloudVault Drive",
        "description": "File storage and sharing portal",
        "icon": "\u2601\ufe0f",
        "field_label": "Email address",
        "tagline": "Your files, anywhere",
        "accent": "#6d28d9",
        "accent_dark": "#571fae",
        "text_dark": "#3b1a63",
        "file": "sim_portal.html",
    },
    {
        "key": "payhub_payroll",
        "title": "PayHub Payroll",
        "description": "Payroll and payslip portal",
        "icon": "\U0001f4b0",
        "field_label": "Employee ID",
        "tagline": "View your payslips and tax documents",
        "accent": "#b45309",
        "accent_dark": "#8f4207",
        "text_dark": "#5c2e06",
        "file": "sim_portal.html",
    },
    {
        "key": "helpdesk_it",
        "title": "IT HelpDesk",
        "description": "Internal support ticket center",
        "icon": "\U0001f6e0\ufe0f",
        "field_label": "Employee email",
        "tagline": "Log a ticket or check ticket status",
        "accent": "#0f766e",
        "accent_dark": "#0b5952",
        "text_dark": "#123f3b",
        "file": "sim_portal.html",
    },
    {
        "key": "medcare_portal",
        "title": "MedCare Portal",
        "description": "Patient health records portal",
        "icon": "\U0001fa7a",
        "field_label": "Patient ID",
        "tagline": "Your appointments and results, in one place",
        "accent": "#0e7490",
        "accent_dark": "#0a5a70",
        "text_dark": "#0d4a5a",
        "file": "sim_portal.html",
    },
    {
        "key": "jetstream_air",
        "title": "JetStream Rewards",
        "description": "Airline loyalty and bookings",
        "icon": "\u2708\ufe0f",
        "field_label": "Membership number",
        "tagline": "Manage your bookings and miles",
        "accent": "#b91c1c",
        "accent_dark": "#921515",
        "text_dark": "#5c1010",
        "file": "sim_portal.html",
    },
    {
        "key": "swiftparcel",
        "title": "SwiftParcel",
        "description": "Parcel tracking and delivery",
        "icon": "\U0001f4e6",
        "field_label": "Email address",
        "tagline": "Track parcels and manage deliveries",
        "accent": "#c2410c",
        "accent_dark": "#9a3409",
        "text_dark": "#6b2506",
        "file": "sim_portal.html",
    },
    {
        "key": "learnly_lms",
        "title": "Learnly e-Learning",
        "description": "Training courses platform",
        "icon": "\U0001f393",
        "field_label": "Student email",
        "tagline": "Your courses are waiting",
        "accent": "#4d7c0f",
        "accent_dark": "#3c6109",
        "text_dark": "#2e4a08",
        "file": "sim_portal.html",
    },
]

# dict view kept for lookups and backward compatibility (admin validation,
# fail-fast template check, tests).
TEMPLATES: dict[str, dict] = {entry["key"]: entry for entry in CATALOG}


def _load(campaign_id: int, participant_id: int, sim_token: str):
    """Resolve campaign/participant/template, enforcing the personal token."""
    c = db.get_campaign(campaign_id)
    p = db.get_participant(participant_id, campaign_id)
    if c is None or p is None:
        abort(404)
    if not sim_token or not p["sim_token"] or sim_token != p["sim_token"]:
        # Wrong or missing token: behave exactly like "does not exist".
        abort(404)
    template = TEMPLATES.get(c["template_key"])
    if template is None:
        abort(404)
    return c, p, template


@sim_bp.get("/<int:campaign_id>/<int:participant_id>-<sim_token>")
def landing(campaign_id: int, participant_id: int, sim_token: str):
    c, p, template = _load(campaign_id, participant_id, sim_token)
    db.record_event(participant_id, campaign_id, "clicked",
                    user_agent=_ua_hash())
    return render_template(template["file"], campaign=c, participant=p,
                           template=template)


@sim_bp.post("/<int:campaign_id>/<int:participant_id>-<sim_token>")
def submit(campaign_id: int, participant_id: int, sim_token: str):
    """Receive a simulated submission.

    SAFETY: `request.form` may contain a password. We deliberately do NOT
    read it into any variable that survives this function. Only whitelisted,
    non-secret metadata (sanitised through safety.sanitize_fields) could ever
    be recorded — and today the schema stores nothing beyond event type,
    timestamp and a user-agent hash.
    """
    c, p, template = _load(campaign_id, participant_id, sim_token)

    # request.form (including any credentials) is discarded here — nothing
    # from it is stored, logged or returned.
    _ = request.form
    db.record_event(participant_id, campaign_id, "submitted",
                    user_agent=_ua_hash())
    return redirect(url_for("sim.caught", campaign_id=campaign_id,
                            participant_id=participant_id,
                            sim_token=sim_token))


@sim_bp.get("/<int:campaign_id>/<int:participant_id>-<sim_token>/caught")
def caught(campaign_id: int, participant_id: int, sim_token: str):
    c, p, template = _load(campaign_id, participant_id, sim_token)
    return render_template("caught.html", campaign=c, participant=p,
                           template=template)


def _ua_hash() -> str | None:
    ua = request.headers.get("User-Agent")
    if not ua:
        return None
    # Hash the agent: we keep analytical signal, not raw fingerprint text.
    return hashlib.sha256(ua.encode()).hexdigest()[:16]
