from datetime import datetime

import pytest

from app import create_app, db
from app.models import (
    Application,
    ApplicationStatus,
    Document,
    DocumentType,
    Resume,
    TimelineEvent,
    TimelineEventType,
)


def add_application(company_name="Timeline Co", **overrides):
    application = Application(
        company_name=company_name,
        position_title="Software Engineer",
        **overrides,
    )
    db.session.add(application)
    db.session.commit()
    return application


def timeline_form(**overrides):
    values = {
        "event_type": "Interview scheduled",
        "event_date": "2026-09-21T14:30",
        "notes": "Technical interview with the platform team",
    }
    values.update(overrides)
    return values


def add_event(application, event_type=TimelineEventType.CUSTOM, event_date=None, notes=None):
    event = TimelineEvent(
        application=application,
        event_type=event_type,
        event_date=event_date or datetime(2026, 9, 20, 9),
        notes=notes,
    )
    db.session.add(event)
    db.session.commit()
    return event


def test_application_timeline_has_useful_empty_state(app, client):
    with app.app_context():
        application_id = add_application().id
    page = client.get(f"/applications/{application_id}").get_data(as_text=True)
    assert "No timeline events yet" in page
    assert f"/applications/{application_id}/timeline/new" in page


def test_add_timeline_event_persists_application_relationship(app, client):
    with app.app_context():
        application_id = add_application().id
    response = client.post(
        f"/applications/{application_id}/timeline/new",
        data=timeline_form(),
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Timeline event added" in body
    assert "Interview scheduled" in body
    assert "Technical interview with the platform team" in body
    with app.app_context():
        event = db.session.scalar(db.select(TimelineEvent))
        assert event.application_id == application_id
        assert event.event_type is TimelineEventType.INTERVIEW_SCHEDULED
        assert event.event_date == datetime(2026, 9, 21, 14, 30)


@pytest.mark.parametrize("event_type", [member.value for member in TimelineEventType])
def test_all_specified_timeline_event_types_are_supported(app, client, event_type):
    with app.app_context():
        application_id = add_application(company_name=event_type).id
    response = client.post(
        f"/applications/{application_id}/timeline/new",
        data=timeline_form(event_type=event_type),
    )
    assert response.status_code == 302
    with app.app_context():
        event = db.session.scalar(
            db.select(TimelineEvent).where(TimelineEvent.application_id == application_id)
        )
        assert event.event_type.value == event_type


def test_timeline_displays_events_earliest_to_latest(app, client):
    with app.app_context():
        application = add_application()
        application_id = application.id
        add_event(
            application,
            TimelineEventType.INTERVIEW_COMPLETED,
            datetime(2026, 9, 25, 16),
            "Later event",
        )
        add_event(
            application,
            TimelineEventType.APPLICATION_SUBMITTED,
            datetime(2026, 9, 10, 8),
            "Earlier event",
        )
        add_event(
            application,
            TimelineEventType.ASSESSMENT_RECEIVED,
            datetime(2026, 9, 15, 12),
            "Middle event",
        )
    body = client.get(f"/applications/{application_id}").get_data(as_text=True)
    assert body.index("Earlier event") < body.index("Middle event") < body.index("Later event")


def test_create_rejects_missing_and_invalid_required_fields(app, client):
    with app.app_context():
        application_id = add_application().id
    response = client.post(
        f"/applications/{application_id}/timeline/new",
        data=timeline_form(event_type="Unknown", event_date="not-a-date"),
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Select a valid event type" in body
    assert "Enter a valid local date and time" in body
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(TimelineEvent.id))) == 0

    missing = client.post(
        f"/applications/{application_id}/timeline/new",
        data={"event_type": "Custom event", "event_date": ""},
    )
    assert "Event date and time are required" in missing.get_data(as_text=True)


def test_create_rejects_timezone_and_excessive_notes(app, client):
    with app.app_context():
        application_id = add_application().id
    response = client.post(
        f"/applications/{application_id}/timeline/new",
        data=timeline_form(event_date="2026-09-21T14:30+08:00", notes="x" * 5001),
    )
    body = response.get_data(as_text=True)
    assert "valid local date and time" in body
    assert "5,000 characters or fewer" in body
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(TimelineEvent.id))) == 0


def test_invalid_form_preserves_submitted_notes(app, client):
    with app.app_context():
        application_id = add_application().id
    body = client.post(
        f"/applications/{application_id}/timeline/new",
        data=timeline_form(event_date="", notes="Do not lose this note"),
    ).get_data(as_text=True)
    assert "Do not lose this note" in body


def test_cannot_add_event_to_missing_application(client):
    assert client.post(
        "/applications/9999/timeline/new", data=timeline_form()
    ).status_code == 404


def test_edit_timeline_event_updates_same_record(app, client):
    with app.app_context():
        application = add_application()
        application_id = application.id
        event_id = add_event(application, notes="Original notes").id
    response = client.post(
        f"/timeline/{event_id}/edit",
        data=timeline_form(
            event_type="Offer received",
            event_date="2026-10-01T09:15",
            notes="Updated notes",
        ),
        follow_redirects=True,
    )
    assert "Timeline event updated" in response.get_data(as_text=True)
    with app.app_context():
        event = db.session.get(TimelineEvent, event_id)
        assert event.application_id == application_id
        assert event.event_type is TimelineEventType.OFFER_RECEIVED
        assert event.event_date == datetime(2026, 10, 1, 9, 15)
        assert event.notes == "Updated notes"
        assert db.session.scalar(db.select(db.func.count(TimelineEvent.id))) == 1


def test_invalid_edit_does_not_change_event(app, client):
    with app.app_context():
        application = add_application()
        event = add_event(application, notes="Original notes")
        event_id = event.id
        original_date = event.event_date
    response = client.post(
        f"/timeline/{event_id}/edit",
        data=timeline_form(event_type="Invalid", notes="Attempted change"),
    )
    assert response.status_code == 200
    with app.app_context():
        event = db.session.get(TimelineEvent, event_id)
        assert event.event_type is TimelineEventType.CUSTOM
        assert event.event_date == original_date
        assert event.notes == "Original notes"


def test_delete_event_is_post_only_and_preserves_application(app, client):
    with app.app_context():
        application = add_application()
        application_id = application.id
        event_id = add_event(application).id
    assert client.get(f"/timeline/{event_id}/delete").status_code == 405
    response = client.post(f"/timeline/{event_id}/delete", follow_redirects=True)
    assert "Timeline event deleted" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(TimelineEvent, event_id) is None
        assert db.session.get(Application, application_id) is not None


def test_edit_and_delete_missing_events_return_404(client):
    assert client.get("/timeline/9999/edit").status_code == 404
    assert client.post("/timeline/9999/delete").status_code == 404


def test_event_changes_do_not_affect_another_application(app, client):
    with app.app_context():
        first = add_application("First Co")
        second = add_application("Second Co")
        first_id, second_id = first.id, second.id
        first_event = add_event(first, notes="First event")
        add_event(second, notes="Second event")
        first_event_id = first_event.id
    client.post(
        f"/timeline/{first_event_id}/edit",
        data=timeline_form(notes="Changed first event"),
    )
    first_page = client.get(f"/applications/{first_id}").get_data(as_text=True)
    second_page = client.get(f"/applications/{second_id}").get_data(as_text=True)
    assert "Changed first event" in first_page
    assert "Second event" not in first_page
    assert "Second event" in second_page
    assert "Changed first event" not in second_page


def test_status_transition_creates_atomic_history_event(app, client):
    with app.app_context():
        application_id = add_application(status=ApplicationStatus.APPLIED).id
    response = client.post(
        f"/applications/{application_id}/status",
        data={"status": "Interview"},
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)
    assert "Status changed" in body
    assert "Status changed from Applied to Interview" in body
    with app.app_context():
        application = db.session.get(Application, application_id)
        assert application.status is ApplicationStatus.INTERVIEW
        assert len(application.timeline_events) == 1
        assert application.timeline_events[0].event_type is TimelineEventType.STATUS_CHANGED


def test_unchanged_or_invalid_status_does_not_create_history(app, client):
    with app.app_context():
        application_id = add_application(status=ApplicationStatus.APPLIED).id
    client.post(f"/applications/{application_id}/status", data={"status": "Applied"})
    client.post(f"/applications/{application_id}/status", data={"status": "Unknown"})
    with app.app_context():
        application = db.session.get(Application, application_id)
        assert application.status is ApplicationStatus.APPLIED
        assert application.timeline_events == []


def test_priority_change_does_not_create_timeline_event(app, client):
    with app.app_context():
        application_id = add_application().id
    client.post(f"/applications/{application_id}/priority", data={"priority": "High"})
    with app.app_context():
        assert db.session.get(Application, application_id).timeline_events == []


def test_deleting_application_cascades_timeline_events(app, client):
    with app.app_context():
        application = add_application()
        application_id = application.id
        event_id = add_event(application).id
    client.post(f"/applications/{application_id}/delete")
    with app.app_context():
        assert db.session.get(Application, application_id) is None
        assert db.session.get(TimelineEvent, event_id) is None


def test_timeline_mutations_preserve_resume_and_document_relationships(app, client):
    with app.app_context():
        resume = Resume(
            display_name="Timeline Resume",
            version_name="v1",
            original_file_name="resume.pdf",
            stored_file_name="9" * 32 + ".pdf",
        )
        application = add_application(resume=resume)
        application_id, resume_id = application.id, resume.id
        document = Document(
            application=application,
            document_type=DocumentType.COVER_LETTER,
            file_path=f"{application.id}/{'8' * 32}.pdf",
            original_file_name="cover.pdf",
        )
        db.session.add(document)
        db.session.commit()
        document_id = document.id
    response = client.post(
        f"/applications/{application_id}/timeline/new", data=timeline_form()
    )
    assert response.status_code == 302
    with app.app_context():
        application = db.session.get(Application, application_id)
        assert application.resume_id == resume_id
        assert db.session.get(Document, document_id).application_id == application_id


def test_timeline_mutations_require_csrf_when_enabled(tmp_path):
    protected_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "csrf-test-secret",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'csrf.db').as_posix()}",
            "UPLOAD_ROOT": str(tmp_path / "uploads"),
        }
    )
    response = protected_app.test_client().post(
        "/applications/1/timeline/new", data=timeline_form()
    )
    assert response.status_code == 400
