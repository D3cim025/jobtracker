from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for

from app import db
from app.models import Application, Document, DocumentType
from app.services.document_service import create_document, delete_document, stored_document_path

documents_bp = Blueprint("documents", __name__)


@documents_bp.route("/applications/<int:application_id>/documents/new", methods=["GET", "POST"])
def create(application_id: int):
    application = db.get_or_404(Application, application_id)
    errors = {}
    if request.method == "POST":
        document, errors = create_document(application, request.form, request.files.get("file"))
        if document:
            flash("Document uploaded.", "success")
            return redirect(url_for("applications.detail", application_id=application.id))
    return render_template(
        "documents/create.html",
        application=application,
        document_types=DocumentType,
        errors=errors,
        form_data=request.form if request.method == "POST" else {},
    )


def deliver_document(document_id: int, as_attachment: bool):
    document = db.get_or_404(Document, document_id)
    try:
        path = stored_document_path(document.file_path)
    except ValueError:
        flash("The stored document path is invalid.", "error")
        return redirect(url_for("applications.detail", application_id=document.application_id))
    if not path.is_file():
        flash("The document file is missing from local storage.", "error")
        return redirect(url_for("applications.detail", application_id=document.application_id))
    return send_file(
        path,
        as_attachment=as_attachment,
        download_name=document.original_file_name,
        conditional=True,
        max_age=0,
    )


@documents_bp.get("/documents/<int:document_id>/open")
def open_file(document_id: int):
    return deliver_document(document_id, as_attachment=False)


@documents_bp.get("/documents/<int:document_id>/download")
def download(document_id: int):
    return deliver_document(document_id, as_attachment=True)


@documents_bp.post("/documents/<int:document_id>/delete")
def delete(document_id: int):
    document = db.get_or_404(Document, document_id)
    application_id = document.application_id
    deleted, message = delete_document(document)
    flash(message, "success" if deleted else "error")
    return redirect(url_for("applications.detail", application_id=application_id))
