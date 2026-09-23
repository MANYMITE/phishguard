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


# Simulation templates. Keys are stable identifiers used by campaigns.
TEMPLATES: dict[str, dict] = {
    "acme_webmail": {
        "title": "Acme Webmail",
        "description": "A generic corporate webmail portal.",
        "file": "sim_acme_webmail.html",
    },
}


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
