from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app import db
from app.models import Application, Reminder, ReminderType


@dataclass(frozen=True)
class ReminderGroups:
    upcoming: list[Reminder]
    overdue: list[Reminder]
    completed: list[Reminder]


def local_now() -> datetime:
    """Return local wall-clock time to match HTML datetime-local input."""

    return datetime.now()


def reminder_groups(
    application_id: int | None = None, now: datetime | None = None
) -> ReminderGroups:
    """Return reusable reminder classifications for application and future dashboard views."""

    boundary = now or local_now()
    base = select(Reminder).options(selectinload(Reminder.application))
    if application_id is not None:
        base = base.where(Reminder.application_id == application_id)

    upcoming = list(
        db.session.scalars(
            base.where(Reminder.completed.is_(False), Reminder.reminder_date >= boundary)
            .order_by(Reminder.reminder_date.asc(), Reminder.id.asc())
        )
    )
    overdue = list(
        db.session.scalars(
            base.where(Reminder.completed.is_(False), Reminder.reminder_date < boundary)
            .order_by(Reminder.reminder_date.desc(), Reminder.id.desc())
        )
    )
    completed = list(
        db.session.scalars(
            base.where(Reminder.completed.is_(True))
            .order_by(Reminder.reminder_date.desc(), Reminder.id.desc())
        )
    )
    return ReminderGroups(upcoming=upcoming, overdue=overdue, completed=completed)


def parse_reminder_form(form: Mapping[str, str]) -> tuple[dict, dict[str, str]]:
    values: dict = {}
    errors: dict[str, str] = {}

    raw_type = form.get("reminder_type", "")
    try:
        values["reminder_type"] = ReminderType(raw_type)
    except ValueError:
        errors["reminder_type"] = "Select a valid reminder type."

    raw_date = form.get("reminder_date", "").strip()
    if not raw_date:
        errors["reminder_date"] = "Reminder date and time are required."
    else:
        try:
            reminder_date = datetime.fromisoformat(raw_date)
            if reminder_date.tzinfo is not None:
                raise ValueError
            values["reminder_date"] = reminder_date
        except ValueError:
            errors["reminder_date"] = "Enter a valid local date and time."

    notes = form.get("notes", "").strip() or None
    if notes and len(notes) > 5000:
        errors["notes"] = "Notes must be 5,000 characters or fewer."
    values["notes"] = notes
    return values, errors


def create_reminder(
    application: Application, form: Mapping[str, str]
) -> tuple[Reminder | None, dict[str, str]]:
    values, errors = parse_reminder_form(form)
    if errors:
        return None, errors
    reminder = Reminder(application=application, completed=False, **values)
    db.session.add(reminder)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return None, {"form": "The reminder could not be saved. Please try again."}
    return reminder, {}


def update_reminder(reminder: Reminder, form: Mapping[str, str]) -> dict[str, str]:
    values, errors = parse_reminder_form(form)
    if errors:
        return errors
    for field, value in values.items():
        setattr(reminder, field, value)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return {"form": "The reminder could not be updated. Please try again."}
    return {}


def set_reminder_completion(reminder: Reminder, completed: bool) -> bool:
    reminder.completed = completed
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return False
    return True


def delete_reminder(reminder: Reminder) -> bool:
    db.session.delete(reminder)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return False
    return True
