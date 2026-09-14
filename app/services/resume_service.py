from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping
from uuid import uuid4

from flask import current_app
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app import db
from app.models import Resume


ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".odt", ".txt"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "application/octet-stream",
    "text/plain",
}


def resume_root() -> Path:
    root = (Path(current_app.config["UPLOAD_ROOT"]) / "resumes").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def stored_resume_path(stored_file_name: str) -> Path:
    """Resolve a generated storage name and reject paths outside the resume root."""

    root = resume_root()
    candidate = (root / stored_file_name).resolve()
    if candidate.parent != root:
        raise ValueError("Unsafe resume storage path.")
    return candidate


def list_resumes(search: str = "") -> list[Resume]:
    statement = select(Resume)
    search = search.strip()
    if search:
        pattern = f"%{search}%"
        statement = statement.where(
            or_(
                Resume.display_name.ilike(pattern),
                Resume.version_name.ilike(pattern),
                Resume.target_role.ilike(pattern),
                Resume.description.ilike(pattern),
                Resume.original_file_name.ilike(pattern),
            )
        )
    return list(db.session.scalars(statement.order_by(Resume.updated_at.desc(), Resume.id.desc())))


def parse_resume_metadata(form: Mapping[str, str]) -> tuple[dict, dict[str, str]]:
    errors: dict[str, str] = {}
    values: dict[str, str | None] = {}
    limits = {"display_name": 200, "version_name": 100, "target_role": 200}
    for field, maximum in limits.items():
        value = form.get(field, "").strip()
        if field in {"display_name", "version_name"} and not value:
            errors[field] = f"{field.replace('_', ' ').title()} is required."
        elif len(value) > maximum:
            errors[field] = f"Must be {maximum} characters or fewer."
        values[field] = value or None
    description = form.get("description", "").strip() or None
    if description and len(description) > 5000:
        errors["description"] = "Description must be 5,000 characters or fewer."
    values["description"] = description
    return values, errors


def validate_upload(upload: FileStorage | None) -> tuple[str | None, str | None]:
    if upload is None or not upload.filename:
        return None, "Choose a resume file."
    original_name = upload.filename.strip()
    if len(original_name) > 255:
        return None, "The file name must be 255 characters or fewer."
    if Path(original_name).name != original_name or "/" in original_name or "\\" in original_name:
        return None, "The file name is unsafe. Rename the file and try again."
    safe_name = secure_filename(original_name)
    extension = Path(safe_name).suffix.lower()
    if not safe_name or extension not in ALLOWED_EXTENSIONS:
        return None, "Upload a PDF, DOC, DOCX, ODT, or TXT file."
    if upload.mimetype not in ALLOWED_MIME_TYPES:
        return None, "The selected file type does not match an allowed resume format."

    try:
        header = upload.stream.read(8)
        upload.stream.seek(0)
    except (OSError, ValueError):
        return None, "The selected file could not be read."
    signature_valid = (
        extension == ".txt"
        or (extension == ".pdf" and header.startswith(b"%PDF-"))
        or (extension == ".doc" and header.startswith(bytes.fromhex("D0CF11E0")))
        or (extension in {".docx", ".odt"} and header.startswith(b"PK"))
    )
    if not signature_valid:
        return None, "The file contents do not match the file extension."
    return extension, None


def create_resume(form: Mapping[str, str], upload: FileStorage | None) -> tuple[Resume | None, dict[str, str]]:
    values, errors = parse_resume_metadata(form)
    extension, upload_error = validate_upload(upload)
    if upload_error:
        errors["file"] = upload_error
    if errors:
        return None, errors

    assert upload is not None and upload.filename and extension
    stored_name = f"{uuid4().hex}{extension}"
    destination: Path | None = None
    try:
        destination = stored_resume_path(stored_name)
        upload.save(destination)
        file_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
        resume = Resume(
            **values,
            original_file_name=upload.filename.strip(),
            stored_file_name=stored_name,
            file_hash=file_hash,
        )
        db.session.add(resume)
        db.session.commit()
    except (OSError, SQLAlchemyError, ValueError):
        db.session.rollback()
        try:
            if destination is not None:
                destination.unlink(missing_ok=True)
        except OSError:
            pass
        return None, {"file": "The resume could not be saved. Please try again."}
    return resume, {}


def update_resume(resume: Resume, form: Mapping[str, str]) -> dict[str, str]:
    values, errors = parse_resume_metadata(form)
    if errors:
        return errors
    for field, value in values.items():
        setattr(resume, field, value)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return {"form": "The resume could not be updated. Please try again."}
    return {}


def delete_resume(resume: Resume) -> tuple[bool, str]:
    if resume.applications:
        return False, "This resume is used by an application and cannot be deleted."

    try:
        path = stored_resume_path(resume.stored_file_name)
    except ValueError:
        return False, "The stored resume path is invalid. No changes were made."

    quarantine = path.with_suffix(path.suffix + ".deleting")
    try:
        if quarantine.exists():
            raise OSError("A resume deletion is already pending.")
        if path.exists():
            path.replace(quarantine)
        db.session.delete(resume)
        db.session.commit()
    except (OSError, SQLAlchemyError):
        db.session.rollback()
        if quarantine.exists() and not path.exists():
            quarantine.replace(path)
        return False, "The resume could not be deleted. No changes were made."

    try:
        quarantine.unlink(missing_ok=True)
    except OSError:
        # The inaccessible quarantine file is no longer addressable through the app.
        pass
    return True, "Resume deleted."
