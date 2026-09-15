from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.models import Application, ApplicationStatus, JobType, Priority, Resume, WorkSetup
from app.services.application_service import (
    delete_application,
    distinct_sources,
    list_applications,
    parse_application_form,
    save_application,
    update_application_choice,
)
from app.services.duplication_service import (
    create_duplicate,
    duplicate_matches,
    duplication_defaults,
    parse_duplication_form,
)
from app.services.reminder_service import reminder_groups

applications_bp = Blueprint("applications", __name__, url_prefix="/applications")


def form_context(**extra):
    context = {
        "statuses": ApplicationStatus,
        "priorities": Priority,
        "job_types": JobType,
        "work_setups": WorkSetup,
        "resumes": list(db.session.scalars(db.select(Resume).order_by(Resume.display_name, Resume.id))),
    }
    context.update(extra)
    return context


@applications_bp.get("")
def index():
    return render_template(
        "applications/list.html",
        applications=list_applications(request.args),
        sources=distinct_sources(),
        filters=request.args,
        **form_context(),
    )


@applications_bp.route("/new", methods=["GET", "POST"])
def create():
    errors = {}
    if request.method == "POST":
        values, errors = parse_application_form(request.form)
        if not errors:
            application = Application()
            if save_application(application, values):
                flash("Application created.", "success")
                return redirect(url_for("applications.detail", application_id=application.id))
            flash("The application could not be saved. Please try again.", "error")
    return render_template(
        "applications/create.html",
        application=None,
        errors=errors,
        form_data=request.form if request.method == "POST" else {},
        **form_context(),
    )


@applications_bp.get("/<int:application_id>")
def detail(application_id: int):
    application = db.get_or_404(Application, application_id)
    return render_template(
        "applications/detail.html",
        application=application,
        reminder_groups=reminder_groups(application.id),
        **form_context(),
    )


@applications_bp.route("/<int:application_id>/edit", methods=["GET", "POST"])
def edit(application_id: int):
    application = db.get_or_404(Application, application_id)
    errors = {}
    if request.method == "POST":
        values, errors = parse_application_form(request.form)
        if not errors:
            if save_application(application, values):
                flash("Application updated.", "success")
                return redirect(url_for("applications.detail", application_id=application.id))
            flash("The application could not be updated. Please try again.", "error")
    return render_template(
        "applications/edit.html",
        application=application,
        errors=errors,
        form_data=request.form if request.method == "POST" else {},
        **form_context(),
    )


@applications_bp.route("/<int:application_id>/apply-again", methods=["GET", "POST"])
def apply_again(application_id: int):
    source_application = db.get_or_404(Application, application_id)
    errors = {}
    duplicate_applications = []
    form_data = duplication_defaults(source_application)
    if request.method == "POST":
        form_data = request.form
        values, errors = parse_duplication_form(request.form, source_application)
        if not errors:
            duplicate_applications = duplicate_matches(values)
            if not duplicate_applications or request.form.get("confirm_duplicate") == "1":
                application = create_duplicate(values)
                if application is not None:
                    flash("New application created. The original was not changed.", "success")
                    return redirect(url_for("applications.detail", application_id=application.id))
                flash("The new application could not be saved. Please try again.", "error")
    return render_template(
        "applications/apply_again.html",
        source_application=source_application,
        errors=errors,
        form_data=form_data,
        duplicate_applications=duplicate_applications,
        **form_context(),
    )


@applications_bp.post("/<int:application_id>/delete")
def delete(application_id: int):
    application = db.get_or_404(Application, application_id)
    if not delete_application(application):
        flash("The application could not be deleted. No changes were made.", "error")
        return redirect(url_for("applications.detail", application_id=application_id))
    flash("Application deleted.", "success")
    return redirect(url_for("applications.index"))


@applications_bp.post("/<int:application_id>/status")
def update_status(application_id: int):
    application = db.get_or_404(Application, application_id)
    if not update_application_choice(application, "status", request.form.get("status", "")):
        flash("Select a valid status.", "error")
    else:
        flash("Status updated.", "success")
    return redirect(url_for("applications.detail", application_id=application_id))


@applications_bp.post("/<int:application_id>/priority")
def update_priority(application_id: int):
    application = db.get_or_404(Application, application_id)
    if not update_application_choice(application, "priority", request.form.get("priority", "")):
        flash("Select a valid priority.", "error")
    else:
        flash("Priority updated.", "success")
    return redirect(url_for("applications.detail", application_id=application_id))
