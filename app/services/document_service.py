from __future__ import annotations

from pathlib import Path
from typing import Mapping
from uuid import uuid4

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app import db
from app.models import Application, Document, DocumentType


ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".odt", ".txt", ".png", ".jpg", ".jpeg"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "application/octet-stream",
    "text/plain",
    "image/png",
    "image/jpeg",
}


def document_root() -> Path:
    root = (Path(current_app.config["UPLOAD_ROOT"]) / "documents").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def stored_document_path(file_path: str) -> Path:
    """Resolve a database storage path while confining it to application documents."""

    root = document_root()
    candidate = (root / file_path).resolve()
    if not candidate.is_relative_to(root) or candidate == root:
        raise ValueError("Unsafe document storage path.")
    return candidate


def _valid_signature(extension: str, header: bytes) -> bool:
    return (
        extension == ".txt"
        or (extension == ".pdf" and header.startswith(b"%PDF-"))
        or (extension == ".doc" and header.startswith(bytes.fromhex("D0CF11E0")))
        or (extension in {".docx", ".odt"} and header.startswith(b"PK"))
        or (extension == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n"))
        or (extension in {".jpg", ".jpeg"} and header.startswith(b"\xff\xd8\xff"))
    )


def validate_document_upload(upload: FileStorage | None) -> tuple[str | None, str | None]:
    if upload is None or not upload.filename:
        return None, "Choose a document file."
    original_name = upload.filename.strip()
    if len(original_name) > 255:
        return None, "The file name must be 255 characters or fewer."
    if Path(original_name).name != original_name or "/" in original_name or "\\" in original_name:
        return None, "The file name is unsafe. Rename the file and try again."
    safe_name = secure_filename(original_name)
    extension = Path(safe_name).suffix.lower()
    if not safe_name or extension not in ALLOWED_EXTENSIONS:
        return None, "Upload a PDF, DOC, DOCX, ODT, TXT, PNG, or JPEG file."
    if upload.mimetype not in ALLOWED_MIME_TYPES:
        return None, "The selected file type is not allowed."
    try:
        header = upload.stream.read(8)
        upload.stream.seek(0)
    except (OSError, ValueError):
        return None, "The selected file could not be read."
    if not _valid_signature(extension, header):
        return None, "The file contents do not match the file extension."
    return extension, None


def parse_document_form(form: Mapping[str, str]) -> tuple[DocumentType | None, str | None, dict[str, str]]:
    errors: dict[str, str] = {}
    try:
        document_type = DocumentType(form.get("document_type", ""))
    except ValueError:
        document_type = None
        errors["document_type"] = "Select a valid document type."
    notes = form.get("notes", "").strip() or None
    if notes and len(notes) > 5000:
        errors["notes"] = "Notes must be 5,000 characters or fewer."
    return document_type, notes, errors


def create_document(
    application: Application, form: Mapping[str, str], upload: FileStorage | None
) -> tuple[Document | None, dict[str, str]]:
    document_type, notes, errors = parse_document_form(form)
    extension, upload_error = validate_document_upload(upload)
    if upload_error:
        errors["file"] = upload_error
    if errors:
        return None, errors

    assert document_type and upload and upload.filename and extension
    relative_path = Path(str(application.id)) / f"{uuid4().hex}{extension}"
    destination: Path | None = None
    try:
        destination = stored_document_path(str(relative_path))
        destination.parent.mkdir(parents=True, exist_ok=True)
        upload.save(destination)
        document = Document(
            application=application,
            document_type=document_type,
            file_path=str(relative_path),
            original_file_name=upload.filename.strip(),
            notes=notes,
        )
        db.session.add(document)
        db.session.commit()
    except (OSError, SQLAlchemyError, ValueError):
        db.session.rollback()
        try:
            if destination is not None:
                destination.unlink(missing_ok=True)
                destination.parent.rmdir()
        except OSError:
            pass
        return None, {"file": "The document could not be saved. Please try again."}
    return document, {}


def _quarantine_paths(documents: list[Document]) -> list[tuple[Path, Path]]:
    moved: list[tuple[Path, Path]] = []
    try:
        for document in documents:
            path = stored_document_path(document.file_path)
            quarantine = path.with_suffix(path.suffix + ".deleting")
            if quarantine.exists():
                raise OSError("A document deletion is already pending.")
            if path.exists():
                path.replace(quarantine)
                moved.append((path, quarantine))
    except (OSError, ValueError):
        restore_quarantined_files(moved)
        raise
    return moved


def restore_quarantined_files(moved: list[tuple[Path, Path]]) -> None:
    for path, quarantine in reversed(moved):
        if quarantine.exists() and not path.exists():
            quarantine.replace(path)


def finalize_quarantined_files(moved: list[tuple[Path, Path]]) -> None:
    for path, quarantine in moved:
        try:
            quarantine.unlink(missing_ok=True)
            path.parent.rmdir()
        except OSError:
            pass


def prepare_application_document_deletion(application: Application) -> list[tuple[Path, Path]]:
    return _quarantine_paths(list(application.documents))


def delete_document(document: Document) -> tuple[bool, str]:
    try:
        moved = _quarantine_paths([document])
    except (OSError, ValueError):
        return False, "The stored document path is invalid or inaccessible. No changes were made."
    try:
        db.session.delete(document)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        try:
            restore_quarantined_files(moved)
        except OSError:
            pass
        return False, "The document could not be deleted. No changes were made."
    finalize_quarantined_files(moved)
    return True, "Document deleted."
