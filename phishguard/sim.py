"""Simulation blueprint: the participant-facing side of a campaign.

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
# A template is (title, description, template filename, next_step_name).
TEMPLATES: dict[str, dict] = {
    "acme_webmail": {
        "title": "Acme Webmail",
        "description": "A generic corporate webmail portal.",
        "file": "sim_acme_webmail.html",
        "next_step": "webmail_inbox",
    },
}


@sim_bp.get("/<int:campaign_id>/<int:participant_id>")
def landing(campaign_id: int, participant_id: int):
    c = db.get_campaign(campaign_id)
    p = db.get_participant(participant_id, campaign_id)
    if c is None or p is None:
        abort(404)
    template = TEMPLATES.get(c["template_key"])
    if template is None:
        abort(404)
    db.record_event(participant_id, campaign_id, "clicked",
                    user_agent=_ua_hash())
    return render_template(template["file"], campaign=c, participant=p,
                           template=template)


@sim_bp.post("/<int:campaign_id>/<int:participant_id>")
def submit(campaign_id: int, participant_id: int):
    """Receive a simulated submission.

    SAFETY: `request.form` may contain a password. We deliberately do NOT
    read it into any variable that survives this function. Only whitelisted,
    non-secret metadata (sanitised through safety.sanitize_fields) could ever
    be recorded — and today the schema stores nothing beyond event type,
    timestamp and a user-agent hash.
    """
    c = db.get_campaign(campaign_id)
    p = db.get_participant(participant_id, campaign_id)
    if c is None or p is None:
        abort(404)
    template = TEMPLATES.get(c["template_key"])
    if template is None:
        abort(404)

    # request.form (including any credentials) is discarded here — nothing
    # from it is stored, logged or returned.
    _ = request.form
    db.record_event(participant_id, campaign_id, "submitted",
                    user_agent=_ua_hash())
    return redirect(url_for("sim.caught", campaign_id=campaign_id,
                            participant_id=participant_id))


@sim_bp.get("/<int:campaign_id>/<int:participant_id>/caught")
def caught(campaign_id: int, participant_id: int):
    c = db.get_campaign(campaign_id)
    p = db.get_participant(participant_id, campaign_id)
    if c is None or p is None:
        abort(404)
    template = TEMPLATES.get(c["template_key"])
    return render_template("caught.html", campaign=c, participant=p,
                           template=template)


def _ua_hash() -> str | None:
    ua = request.headers.get("User-Agent")
    if not ua:
        return None
    # Hash the agent: we keep analytical signal, not raw fingerprint text.
    return hashlib.sha256(ua.encode()).hexdigest()[:16]
