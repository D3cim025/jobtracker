from __future__ import annotations

from datetime import datetime
from typing import Mapping

from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import Application, TimelineEvent, TimelineEventType


def parse_timeline_form(
    form: Mapping[str, str],
) -> tuple[dict, dict[str, str]]:
    values: dict = {}
    errors: dict[str, str] = {}

    raw_type = form.get("event_type", "")
    try:
        values["event_type"] = TimelineEventType(raw_type)
    except ValueError:
        errors["event_type"] = "Select a valid event type."

    raw_date = form.get("event_date", "").strip()
    if not raw_date:
        errors["event_date"] = "Event date and time are required."
    else:
        try:
            event_date = datetime.fromisoformat(raw_date)
            if event_date.tzinfo is not None:
                raise ValueError
            values["event_date"] = event_date
        except ValueError:
            errors["event_date"] = "Enter a valid local date and time."

    notes = form.get("notes", "").strip() or None
    if notes and len(notes) > 5000:
        errors["notes"] = "Notes must be 5,000 characters or fewer."
    values["notes"] = notes
    return values, errors


def create_timeline_event(
    application: Application, form: Mapping[str, str]
) -> tuple[TimelineEvent | None, dict[str, str]]:
    values, errors = parse_timeline_form(form)
    if errors:
        return None, errors
    event = TimelineEvent(application=application, **values)
    db.session.add(event)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return None, {"form": "The timeline event could not be saved. Please try again."}
    return event, {}


def update_timeline_event(
    event: TimelineEvent, form: Mapping[str, str]
) -> dict[str, str]:
    values, errors = parse_timeline_form(form)
    if errors:
        return errors
    for field, value in values.items():
        setattr(event, field, value)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return {"form": "The timeline event could not be updated. Please try again."}
    return {}


def delete_timeline_event(event: TimelineEvent) -> bool:
    db.session.delete(event)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return False
    return True
