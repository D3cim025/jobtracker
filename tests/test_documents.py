from io import BytesIO
from pathlib import Path

import pytest

from app import create_app, db
from app.models import Application, Document, DocumentType, Resume


PDF_BYTES = b"%PDF-1.4\n% application document\n"


def add_application(**overrides):
    values = {"company_name": "Document Co", "position_title": "Python Engineer"}
    values.update(overrides)
    application = Application(**values)
    db.session.add(application)
    db.session.commit()
    return application


def document_form(**overrides):
    data = {
        "document_type": "Cover Letter",
        "notes": "Tailored for this company",
        "file": (BytesIO(PDF_BYTES), "Cover Letter.pdf", "application/pdf"),
    }
    data.update(overrides)
    return data


def add_document(upload_root: Path, application: Application, **overrides):
    values = {
        "document_type": DocumentType.COVER_LETTER,
        "file_path": str(Path(str(application.id)) / ("b" * 32 + ".pdf")),
        "original_file_name": "Cover Letter.pdf",
        "notes": "Company-specific letter",
    }
    values.update(overrides)
    document = Document(application=application, **values)
    db.session.add(document)
    db.session.commit()
    path = upload_root / "documents" / document.file_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PDF_BYTES)
    return document


def test_application_detail_has_document_empty_state_and_upload_action(app, client):
    with app.app_context():
        application_id = add_application().id
    body = client.get(f"/applications/{application_id}").get_data(as_text=True)
    assert "No application-specific documents attached" in body
    assert f"/applications/{application_id}/documents/new" in body


def test_upload_creates_application_owned_record_and_generated_file(app, client, tmp_path):
    with app.app_context():
        application_id = add_application().id
    response = client.post(
        f"/applications/{application_id}/documents/new",
        data=document_form(),
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/applications/{application_id}")
    with app.app_context():
        document = db.session.scalar(db.select(Document))
        assert document.application_id == application_id
        assert document.document_type is DocumentType.COVER_LETTER
        assert document.original_file_name == "Cover Letter.pdf"
        assert document.notes == "Tailored for this company"
        stored_path = Path(document.file_path)
        assert stored_path.parts[0] == str(application_id)
        assert stored_path.name != document.original_file_name
        assert len(stored_path.stem) == 32
        assert (tmp_path / "uploads" / "documents" / stored_path).read_bytes() == PDF_BYTES


@pytest.mark.parametrize("document_type", [member.value for member in DocumentType])
def test_all_document_categories_are_supported(app, client, document_type):
    with app.app_context():
        application_id = add_application(company_name=document_type).id
    response = client.post(
        f"/applications/{application_id}/documents/new",
        data=document_form(
            document_type=document_type,
            file=(BytesIO(b"plain text"), f"{document_type}.txt", "text/plain"),
        ),
    )
    assert response.status_code == 302
    with app.app_context():
        document = db.session.scalar(
            db.select(Document).where(Document.application_id == application_id)
        )
        assert document.document_type.value == document_type


def test_upload_requires_existing_application(client):
    response = client.post("/applications/9999/documents/new", data=document_form())
    assert response.status_code == 404


def test_upload_requires_valid_type_and_file(app, client):
    with app.app_context():
        application_id = add_application().id
    response = client.post(
        f"/applications/{application_id}/documents/new",
        data={"document_type": "Unknown", "notes": "preserve this"},
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Select a valid document type" in body
    assert "Choose a document file" in body
    assert "preserve this" in body
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Document.id))) == 0


@pytest.mark.parametrize(
    ("file_tuple", "message"),
    [
        ((BytesIO(b"program"), "payload.exe", "application/octet-stream"), "PDF, DOC"),
        ((BytesIO(b"not pdf"), "letter.pdf", "application/pdf"), "contents do not match"),
        ((BytesIO(PDF_BYTES), "letter.pdf", "text/html"), "file type is not allowed"),
        ((BytesIO(PDF_BYTES), "../letter.pdf", "application/pdf"), "file name is unsafe"),
    ],
)
def test_upload_rejects_unsafe_or_unsupported_files(app, client, file_tuple, message):
    with app.app_context():
        application_id = add_application().id
    response = client.post(
        f"/applications/{application_id}/documents/new",
        data=document_form(file=file_tuple),
    )
    assert message in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Document.id))) == 0


def test_upload_rejects_excessive_notes(app, client):
    with app.app_context():
        application_id = add_application().id
    response = client.post(
        f"/applications/{application_id}/documents/new",
        data=document_form(notes="x" * 5001),
    )
    assert "5,000 characters or fewer" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Document.id))) == 0


def test_application_detail_lists_only_its_documents(app, client, tmp_path):
    with app.app_context():
        first = add_application(company_name="First Co")
        second = add_application(company_name="Second Co")
        first_id, second_id = first.id, second.id
        add_document(tmp_path / "uploads", first, original_file_name="First Letter.pdf")
        add_document(
            tmp_path / "uploads",
            second,
            file_path=str(Path(str(second.id)) / ("c" * 32 + ".pdf")),
            original_file_name="Second Letter.pdf",
        )
    first_page = client.get(f"/applications/{first_id}").get_data(as_text=True)
    second_page = client.get(f"/applications/{second_id}").get_data(as_text=True)
    assert "First Letter.pdf" in first_page
    assert "Second Letter.pdf" not in first_page
    assert "Second Letter.pdf" in second_page
    assert "First Letter.pdf" not in second_page


def test_open_and_download_use_database_record_and_safe_headers(app, client, tmp_path):
    with app.app_context():
        application = add_application()
        document_id = add_document(tmp_path / "uploads", application).id
    opened = client.get(f"/documents/{document_id}/open")
    downloaded = client.get(f"/documents/{document_id}/download")
    assert opened.status_code == 200
    assert opened.data == PDF_BYTES
    assert "attachment" not in opened.headers["Content-Disposition"]
    assert downloaded.status_code == 200
    assert downloaded.data == PDF_BYTES
    assert "attachment" in downloaded.headers["Content-Disposition"]
    assert "Cover Letter.pdf" in downloaded.headers["Content-Disposition"]
    assert client.get("/documents/9999/download").status_code == 404


def test_missing_document_file_returns_to_owning_application(app, client, tmp_path):
    with app.app_context():
        application = add_application()
        application_id = application.id
        document = add_document(tmp_path / "uploads", application)
        (tmp_path / "uploads" / "documents" / document.file_path).unlink()
        document_id = document.id
    response = client.get(f"/documents/{document_id}/open", follow_redirects=True)
    assert response.status_code == 200
    assert "document file is missing" in response.get_data(as_text=True)
    assert f"Application #{application_id}" in response.get_data(as_text=True)


def test_tampered_document_path_cannot_escape_storage_root(app, client, tmp_path):
    outside = tmp_path / "private.pdf"
    outside.write_bytes(PDF_BYTES)
    with app.app_context():
        application = add_application()
        document = Document(
            application=application,
            document_type=DocumentType.OTHER,
            file_path="..\\..\\private.pdf",
            original_file_name="private.pdf",
        )
        db.session.add(document)
        db.session.commit()
        document_id = document.id
    response = client.get(f"/documents/{document_id}/open", follow_redirects=True)
    assert response.status_code == 200
    assert "stored document path is invalid" in response.get_data(as_text=True)
    assert outside.read_bytes() == PDF_BYTES


def test_delete_document_is_post_only_and_preserves_application(app, client, tmp_path):
    with app.app_context():
        application = add_application()
        application_id = application.id
        document = add_document(tmp_path / "uploads", application)
        document_id = document.id
        path = tmp_path / "uploads" / "documents" / document.file_path
    assert client.get(f"/documents/{document_id}/delete").status_code == 405
    response = client.post(f"/documents/{document_id}/delete", follow_redirects=True)
    assert "Document deleted" in response.get_data(as_text=True)
    assert not path.exists()
    with app.app_context():
        assert db.session.get(Document, document_id) is None
        assert db.session.get(Application, application_id) is not None


def test_deleting_one_document_preserves_other_files_and_resume_history(app, client, tmp_path):
    with app.app_context():
        resume = Resume(
            display_name="Historical Resume",
            version_name="v1",
            original_file_name="resume.pdf",
            stored_file_name="d" * 32 + ".pdf",
        )
        application = add_application(resume=resume)
        first = add_document(tmp_path / "uploads", application)
        second = add_document(
            tmp_path / "uploads",
            application,
            file_path=str(Path(str(application.id)) / ("e" * 32 + ".pdf")),
            original_file_name="Portfolio.pdf",
        )
        first_id, second_id, resume_id, application_id = (
            first.id,
            second.id,
            resume.id,
            application.id,
        )
        second_path = tmp_path / "uploads" / "documents" / second.file_path
    client.post(f"/documents/{first_id}/delete")
    with app.app_context():
        application = db.session.get(Application, application_id)
        assert application.resume_id == resume_id
        assert db.session.get(Document, second_id) is not None
        assert second_path.exists()


def test_deleting_application_removes_its_document_files_only(app, client, tmp_path):
    with app.app_context():
        first = add_application(company_name="Delete Me")
        second = add_application(company_name="Keep Me")
        first_document = add_document(tmp_path / "uploads", first)
        second_document = add_document(
            tmp_path / "uploads",
            second,
            file_path=str(Path(str(second.id)) / ("f" * 32 + ".pdf")),
        )
        first_path = tmp_path / "uploads" / "documents" / first_document.file_path
        second_path = tmp_path / "uploads" / "documents" / second_document.file_path
        first_id, second_id = first.id, second.id
    response = client.post(f"/applications/{first_id}/delete", follow_redirects=True)
    assert "Application deleted" in response.get_data(as_text=True)
    assert not first_path.exists()
    assert second_path.exists()
    with app.app_context():
        assert db.session.get(Application, first_id) is None
        assert db.session.get(Application, second_id) is not None


def test_document_upload_requires_csrf_when_enabled(tmp_path):
    protected_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "csrf-test-secret",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'csrf.db').as_posix()}",
            "UPLOAD_ROOT": str(tmp_path / "uploads"),
        }
    )
    response = protected_app.test_client().post(
        "/applications/1/documents/new", data=document_form()
    )
    assert response.status_code == 400
