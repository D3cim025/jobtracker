from datetime import date, datetime, time, timedelta

from app import db
from app.models import (
    Application,
    ApplicationStatus,
    Reminder,
    ReminderType,
    TimelineEvent,
    TimelineEventType,
)
from app.services.dashboard_service import calendar_boundaries, dashboard_data


def add_application(company: str, status=ApplicationStatus.SAVED, **values):
    application = Application(
        company_name=company,
        position_title=values.pop("position_title", "Engineer"),
        status=status,
        **values,
    )
    db.session.add(application)
    db.session.commit()
    return application


def test_dashboard_loads_with_empty_states_and_navigation(client):
    response = client.get("/")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Application summary" in body
    assert "No applications yet" in body
    assert "No upcoming reminders" in body
    assert "Nothing overdue" in body
    assert "No upcoming interviews or assessment deadlines" in body
    assert "Recent application status changes will appear here" in body
    for path in ("/applications/new", "/applications", "/resumes", "/reminders", "/analytics"):
        assert f'href="{path}"' in body


def test_dashboard_counts_total_and_every_status(app, client):
    with app.app_context():
        for status in ApplicationStatus:
            add_application(f"{status.value} Co", status=status)
        add_application("Another Applied", status=ApplicationStatus.APPLIED)
        data = dashboard_data()
        assert data.total_applications == 8
        assert data.status_counts == {
            ApplicationStatus.SAVED: 1,
            ApplicationStatus.APPLIED: 2,
            ApplicationStatus.ASSESSMENT: 1,
            ApplicationStatus.INTERVIEW: 1,
            ApplicationStatus.OFFER: 1,
            ApplicationStatus.REJECTED: 1,
            ApplicationStatus.WITHDRAWN: 1,
        }
    body = client.get("/").get_data(as_text=True)
    assert "Total applications</span><strong>8" in body
    for status in ApplicationStatus:
        assert f">{status.value}</span>" in body


def test_dashboard_weekly_and_monthly_date_boundaries(app):
    today = date(2026, 9, 14)
    week_start, month_start = calendar_boundaries(today)
    with app.app_context():
        dates = [today, week_start, month_start, month_start - timedelta(days=1)]
        for index, record_date in enumerate(dates):
            added = add_application(f"Company {index}", date_applied=record_date)
            added.created_at = datetime.combine(record_date, time(12))
        db.session.commit()
        counts = dashboard_data(today=today, now=datetime.combine(today, time(12))).activity_counts
        assert counts.added_this_week == sum(week_start <= value <= today for value in dates)
        assert counts.added_this_month == sum(month_start <= value <= today for value in dates)
        assert counts.applied_this_week == sum(week_start <= value <= today for value in dates)
        assert counts.applied_this_month == sum(month_start <= value <= today for value in dates)


def test_dashboard_classifies_active_reminders_and_excludes_completed(app, client):
    now = datetime.now().replace(microsecond=0)
    with app.app_context():
        upcoming_app = add_application("Upcoming Company")
        overdue_app = add_application("Overdue Company")
        completed_app = add_application("Completed Only Company")
        db.session.add_all([
            Reminder(application=upcoming_app, reminder_type=ReminderType.FOLLOW_UP,
                     reminder_date=now + timedelta(days=1), notes="Upcoming note"),
            Reminder(application=overdue_app, reminder_type=ReminderType.CUSTOM,
                     reminder_date=now - timedelta(days=1), notes="Overdue note"),
            Reminder(application=completed_app, reminder_type=ReminderType.FOLLOW_UP,
                     reminder_date=now + timedelta(hours=1), completed=True, notes="Completed secret"),
        ])
        db.session.commit()
    body = client.get("/").get_data(as_text=True)
    assert "Upcoming Company" in body and "Overdue Company" in body
    assert "Completed secret" not in body


def test_dashboard_shows_interview_and_assessment_reminders_and_events(app, client):
    now = datetime.now().replace(microsecond=0)
    with app.app_context():
        interview = add_application("Interview Company", position_title="Designer")
        assessment = add_application("Assessment Company", position_title="Developer")
        timeline = add_application("Timeline Interview", position_title="Manager")
        db.session.add_all([
            Reminder(application=interview, reminder_type=ReminderType.INTERVIEW,
                     reminder_date=now + timedelta(days=1)),
            Reminder(application=assessment, reminder_type=ReminderType.ASSESSMENT_DEADLINE,
                     reminder_date=now + timedelta(days=2)),
            TimelineEvent(application=timeline, event_type=TimelineEventType.INTERVIEW_SCHEDULED,
                          event_date=now + timedelta(days=3)),
        ])
        db.session.commit()
    body = client.get("/").get_data(as_text=True)
    assert "Interview reminder" in body and "Interview Company — Designer" in body
    assert "Assessment deadline" in body and "Assessment Company — Developer" in body
    assert "Interview scheduled" in body and "Timeline Interview — Manager" in body


def test_dashboard_recent_activity_uses_existing_records(app, client):
    with app.app_context():
        application = add_application("Recent Company", position_title="Recent Role")
        application.timeline_events.append(TimelineEvent(
            event_type=TimelineEventType.STATUS_CHANGED,
            event_date=datetime.now(),
            notes="Status changed from Saved to Applied.",
        ))
        db.session.commit()
    body = client.get("/").get_data(as_text=True)
    assert "Recently added applications" in body
    assert "Recent Company — Recent Role" in body
    assert "Status changed from Saved to Applied." in body


def test_dashboard_limits_long_lists_and_orders_nearest_reminders(app):
    now = datetime.now().replace(microsecond=0)
    with app.app_context():
        for offset in range(7, 0, -1):
            application = add_application(f"Reminder Company {offset}")
            db.session.add(Reminder(
                application=application,
                reminder_type=ReminderType.FOLLOW_UP,
                reminder_date=now + timedelta(days=offset),
            ))
        db.session.commit()
        data = dashboard_data(now=now)
        assert [item.reminder_date for item in data.reminders.upcoming] == sorted(
            item.reminder_date for item in data.reminders.upcoming
        )
        assert len(data.recent_applications) == 5
