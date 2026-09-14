from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for

from app import db
from app.models import Resume
from app.services.resume_service import (
    create_resume,
    delete_resume,
    list_resumes,
    stored_resume_path,
    update_resume,
)

resumes_bp = Blueprint("resumes", __name__, url_prefix="/resumes")


@resumes_bp.get("")
def index():
    search = request.args.get("q", "")
    return render_template("resumes/list.html", resumes=list_resumes(search), search=search)


@resumes_bp.route("/new", methods=["GET", "POST"])
def create():
    errors = {}
    if request.method == "POST":
        resume, errors = create_resume(request.form, request.files.get("file"))
        if resume:
            flash("Resume version uploaded.", "success")
            return redirect(url_for("resumes.detail", resume_id=resume.id))
    return render_template(
        "resumes/create.html",
        errors=errors,
        form_data=request.form if request.method == "POST" else {},
    )


@resumes_bp.get("/<int:resume_id>")
def detail(resume_id: int):
    return render_template("resumes/detail.html", resume=db.get_or_404(Resume, resume_id))


@resumes_bp.route("/<int:resume_id>/edit", methods=["GET", "POST"])
def edit(resume_id: int):
    resume = db.get_or_404(Resume, resume_id)
    errors = {}
    if request.method == "POST":
        errors = update_resume(resume, request.form)
        if not errors:
            flash("Resume details updated.", "success")
            return redirect(url_for("resumes.detail", resume_id=resume.id))
    return render_template(
        "resumes/edit.html",
        resume=resume,
        errors=errors,
        form_data=request.form if request.method == "POST" else {},
    )


def deliver_resume(resume_id: int, as_attachment: bool):
    resume = db.get_or_404(Resume, resume_id)
    try:
        path = stored_resume_path(resume.stored_file_name)
    except ValueError:
        flash("The stored resume path is invalid.", "error")
        return redirect(url_for("resumes.detail", resume_id=resume.id))
    if not path.is_file():
        flash("The resume file is missing from local storage.", "error")
        return redirect(url_for("resumes.detail", resume_id=resume.id))
    return send_file(
        path,
        as_attachment=as_attachment,
        download_name=resume.original_file_name,
        conditional=True,
        max_age=0,
    )


@resumes_bp.get("/<int:resume_id>/open")
def open_file(resume_id: int):
    return deliver_resume(resume_id, as_attachment=False)


@resumes_bp.get("/<int:resume_id>/download")
def download(resume_id: int):
    return deliver_resume(resume_id, as_attachment=True)


@resumes_bp.post("/<int:resume_id>/delete")
def delete(resume_id: int):
    resume = db.get_or_404(Resume, resume_id)
    deleted, message = delete_resume(resume)
    flash(message, "success" if deleted else "error")
    if deleted:
        return redirect(url_for("resumes.index"))
    return redirect(url_for("resumes.detail", resume_id=resume.id))
