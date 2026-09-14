from datetime import datetime

import pytest

from app import create_app, db
from app.models import (
    Application,
    Document,
    DocumentType,
    Reminder,
    ReminderType,
    Resume,
    TimelineEvent,
    TimelineEventType,
)
from app.services.reminder_service import reminder_groups


def add_application(company_name="Reminder Co", **overrides):
    application = Application(
        company_name=company_name,
        position_title="Software Engineer",
        **overrides,
    )
    db.session.add(application)
    db.session.commit()
    return application


def reminder_form(**overrides):
    values = {
        "reminder_type": "Follow-up",
        "reminder_date": "2099-09-21T14:30",
        "notes": "Email the recruiter",
    }
    values.update(overrides)
    return values


def add_reminder(application, reminder_date, completed=False, notes=None, reminder_type=ReminderType.CUSTOM):
    reminder = Reminder(
        application=application,
        reminder_type=reminder_type,
        reminder_date=reminder_date,
        completed=completed,
        notes=notes,
    )
    db.session.add(reminder)
    db.session.commit()
    return reminder


def test_application_reminders_have_useful_empty_states(app, client):
    with app.app_context():
        application_id = add_application().id
    body = client.get(f"/applications/{application_id}").get_data(as_text=True)
    assert "Nothing overdue" in body
    assert "No upcoming reminders" in body
    assert "No completed reminders yet" in body
    assert f"/applications/{application_id}/reminders/new" in body


def test_create_reminder_defaults_incomplete_and_belongs_to_application(app, client):
    with app.app_context():
        application_id = add_application().id
    response = client.post(
        f"/applications/{application_id}/reminders/new",
        data=reminder_form(),
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Reminder created" in body
    assert "Email the recruiter" in body
    with app.app_context():
        reminder = db.session.scalar(db.select(Reminder))
        assert reminder.application_id == application_id
        assert reminder.reminder_type is ReminderType.FOLLOW_UP
        assert reminder.reminder_date == datetime(2099, 9, 21, 14, 30)
        assert reminder.completed is False
        assert reminder.created_at is not None


@pytest.mark.parametrize("reminder_type", [member.value for member in ReminderType])
def test_all_specified_reminder_types_are_supported(app, client, reminder_type):
    with app.app_context():
        application_id = add_application(company_name=reminder_type).id
    response = client.post(
        f"/applications/{application_id}/reminders/new",
        data=reminder_form(reminder_type=reminder_type),
    )
    assert response.status_code == 302
    with app.app_context():
        reminder = db.session.scalar(
            db.select(Reminder).where(Reminder.application_id == application_id)
        )
        assert reminder.reminder_type.value == reminder_type


def test_create_rejects_invalid_type_missing_date_and_preserves_notes(app, client):
    with app.app_context():
        application_id = add_application().id
    response = client.post(
        f"/applications/{application_id}/reminders/new",
        data=reminder_form(
            reminder_type="Unknown",
            reminder_date="",
            notes="Do not lose this reminder note",
        ),
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Select a valid reminder type" in body
    assert "Reminder date and time are required" in body
    assert "Do not lose this reminder note" in body
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Reminder.id))) == 0


@pytest.mark.parametrize("bad_date", ["not-a-date", "2099-09-21T14:30+08:00"])
def test_create_rejects_malformed_or_timezone_aware_date(app, client, bad_date):
    with app.app_context():
        application_id = add_application().id
    response = client.post(
        f"/applications/{application_id}/reminders/new",
        data=reminder_form(reminder_date=bad_date),
    )
    assert "Enter a valid local date and time" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Reminder.id))) == 0


def test_create_rejects_excessive_notes(app, client):
    with app.app_context():
        application_id = add_application().id
    response = client.post(
        f"/applications/{application_id}/reminders/new",
        data=reminder_form(notes="x" * 5001),
    )
    assert "5,000 characters or fewer" in response.get_data(as_text=True)


def test_cannot_create_reminder_for_missing_application(client):
    assert client.post(
        "/applications/9999/reminders/new", data=reminder_form()
    ).status_code == 404


def test_edit_reminder_updates_same_record_without_changing_owner(app, client):
    with app.app_context():
        application = add_application()
        application_id = application.id
        reminder_id = add_reminder(
            application, datetime(2099, 9, 20), notes="Original"
        ).id
    response = client.post(
        f"/applications/{application_id}/reminders/{reminder_id}/edit",
        data=reminder_form(
            reminder_type="Interview",
            reminder_date="2099-10-01T09:15",
            notes="Updated",
        ),
        follow_redirects=True,
    )
    assert "Reminder updated" in response.get_data(as_text=True)
    with app.app_context():
        reminder = db.session.get(Reminder, reminder_id)
        assert reminder.application_id == application_id
        assert reminder.reminder_type is ReminderType.INTERVIEW
        assert reminder.reminder_date == datetime(2099, 10, 1, 9, 15)
        assert reminder.notes == "Updated"
        assert db.session.scalar(db.select(db.func.count(Reminder.id))) == 1


def test_invalid_edit_preserves_stored_reminder(app, client):
    with app.app_context():
        application = add_application()
        application_id = application.id
        reminder = add_reminder(application, datetime(2099, 9, 20), notes="Original")
        reminder_id = reminder.id
        original_date = reminder.reminder_date
    response = client.post(
        f"/applications/{application_id}/reminders/{reminder_id}/edit",
        data=reminder_form(reminder_type="Invalid", notes="Attempted"),
    )
    assert response.status_code == 200
    with app.app_context():
        reminder = db.session.get(Reminder, reminder_id)
        assert reminder.reminder_type is ReminderType.CUSTOM
        assert reminder.reminder_date == original_date
        assert reminder.notes == "Original"


def test_mark_completed_and_reopen_preserves_reminder_history(app, client):
    with app.app_context():
        application = add_application()
        application_id = application.id
        reminder_id = add_reminder(application, datetime(2099, 9, 20)).id
    completed = client.post(
        f"/applications/{application_id}/reminders/{reminder_id}/completion",
        data={"completed": "1"},
        follow_redirects=True,
    )
    assert "Reminder marked completed" in completed.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Reminder, reminder_id).completed is True
    reopened = client.post(
        f"/applications/{application_id}/reminders/{reminder_id}/completion",
        data={"completed": "0"},
        follow_redirects=True,
    )
    assert "Reminder reopened" in reopened.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Reminder, reminder_id).completed is False


def test_invalid_completion_value_does_not_change_reminder(app, client):
    with app.app_context():
        application = add_application()
        application_id = application.id
        reminder_id = add_reminder(application, datetime(2099, 9, 20)).id
    response = client.post(
        f"/applications/{application_id}/reminders/{reminder_id}/completion",
        data={"completed": "yes"},
        follow_redirects=True,
    )
    assert "completion value is invalid" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Reminder, reminder_id).completed is False


def test_delete_is_post_only_and_preserves_application(app, client):
    with app.app_context():
        application = add_application()
        application_id = application.id
        reminder_id = add_reminder(application, datetime(2099, 9, 20)).id
    delete_url = f"/applications/{application_id}/reminders/{reminder_id}/delete"
    assert client.get(delete_url).status_code == 405
    response = client.post(delete_url, follow_redirects=True)
    assert "Reminder deleted" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Reminder, reminder_id) is None
        assert db.session.get(Application, application_id) is not None


def test_completion_is_post_only(app, client):
    with app.app_context():
        application = add_application()
        application_id = application.id
        reminder_id = add_reminder(application, datetime(2099, 9, 20)).id
    url = f"/applications/{application_id}/reminders/{reminder_id}/completion"
    assert client.get(url).status_code == 405


@pytest.mark.parametrize("action", ["edit", "completion", "delete"])
def test_application_isolation_rejects_mismatched_parent(app, client, action):
    with app.app_context():
        owner = add_application("Owner")
        other = add_application("Other")
        other_id = other.id
        reminder_id = add_reminder(owner, datetime(2099, 9, 20)).id
    url = f"/applications/{other_id}/reminders/{reminder_id}/{action}"
    response = client.post(url, data=reminder_form(completed="1"))
    assert response.status_code == 404


def test_groups_classify_boundary_and_keep_completed_history(app):
    boundary = datetime(2026, 9, 14, 12)
    with app.app_context():
        application = add_application()
        overdue = add_reminder(application, datetime(2026, 9, 14, 11), notes="Overdue")
        boundary_item = add_reminder(application, boundary, notes="Boundary")
        future = add_reminder(application, datetime(2026, 9, 15), notes="Future")
        completed = add_reminder(
            application, datetime(2026, 9, 13), completed=True, notes="Completed"
        )
        groups = reminder_groups(application.id, now=boundary)
        assert groups.overdue == [overdue]
        assert groups.upcoming == [boundary_item, future]
        assert groups.completed == [completed]


def test_active_and_completed_reminder_sorting(app):
    boundary = datetime(2026, 9, 14, 12)
    with app.app_context():
        application = add_application()
        late_overdue = add_reminder(application, datetime(2026, 9, 10), notes="Oldest overdue")
        near_overdue = add_reminder(application, datetime(2026, 9, 14, 11), notes="Nearest overdue")
        near_upcoming = add_reminder(application, datetime(2026, 9, 14, 13), notes="Nearest upcoming")
        far_upcoming = add_reminder(application, datetime(2026, 10, 1), notes="Far upcoming")
        old_completed = add_reminder(application, datetime(2026, 8, 1), True, "Old completed")
        new_completed = add_reminder(application, datetime(2026, 9, 1), True, "New completed")
        groups = reminder_groups(application.id, now=boundary)
        assert groups.overdue == [near_overdue, late_overdue]
        assert groups.upcoming == [near_upcoming, far_upcoming]
        assert groups.completed == [new_completed, old_completed]


def test_global_groups_and_page_include_multiple_applications(app, client):
    with app.app_context():
        first = add_application("Alpha Co")
        second = add_application("Beta Co")
        add_reminder(first, datetime(2099, 9, 20), notes="Alpha reminder")
        add_reminder(second, datetime(2000, 9, 20), notes="Beta reminder")
    body = client.get("/reminders").get_data(as_text=True)
    assert "Alpha Co" in body
    assert "Beta Co" in body
    assert "Alpha reminder" in body
    assert "Beta reminder" in body


def test_application_detail_shows_only_its_reminder_groups(app, client):
    with app.app_context():
        first = add_application("First Co")
        second = add_application("Second Co")
        first_id, second_id = first.id, second.id
        add_reminder(first, datetime(2099, 9, 20), notes="First reminder")
        add_reminder(second, datetime(2099, 9, 20), notes="Second reminder")
    first_page = client.get(f"/applications/{first_id}").get_data(as_text=True)
    second_page = client.get(f"/applications/{second_id}").get_data(as_text=True)
    assert "First reminder" in first_page and "Second reminder" not in first_page
    assert "Second reminder" in second_page and "First reminder" not in second_page


def test_deleting_application_cascades_reminders(app, client):
    with app.app_context():
        application = add_application()
        application_id = application.id
        reminder_id = add_reminder(application, datetime(2099, 9, 20)).id
    client.post(f"/applications/{application_id}/delete")
    with app.app_context():
        assert db.session.get(Application, application_id) is None
        assert db.session.get(Reminder, reminder_id) is None


def test_reminder_changes_preserve_resume_document_and_timeline(app, client):
    with app.app_context():
        resume = Resume(
            display_name="Reminder Resume",
            version_name="v1",
            original_file_name="resume.pdf",
            stored_file_name="7" * 32 + ".pdf",
        )
        application = add_application(resume=resume)
        application_id, resume_id = application.id, resume.id
        document = Document(
            application=application,
            document_type=DocumentType.COVER_LETTER,
            file_path=f"{application.id}/{'6' * 32}.pdf",
            original_file_name="cover.pdf",
        )
        event = TimelineEvent(
            application=application,
            event_type=TimelineEventType.CUSTOM,
            event_date=datetime(2026, 9, 1),
        )
        db.session.add_all([document, event])
        db.session.commit()
        document_id, event_id = document.id, event.id
    response = client.post(
        f"/applications/{application_id}/reminders/new", data=reminder_form()
    )
    assert response.status_code == 302
    with app.app_context():
        application = db.session.get(Application, application_id)
        assert application.resume_id == resume_id
        assert db.session.get(Document, document_id).application_id == application_id
        assert db.session.get(TimelineEvent, event_id).application_id == application_id


def test_reminder_mutations_require_csrf_when_enabled(tmp_path):
    protected_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "csrf-test-secret",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'csrf.db').as_posix()}",
            "UPLOAD_ROOT": str(tmp_path / "uploads"),
        }
    )
    response = protected_app.test_client().post(
        "/applications/1/reminders/new", data=reminder_form()
    )
    assert response.status_code == 400
