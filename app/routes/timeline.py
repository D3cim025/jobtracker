from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.models import Application, TimelineEvent, TimelineEventType
from app.services.timeline_service import (
    create_timeline_event,
    delete_timeline_event,
    update_timeline_event,
)

timeline_bp = Blueprint("timeline", __name__)


@timeline_bp.route("/applications/<int:application_id>/timeline/new", methods=["GET", "POST"])
def create(application_id: int):
    application = db.get_or_404(Application, application_id)
    errors = {}
    if request.method == "POST":
        event, errors = create_timeline_event(application, request.form)
        if event:
            flash("Timeline event added.", "success")
            return redirect(url_for("applications.detail", application_id=application.id))
    return render_template(
        "timeline/create.html",
        application=application,
        event=None,
        event_types=TimelineEventType,
        errors=errors,
        form_data=request.form if request.method == "POST" else {},
    )


@timeline_bp.route("/timeline/<int:event_id>/edit", methods=["GET", "POST"])
def edit(event_id: int):
    event = db.get_or_404(TimelineEvent, event_id)
    errors = {}
    if request.method == "POST":
        errors = update_timeline_event(event, request.form)
        if not errors:
            flash("Timeline event updated.", "success")
            return redirect(url_for("applications.detail", application_id=event.application_id))
    return render_template(
        "timeline/edit.html",
        application=event.application,
        event=event,
        event_types=TimelineEventType,
        errors=errors,
        form_data=request.form if request.method == "POST" else {},
    )


@timeline_bp.post("/timeline/<int:event_id>/delete")
def delete(event_id: int):
    event = db.get_or_404(TimelineEvent, event_id)
    application_id = event.application_id
    if delete_timeline_event(event):
        flash("Timeline event deleted.", "success")
    else:
        flash("The timeline event could not be deleted. No changes were made.", "error")
    return redirect(url_for("applications.detail", application_id=application_id))
