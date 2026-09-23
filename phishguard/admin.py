"""Admin blueprint: dashboard, campaigns, participants, reporting.

Consent gates live here — every creation path requires an explicit
confirmation from the trainer, and the DB layer double-checks it.
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from . import db
from .sim import TEMPLATES

admin_bp = Blueprint("admin", __name__, url_prefix="/")


@admin_bp.get("/")
def dashboard():
    campaigns = db.list_campaigns()
    rows = []
    for c in campaigns:
        stats = db.campaign_stats(c["id"])
        rows.append({
            "campaign": c,
            "stats": stats,
            "url": url_for("sim.landing", campaign_id=c["id"],
                           participant_id=0, _external=True),
        })
    return render_template("dashboard.html", campaigns=rows,
                           templates=sorted(TEMPLATES))


@admin_bp.post("/campaigns")
def create_campaign():
    name = (request.form.get("name") or "").strip()
    template_key = request.form.get("template_key") or ""
    consent = request.form.get("consent") == "yes"

    if not name:
        flash("Campaign needs a name.", "error")
        return redirect(url_for("admin.dashboard"))
    if template_key not in TEMPLATES:
        flash("Pick a valid simulation template.", "error")
        return redirect(url_for("admin.dashboard"))
    if not consent:
        flash(
            "Consent is required: only run simulations on people who have "
            "agreed to take part in awareness training.",
            "error",
        )
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
                         participant_id=p["id"], _external=True)
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
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    consent = request.form.get("consent") == "yes"

    if not name or not email or "@" not in email:
        flash("Participant needs a name and a valid email.", "error")
        return redirect(url_for("admin.campaign", campaign_id=campaign_id))
    if not consent:
        flash("Each participant must have consented before being added.", "error")
        return redirect(url_for("admin.campaign", campaign_id=campaign_id))

    db.create_participant(campaign_id, name, email, consent=True)
    flash(f"Added {name}. Copy their unique simulation link below.", "ok")
    return redirect(url_for("admin.campaign", campaign_id=campaign_id))
