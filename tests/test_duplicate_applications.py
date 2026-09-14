from datetime import date, datetime
from decimal import Decimal

from app import create_app, db
from app.models import (
    Application, ApplicationStatus, Document, DocumentType, JobType, Priority,
    Reminder, ReminderType, Resume, TimelineEvent, TimelineEventType, WorkSetup,
)


def add_source():
    resume = Resume(
        display_name="Backend Resume", original_file_name="resume.pdf",
        stored_file_name="resume-immutable.pdf", version_name="v3",
    )
    source = Application(
        company_name="Original Co", position_title="Platform Engineer",
        job_type=JobType.CONTRACT, work_setup=WorkSetup.HYBRID, location="Manila",
        salary_min=Decimal("70000"), salary_max=Decimal("90000"), currency="USD",
        priority=Priority.HIGH, source="Referral", resume=resume,
        job_url="https://example.com/old", date_found=date(2026, 1, 2),
        date_applied=date(2026, 1, 3), status=ApplicationStatus.INTERVIEW,
        contact_name="Recruiter", contact_email="person@example.com",
        contact_phone="123", notes="Reusable only by choice",
    )
    source.documents.append(Document(
        document_type=DocumentType.COVER_LETTER, file_path="1/letter.pdf",
        original_file_name="letter.pdf",
    ))
    source.timeline_events.append(TimelineEvent(
        event_type=TimelineEventType.INTERVIEW_SCHEDULED,
        event_date=datetime(2026, 1, 4, 10), notes="Old event",
    ))
    source.reminders.append(Reminder(
        reminder_type=ReminderType.FOLLOW_UP,
        reminder_date=datetime(2026, 1, 5, 10), notes="Old reminder",
    ))
    db.session.add(source)
    db.session.commit()
    return source


def duplicate_form(**overrides):
    values = {
        "company_name": "New Co", "position_title": "Platform Engineer",
        "job_type": "Contract", "work_setup": "Hybrid", "location": "Manila",
        "salary_min": "70000", "salary_max": "90000", "currency": "USD",
        "priority": "High", "source": "Referral", "resume_id": "", "notes": "",
    }
    values.update(overrides)
    return values


def test_apply_again_actions_appear_in_detail_and_list(app, client):
    with app.app_context():
        source_id = add_source().id
    assert f"/applications/{source_id}/apply-again" in client.get(f"/applications/{source_id}").get_data(as_text=True)
    assert f"/applications/{source_id}/apply-again" in client.get("/applications").get_data(as_text=True)


def test_review_prefills_only_reusable_information(app, client):
    with app.app_context():
        source = add_source()
        source_id, resume_id = source.id, source.resume_id
    body = client.get(f"/applications/{source_id}/apply-again").get_data(as_text=True)
    assert 'value="Platform Engineer"' in body
    assert 'value="Original Co"' not in body
    assert f'<option value="{resume_id}" selected' in body
    assert "Status is Saved" in body
    assert "Timeline, reminders, and application documents start empty" in body


def test_apply_again_creates_new_record_with_reusable_fields_and_safe_defaults(app, client):
    with app.app_context():
        source = add_source()
        source_id, resume_id = source.id, source.resume_id
        original_snapshot = (source.company_name, source.status, source.date_applied, len(source.documents))
    response = client.post(
        f"/applications/{source_id}/apply-again",
        data=duplicate_form(resume_id=str(resume_id)), follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        records = list(db.session.scalars(db.select(Application).order_by(Application.id)))
        original, duplicate = records
        assert duplicate.id != original.id
        assert (original.company_name, original.status, original.date_applied, len(original.documents)) == original_snapshot
        assert (duplicate.position_title, duplicate.job_type, duplicate.work_setup) == ("Platform Engineer", JobType.CONTRACT, WorkSetup.HYBRID)
        assert (duplicate.location, duplicate.salary_min, duplicate.salary_max) == ("Manila", Decimal("70000"), Decimal("90000"))
        assert (duplicate.currency, duplicate.priority, duplicate.source) == ("USD", Priority.HIGH, "Referral")
        assert duplicate.resume_id == resume_id
        assert duplicate.company_name == "New Co"
        assert duplicate.status is ApplicationStatus.SAVED
        assert duplicate.date_found == date.today()
        assert duplicate.date_applied is None
        assert duplicate.job_url is None
        assert duplicate.contact_name is None and duplicate.contact_email is None and duplicate.contact_phone is None
        assert duplicate.notes is None
        assert duplicate.documents == [] and duplicate.timeline_events == [] and duplicate.reminders == []
        assert db.session.scalar(db.select(db.func.count(Resume.id))) == 1


def test_crafted_forbidden_fields_are_ignored(app, client):
    with app.app_context():
        source_id = add_source().id
    data = duplicate_form(status="Offer", date_found="2000-01-01", date_applied="2000-01-02",
                          job_url="https://evil.example", contact_name="Copied", contact_email="x@y.com")
    client.post(f"/applications/{source_id}/apply-again", data=data)
    with app.app_context():
        duplicate = db.session.scalar(db.select(Application).where(Application.id != source_id))
        assert duplicate.status is ApplicationStatus.SAVED
        assert duplicate.date_found == date.today() and duplicate.date_applied is None
        assert duplicate.job_url is None and duplicate.contact_name is None and duplicate.contact_email is None


def test_resume_can_be_reassigned_or_removed(app, client):
    with app.app_context():
        source = add_source()
        other = Resume(display_name="Other", original_file_name="other.pdf", stored_file_name="other.pdf", version_name="v1")
        db.session.add(other); db.session.commit()
        source_id, other_id = source.id, other.id
    client.post(f"/applications/{source_id}/apply-again", data=duplicate_form(company_name="Second", resume_id=str(other_id)))
    client.post(f"/applications/{source_id}/apply-again", data=duplicate_form(company_name="Third", resume_id=""))
    with app.app_context():
        second = db.session.scalar(db.select(Application).where(Application.company_name == "Second"))
        third = db.session.scalar(db.select(Application).where(Application.company_name == "Third"))
        assert second.resume_id == other_id
        assert third.resume_id is None


def test_original_notes_require_explicit_reuse(app, client):
    with app.app_context():
        source_id = add_source().id
    client.post(f"/applications/{source_id}/apply-again", data=duplicate_form(company_name="No Notes"))
    client.post(f"/applications/{source_id}/apply-again", data=duplicate_form(company_name="With Notes", reuse_notes="1"))
    with app.app_context():
        assert db.session.scalar(db.select(Application).where(Application.company_name == "No Notes")).notes is None
        assert db.session.scalar(db.select(Application).where(Application.company_name == "With Notes")).notes == "Reusable only by choice"


def test_custom_new_notes_are_supported(app, client):
    with app.app_context():
        source_id = add_source().id
    client.post(f"/applications/{source_id}/apply-again", data=duplicate_form(notes="Fresh notes"))
    with app.app_context():
        duplicate = db.session.scalar(db.select(Application).where(Application.company_name == "New Co"))
        assert duplicate.notes == "Fresh notes"


def test_duplicate_warning_is_non_blocking_confirmation(app, client):
    with app.app_context():
        source_id = add_source().id
    data = duplicate_form(company_name="original co", position_title="platform engineer")
    warning = client.post(f"/applications/{source_id}/apply-again", data=data)
    assert warning.status_code == 200
    assert "Possible duplicate" in warning.get_data(as_text=True)
    assert "Create anyway" in warning.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Application.id))) == 1
    data["confirm_duplicate"] = "1"
    assert client.post(f"/applications/{source_id}/apply-again", data=data).status_code == 302
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Application.id))) == 2


def test_validation_rejects_missing_invalid_and_stale_resume(app, client):
    with app.app_context():
        source_id = add_source().id
    response = client.post(f"/applications/{source_id}/apply-again", data=duplicate_form(company_name="", job_type="Wrong", resume_id="9999"))
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Company is required" in body and "Select a valid option" in body
    assert "selected resume no longer exists" in body
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Application.id))) == 1


def test_apply_again_missing_source_returns_404(client):
    assert client.get("/applications/999/apply-again").status_code == 404
    assert client.post("/applications/999/apply-again", data=duplicate_form()).status_code == 404


def test_csrf_protects_apply_again_creation(tmp_path):
    app = create_app({
        "TESTING": True, "SECRET_KEY": "csrf-test", "WTF_CSRF_ENABLED": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'csrf.db').as_posix()}",
        "UPLOAD_ROOT": str(tmp_path / "uploads"),
    })
    with app.app_context():
        db.create_all(); source_id = add_source().id
    response = app.test_client().post(f"/applications/{source_id}/apply-again", data=duplicate_form())
    assert response.status_code == 400
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Application.id))) == 1
        db.session.remove(); db.drop_all()
