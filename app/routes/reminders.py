from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app import db
from app.models import Application, Reminder, ReminderType
from app.services.reminder_service import (
    create_reminder,
    delete_reminder,
    reminder_groups,
    set_reminder_completion,
    update_reminder,
)

reminders_bp = Blueprint("reminders", __name__)


def application_reminder_or_404(application_id: int, reminder_id: int) -> tuple[Application, Reminder]:
    application = db.get_or_404(Application, application_id)
    reminder = db.get_or_404(Reminder, reminder_id)
    if reminder.application_id != application.id:
        abort(404)
    return application, reminder


@reminders_bp.get("/reminders")
def index():
    return render_template("reminders/list.html", groups=reminder_groups())


@reminders_bp.route("/applications/<int:application_id>/reminders/new", methods=["GET", "POST"])
def create(application_id: int):
    application = db.get_or_404(Application, application_id)
    errors = {}
    if request.method == "POST":
        reminder, errors = create_reminder(application, request.form)
        if reminder:
            flash("Reminder created.", "success")
            return redirect(url_for("applications.detail", application_id=application.id))
    return render_template(
        "reminders/create.html",
        application=application,
        reminder=None,
        reminder_types=ReminderType,
        errors=errors,
        form_data=request.form if request.method == "POST" else {},
    )


@reminders_bp.route(
    "/applications/<int:application_id>/reminders/<int:reminder_id>/edit",
    methods=["GET", "POST"],
)
def edit(application_id: int, reminder_id: int):
    application, reminder = application_reminder_or_404(application_id, reminder_id)
    errors = {}
    if request.method == "POST":
        errors = update_reminder(reminder, request.form)
        if not errors:
            flash("Reminder updated.", "success")
            return redirect(url_for("applications.detail", application_id=application.id))
    return render_template(
        "reminders/edit.html",
        application=application,
        reminder=reminder,
        reminder_types=ReminderType,
        errors=errors,
        form_data=request.form if request.method == "POST" else {},
    )


@reminders_bp.post(
    "/applications/<int:application_id>/reminders/<int:reminder_id>/completion"
)
def completion(application_id: int, reminder_id: int):
    application, reminder = application_reminder_or_404(application_id, reminder_id)
    raw_completed = request.form.get("completed", "")
    if raw_completed not in {"0", "1"}:
        flash("The reminder completion value is invalid.", "error")
    elif set_reminder_completion(reminder, raw_completed == "1"):
        flash("Reminder marked completed." if raw_completed == "1" else "Reminder reopened.", "success")
    else:
        flash("The reminder could not be updated. No changes were made.", "error")
    return redirect(url_for("applications.detail", application_id=application.id))


@reminders_bp.post(
    "/applications/<int:application_id>/reminders/<int:reminder_id>/delete"
)
def delete(application_id: int, reminder_id: int):
    application, reminder = application_reminder_or_404(application_id, reminder_id)
    if delete_reminder(reminder):
        flash("Reminder deleted.", "success")
    else:
        flash("The reminder could not be deleted. No changes were made.", "error")
    return redirect(url_for("applications.detail", application_id=application.id))
