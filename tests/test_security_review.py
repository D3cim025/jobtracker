from io import BytesIO

import pytest
from werkzeug.datastructures import FileStorage

from app import create_app, db, installation_secret
from app.models import Application, ApplicationStatus, TimelineEvent, TimelineEventType
from app.services.document_service import create_document
from app.services.resume_service import create_resume


def test_installation_secret_is_random_persistent_and_not_default(tmp_path):
    first = installation_secret(str(tmp_path))
    second = installation_secret(str(tmp_path))
    assert first == second
    assert len(first) == 64
    assert first != "local-development-only-change-me"


def test_security_headers_cover_html_health_and_missing_pages(client):
    for path in ("/", "/health", "/missing"):
        response = client.get(path)
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["Cache-Control"] == "no-store"


def test_edit_status_creates_exactly_one_history_event(app, client):
    with app.app_context():
        application = Application(company_name="Acme", position_title="Engineer")
        db.session.add(application)
        db.session.commit()
        application_id = application.id
    response = client.post(
        f"/applications/{application_id}/edit",
        data={"company_name": "Acme", "position_title": "Engineer", "status": "Interview"},
    )
    assert response.status_code == 302
    with app.app_context():
        application = db.session.get(Application, application_id)
        events = list(db.session.scalars(db.select(TimelineEvent)))
        assert application.status is ApplicationStatus.INTERVIEW
        assert len(events) == 1
        assert events[0].event_type is TimelineEventType.STATUS_CHANGED
        assert "Saved to Interview" in events[0].notes


@pytest.mark.parametrize("job_url", ["http://[", "https://[]"])
def test_malformed_urls_return_validation_errors_not_500(app, client, job_url):
    response = client.post(
        "/applications/new",
        data={"company_name": "Acme", "position_title": "Engineer", "job_url": job_url},
    )
    assert response.status_code == 200
    assert "complete http:// or https:// URL" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Application.id))) == 0


@pytest.mark.parametrize("amount", ["Infinity", "1e1000", "10000000000", "1.001"])
def test_nonfinite_oversized_or_overprecision_salary_is_rejected(app, client, amount):
    response = client.post(
        "/applications/new",
        data={"company_name": "Acme", "position_title": "Engineer", "salary_min": amount},
    )
    assert response.status_code == 200
    assert "at most two decimals" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Application.id))) == 0


def test_oversized_resume_reference_is_rejected_without_database_overflow(app, client):
    response = client.post(
        "/applications/new",
        data={"company_name": "Acme", "position_title": "Engineer", "resume_id": str(2**80)},
    )
    assert response.status_code == 200
    assert "Select a valid resume" in response.get_data(as_text=True)


def test_application_and_resume_long_text_is_bounded(app, client):
    application_response = client.post(
        "/applications/new",
        data={"company_name": "Acme", "position_title": "Engineer", "notes": "x" * 5001},
    )
    resume_response = client.post(
        "/resumes/new",
        data={"display_name": "Resume", "version_name": "v1", "description": "x" * 5001},
    )
    assert "5,000 characters" in application_response.get_data(as_text=True)
    assert "5,000 characters" in resume_response.get_data(as_text=True)


class FailingUpload(FileStorage):
    def save(self, dst, buffer_size=16384):
        raise OSError("simulated disk failure")


def test_resume_and_document_io_failures_are_safe_validation_results(app):
    with app.app_context():
        application = Application(company_name="Acme", position_title="Engineer")
        db.session.add(application)
        db.session.commit()
        resume, resume_errors = create_resume(
            {"display_name": "Resume", "version_name": "v1"},
            FailingUpload(stream=BytesIO(b"%PDF-test"), filename="resume.pdf", content_type="application/pdf"),
        )
        document, document_errors = create_document(
            application,
            {"document_type": "Other"},
            FailingUpload(stream=BytesIO(b"%PDF-test"), filename="file.pdf", content_type="application/pdf"),
        )
        assert resume is None and "could not be saved" in resume_errors["file"]
        assert document is None and "could not be saved" in document_errors["file"]
