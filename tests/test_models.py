from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError, StatementError

from app import db
from app.models import (
    Application,
    ApplicationStatus,
    Document,
    DocumentType,
    JobType,
    Priority,
    Reminder,
    ReminderType,
    Resume,
    Setting,
    TimelineEvent,
    TimelineEventType,
    WorkSetup,
)


def make_application(**overrides):
    values = {"company_name": "Acme", "position_title": "Python Developer"}
    values.update(overrides)
    return Application(**values)


def make_resume(**overrides):
    values = {
        "display_name": "Software Engineer Resume",
        "original_file_name": "resume.pdf",
        "stored_file_name": "7a1c-resume.pdf",
        "version_name": "v1",
    }
    values.update(overrides)
    return Resume(**values)


def test_schema_contains_all_stage_two_entities(app):
    with app.app_context():
        assert set(inspect(db.engine).get_table_names()) == {
            "applications", "documents", "reminders", "resumes", "settings", "timeline_events"
        }


def test_application_defaults_and_normalization(app):
    with app.app_context():
        application = make_application(company_name="  Acme  ", currency="usd")
        db.session.add(application)
        db.session.commit()
        assert application.company_name == "Acme"
        assert application.status is ApplicationStatus.SAVED
        assert application.priority is Priority.MEDIUM
        assert application.job_type is JobType.FULL_TIME
        assert application.work_setup is WorkSetup.FLEXIBLE_OTHER
        assert application.currency == "USD"
        assert application.date_found == date.today()
        assert application.created_at is not None
        assert application.updated_at is not None


@pytest.mark.parametrize("field", ["company_name", "position_title"])
def test_application_requires_meaningful_names(field):
    with pytest.raises(ValueError, match="required"):
        make_application(**{field: "   "})


@pytest.mark.parametrize("currency", ["US", "US12", ""])
def test_application_rejects_invalid_currency(currency):
    with pytest.raises(ValueError, match="three-letter"):
        make_application(currency=currency)


def test_application_salary_constraints_are_enforced(app):
    with app.app_context():
        db.session.add(make_application(salary_min=Decimal("90000"), salary_max=Decimal("50000")))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_application_enum_constraint_rejects_unknown_database_value(app):
    with app.app_context():
        db.session.add(make_application(status="Waiting"))
        with pytest.raises((LookupError, StatementError)):
            db.session.commit()
        db.session.rollback()


def test_exact_resume_relationship_is_bidirectional(app):
    with app.app_context():
        resume = make_resume()
        first = make_application(company_name="Alpha", resume=resume)
        second = make_application(company_name="Beta", resume=resume)
        db.session.add_all([first, second])
        db.session.commit()
        assert first.resume_id == resume.id
        assert {item.company_name for item in resume.applications} == {"Alpha", "Beta"}


def test_referenced_resume_cannot_be_deleted(app):
    with app.app_context():
        resume = make_resume()
        db.session.add(make_application(resume=resume))
        db.session.commit()
        resume_id = resume.id
        db.session.delete(resume)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        assert db.session.get(Resume, resume_id) is not None


def test_resume_versions_coexist_as_separate_records(app):
    with app.app_context():
        version_one = make_resume()
        version_two = make_resume(stored_file_name="8b2d-resume.pdf", version_name="v2")
        db.session.add_all([version_one, version_two])
        db.session.commit()
        assert version_one.id != version_two.id
        assert Resume.query.count() == 2


def test_resume_storage_name_is_unique(app):
    with app.app_context():
        db.session.add_all([make_resume(), make_resume(version_name="v2")])
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_resume_hash_validation_and_normalization():
    digest = "A" * 64
    assert make_resume(file_hash=digest).file_hash == digest.lower()
    with pytest.raises(ValueError, match="SHA-256"):
        make_resume(file_hash="not-a-hash")


def test_document_belongs_to_application(app):
    with app.app_context():
        application = make_application()
        document = Document(
            document_type=DocumentType.COVER_LETTER,
            file_path="cover_letters/generated.pdf",
            original_file_name="Acme cover letter.pdf",
        )
        application.documents.append(document)
        db.session.add(application)
        db.session.commit()
        assert document.application_id == application.id
        assert application.documents == [document]


def test_document_requires_an_existing_application(app):
    with app.app_context():
        db.session.add(Document(
            application_id=9999,
            document_type=DocumentType.OTHER,
            file_path="documents/missing.txt",
            original_file_name="missing.txt",
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_timeline_events_are_ordered_chronologically(app):
    with app.app_context():
        application = make_application()
        later = TimelineEvent(
            event_type=TimelineEventType.INTERVIEW_SCHEDULED,
            event_date=datetime(2026, 9, 20, 10),
        )
        earlier = TimelineEvent(
            event_type=TimelineEventType.APPLICATION_SUBMITTED,
            event_date=datetime(2026, 9, 14, 9),
        )
        application.timeline_events.extend([later, earlier])
        db.session.add(application)
        db.session.commit()
        db.session.expire(application, ["timeline_events"])
        assert application.timeline_events == [earlier, later]


def test_reminders_belong_to_application_and_default_incomplete(app):
    with app.app_context():
        application = make_application()
        reminder = Reminder(
            reminder_type=ReminderType.FOLLOW_UP,
            reminder_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=3),
        )
        application.reminders.append(reminder)
        db.session.add(application)
        db.session.commit()
        assert reminder.application_id == application.id
        assert reminder.completed is False


def test_deleting_application_cascades_to_owned_records(app):
    with app.app_context():
        application = make_application()
        application.documents.append(Document(
            document_type=DocumentType.PORTFOLIO,
            file_path="documents/portfolio.pdf",
            original_file_name="portfolio.pdf",
        ))
        application.timeline_events.append(TimelineEvent(
            event_type=TimelineEventType.CUSTOM,
            event_date=datetime.now(UTC).replace(tzinfo=None),
        ))
        application.reminders.append(Reminder(
            reminder_type=ReminderType.CUSTOM,
            reminder_date=datetime.now(UTC).replace(tzinfo=None),
        ))
        db.session.add(application)
        db.session.commit()
        db.session.delete(application)
        db.session.commit()
        assert Document.query.count() == 0
        assert TimelineEvent.query.count() == 0
        assert Reminder.query.count() == 0


def test_setting_keys_are_unique(app):
    with app.app_context():
        db.session.add_all([Setting(key="currency", value="PHP"), Setting(key="currency", value="USD")])
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_init_db_command_is_safe_to_run_repeatedly(app):
    runner = app.test_cli_runner()
    first = runner.invoke(args=["init-db"])
    second = runner.invoke(args=["init-db"])
    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "Initialized" in second.output
