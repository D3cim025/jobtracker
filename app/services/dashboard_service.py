from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app import db
from app.models import (
    Application,
    ApplicationStatus,
    Reminder,
    ReminderType,
    TimelineEvent,
    TimelineEventType,
)
from app.services.reminder_service import ReminderGroups, reminder_groups


@dataclass(frozen=True)
class ActivityCounts:
    added_this_week: int
    added_this_month: int
    applied_this_week: int
    applied_this_month: int


@dataclass(frozen=True)
class DashboardData:
    total_applications: int
    status_counts: dict[ApplicationStatus, int]
    activity_counts: ActivityCounts
    reminders: ReminderGroups
    interview_reminders: list[Reminder]
    assessment_reminders: list[Reminder]
    interview_events: list[TimelineEvent]
    recent_applications: list[Application]
    recent_status_changes: list[TimelineEvent]


def calendar_boundaries(today: date) -> tuple[date, date]:
    """Return the Monday and first day of month containing the local date."""
    return today - timedelta(days=today.weekday()), today.replace(day=1)


def dashboard_data(
    today: date | None = None, now: datetime | None = None, limit: int = 5
) -> DashboardData:
    """Build the dashboard with bounded aggregate and eager-loaded queries."""
    local_now = now or datetime.now()
    local_today = today or local_now.date()
    week_start, month_start = calendar_boundaries(local_today)
    tomorrow = local_today + timedelta(days=1)
    week_start_dt = datetime.combine(week_start, time.min)
    month_start_dt = datetime.combine(month_start, time.min)
    tomorrow_dt = datetime.combine(tomorrow, time.min)

    grouped_counts = dict(
        db.session.execute(
            select(Application.status, func.count(Application.id)).group_by(Application.status)
        ).all()
    )
    status_counts = {status: grouped_counts.get(status, 0) for status in ApplicationStatus}

    activity_row = db.session.execute(
        select(
            func.count(Application.id).filter(
                Application.created_at >= week_start_dt, Application.created_at < tomorrow_dt
            ),
            func.count(Application.id).filter(
                Application.created_at >= month_start_dt, Application.created_at < tomorrow_dt
            ),
            func.count(Application.id).filter(
                Application.date_applied >= week_start, Application.date_applied < tomorrow
            ),
            func.count(Application.id).filter(
                Application.date_applied >= month_start, Application.date_applied < tomorrow
            ),
        )
    ).one()
    activity_counts = ActivityCounts(*activity_row)

    groups = reminder_groups(now=local_now)
    interview_reminders = [
        reminder for reminder in groups.upcoming if reminder.reminder_type is ReminderType.INTERVIEW
    ]
    assessment_reminders = [
        reminder
        for reminder in groups.upcoming
        if reminder.reminder_type is ReminderType.ASSESSMENT_DEADLINE
    ]
    interview_events = list(
        db.session.scalars(
            select(TimelineEvent)
            .options(selectinload(TimelineEvent.application))
            .where(
                TimelineEvent.event_type == TimelineEventType.INTERVIEW_SCHEDULED,
                TimelineEvent.event_date >= local_now,
            )
            .order_by(TimelineEvent.event_date, TimelineEvent.id)
            .limit(limit)
        )
    )
    recent_applications = list(
        db.session.scalars(
            select(Application).order_by(Application.created_at.desc(), Application.id.desc()).limit(limit)
        )
    )
    recent_status_changes = list(
        db.session.scalars(
            select(TimelineEvent)
            .options(selectinload(TimelineEvent.application))
            .where(TimelineEvent.event_type == TimelineEventType.STATUS_CHANGED)
            .order_by(TimelineEvent.created_at.desc(), TimelineEvent.id.desc())
            .limit(limit)
        )
    )
    return DashboardData(
        total_applications=sum(status_counts.values()),
        status_counts=status_counts,
        activity_counts=activity_counts,
        reminders=groups,
        interview_reminders=interview_reminders[:limit],
        assessment_reminders=assessment_reminders[:limit],
        interview_events=interview_events,
        recent_applications=recent_applications,
        recent_status_changes=recent_status_changes,
    )
