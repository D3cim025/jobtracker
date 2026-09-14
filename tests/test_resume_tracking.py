from hashlib import sha256
from io import BytesIO

import pytest

from app import db
from app.models import Application, Document, DocumentType, Resume
from tests.test_applications import valid_form


PDF_V1 = b"%PDF-1.4\n% exact version one\n"
PDF_V2 = b"%PDF-1.4\n% exact version two\n"


def add_resume(version: str, marker: str, content: bytes = PDF_V1) -> Resume:
    resume = Resume(
        display_name="Software Engineer Resume",
        version_name=version,
        target_role="Software Engineering",
        original_file_name=f"Software Engineer Resume {version}.pdf",
        stored_file_name=f"{marker * 32}.pdf",
        file_hash=sha256(content).hexdigest(),
    )
    db.session.add(resume)
    db.session.commit()
    return resume


def add_application(company: str, resume: Resume | None = None) -> Application:
    application = Application(
        company_name=company,
        position_title="Backend Engineer",
        resume=resume,
    )
    db.session.add(application)
    db.session.commit()
    return application


def test_assign_resume_during_application_creation(app, client):
    with app.app_context():
        resume_id = add_resume("v1", "1").id
    response = client.post(
        "/applications/new",
        data=valid_form(resume_id=str(resume_id)),
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Exact resume used" in body
    assert "Software Engineer Resume" in body
    assert "v1" in body
    assert f"Resume version ID</dt><dd>#{resume_id}" in body
    with app.app_context():
        application = db.session.scalar(db.select(Application))
        assert application.resume_id == resume_id


def test_change_selected_resume_on_existing_application(app, client):
    with app.app_context():
        first = add_resume("v1", "1")
        second = add_resume("v2", "2", PDF_V2)
        application = add_application("Change Co", first)
        application_id, first_id, second_id = application.id, first.id, second.id
    response = client.post(
        f"/applications/{application_id}/edit",
        data=valid_form(company_name="Change Co", resume_id=str(second_id)),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "v2" in response.get_data(as_text=True)
    with app.app_context():
        application = db.session.get(Application, application_id)
        assert application.resume_id == second_id
        assert db.session.get(Resume, first_id) is not None


def test_resume_can_be_explicitly_cleared_from_application(app, client):
    with app.app_context():
        resume = add_resume("v1", "1")
        application_id = add_application("Clear Co", resume).id
    response = client.post(
        f"/applications/{application_id}/edit",
        data=valid_form(company_name="Clear Co", resume_id=""),
        follow_redirects=True,
    )
    assert "No Resume Library version is recorded" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Application, application_id).resume_id is None


def test_uploading_newer_resume_does_not_change_historical_association(app, client):
    with app.app_context():
        first = add_resume("v1", "1")
        first_id = first.id
        application_id = add_application("Historical Co", first).id
    response = client.post(
        "/resumes/new",
        data={
            "display_name": "Software Engineer Resume",
            "version_name": "v2",
            "target_role": "Software Engineering",
            "description": "Newer edition",
            "file": (BytesIO(PDF_V2), "Software Engineer Resume v2.pdf", "application/pdf"),
        },
    )
    assert response.status_code == 302
    with app.app_context():
        application = db.session.get(Application, application_id)
        assert application.resume_id == first_id
        assert application.resume.version_name == "v1"
        assert db.session.scalar(db.select(db.func.count(Resume.id))) == 2


def test_multiple_applications_can_share_exact_resume_version(app, client):
    with app.app_context():
        resume = add_resume("v3", "3")
        resume_id = resume.id
        first_id = add_application("Alpha Co", resume).id
        second_id = add_application("Beta Co", resume).id
    page = client.get(f"/resumes/{resume_id}").get_data(as_text=True)
    assert "Alpha Co" in page
    assert "Beta Co" in page
    assert f"/applications/{first_id}" in page
    assert f"/applications/{second_id}" in page
    with app.app_context():
        assert len(db.session.get(Resume, resume_id).applications) == 2


def test_usage_history_contains_only_applications_for_that_version(app, client):
    with app.app_context():
        first = add_resume("v1", "1")
        second = add_resume("v2", "2", PDF_V2)
        first_id = first.id
        add_application("Uses First", first)
        add_application("Uses Second", second)
        add_application("Uses None")
    page = client.get(f"/resumes/{first_id}").get_data(as_text=True)
    assert "These applications reference this exact file version" in page
    assert "Uses First" in page
    assert "Uses Second" not in page
    assert "Uses None" not in page


@pytest.mark.parametrize("resume_id", ["not-a-number", "999999"])
def test_invalid_or_missing_resume_reference_is_rejected_without_creating_application(
    app, client, resume_id
):
    response = client.post(
        "/applications/new", data=valid_form(resume_id=resume_id)
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "valid resume" in body or "no longer exists" in body
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Application.id))) == 0


def test_missing_resume_reference_does_not_replace_current_selection(app, client):
    with app.app_context():
        resume = add_resume("v1", "1")
        resume_id = resume.id
        application_id = add_application("Protected Co", resume).id
    response = client.post(
        f"/applications/{application_id}/edit",
        data=valid_form(company_name="Attempted Change", resume_id="987654"),
    )
    assert response.status_code == 200
    with app.app_context():
        application = db.session.get(Application, application_id)
        assert application.company_name == "Protected Co"
        assert application.resume_id == resume_id


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("original_file_name", "replacement.pdf"),
        ("stored_file_name", "f" * 32 + ".pdf"),
        ("file_hash", sha256(b"replacement").hexdigest()),
    ],
)
def test_persisted_resume_file_identity_is_immutable(app, field, replacement):
    with app.app_context():
        resume = add_resume("v1", "1")
        resume_id = resume.id
        original = getattr(resume, field)
        setattr(resume, field, replacement)
        with pytest.raises(ValueError, match="Upload a new resume version"):
            db.session.commit()
        db.session.rollback()
        assert getattr(db.session.get(Resume, resume_id), field) == original


def test_editing_resume_metadata_preserves_file_identity_and_application_link(app, client):
    with app.app_context():
        resume = add_resume("v1", "1")
        resume_id = resume.id
        stored_name, original_name, digest = (
            resume.stored_file_name,
            resume.original_file_name,
            resume.file_hash,
        )
        application_id = add_application("Metadata Co", resume).id
    response = client.post(
        f"/resumes/{resume_id}/edit",
        data={
            "display_name": "Renamed Display Resume",
            "version_name": "v1 final",
            "target_role": "Platform Engineer",
            "description": "Metadata only",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        resume = db.session.get(Resume, resume_id)
        application = db.session.get(Application, application_id)
        assert resume.stored_file_name == stored_name
        assert resume.original_file_name == original_name
        assert resume.file_hash == digest
        assert application.resume_id == resume_id
        assert application.resume.display_name == "Renamed Display Resume"


def test_application_document_named_resume_does_not_change_library_association(app):
    with app.app_context():
        library_resume = add_resume("v1", "1")
        resume_id = library_resume.id
        application = add_application("Document Co", library_resume)
        application_id = application.id
        document = Document(
            application=application,
            document_type=DocumentType.RESUME,
            file_path=f"{application.id}/{'d' * 32}.pdf",
            original_file_name="application-copy.pdf",
        )
        db.session.add(document)
        db.session.commit()
        assert document.application_id == application_id
        assert db.session.get(Application, application_id).resume_id == resume_id
        assert db.session.scalar(db.select(db.func.count(Resume.id))) == 1


def test_changing_resume_preserves_application_documents(app, client):
    with app.app_context():
        first = add_resume("v1", "1")
        second = add_resume("v2", "2", PDF_V2)
        application = add_application("Documents Stay", first)
        application_id, second_id = application.id, second.id
        document = Document(
            application=application,
            document_type=DocumentType.COVER_LETTER,
            file_path=f"{application.id}/{'e' * 32}.pdf",
            original_file_name="cover-letter.pdf",
        )
        db.session.add(document)
        db.session.commit()
        document_id = document.id
    response = client.post(
        f"/applications/{application_id}/edit",
        data=valid_form(company_name="Documents Stay", resume_id=str(second_id)),
    )
    assert response.status_code == 302
    with app.app_context():
        application = db.session.get(Application, application_id)
        assert application.resume_id == second_id
        assert db.session.get(Document, document_id).application_id == application_id
