from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Mapping
from urllib.parse import urlparse

from sqlalchemy import asc, desc, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import (
    Application,
    ApplicationStatus,
    JobType,
    Priority,
    Resume,
    TimelineEvent,
    TimelineEventType,
    WorkSetup,
    utc_now,
)


SORT_COLUMNS = {
    "company": Application.company_name,
    "position": Application.position_title,
    "status": Application.status,
    "priority": Application.priority,
    "date_found": Application.date_found,
    "date_applied": Application.date_applied,
    "updated": Application.updated_at,
}


def list_applications(filters: Mapping[str, str]) -> list[Application]:
    statement = select(Application)
    search = filters.get("q", "").strip()
    if search:
        pattern = f"%{search}%"
        statement = statement.where(
            or_(
                Application.company_name.ilike(pattern),
                Application.position_title.ilike(pattern),
                Application.location.ilike(pattern),
                Application.contact_name.ilike(pattern),
                Application.notes.ilike(pattern),
            )
        )

    enum_filters = {
        "status": (Application.status, ApplicationStatus),
        "priority": (Application.priority, Priority),
        "job_type": (Application.job_type, JobType),
        "work_setup": (Application.work_setup, WorkSetup),
    }
    for name, (column, enum_class) in enum_filters.items():
        raw_value = filters.get(name, "")
        if raw_value:
            try:
                statement = statement.where(column == enum_class(raw_value))
            except ValueError:
                pass

    source = filters.get("source", "").strip()
    if source:
        statement = statement.where(Application.source.ilike(source))

    for name, operator in (("date_from", Application.date_applied.__ge__), ("date_to", Application.date_applied.__le__)):
        raw_date = filters.get(name, "")
        if raw_date:
            try:
                statement = statement.where(operator(date.fromisoformat(raw_date)))
            except ValueError:
                pass

    sort_name = filters.get("sort", "updated")
    sort_column = SORT_COLUMNS.get(sort_name, Application.updated_at)
    direction = asc if filters.get("direction") == "asc" else desc
    statement = statement.order_by(direction(sort_column), desc(Application.id))
    return list(db.session.scalars(statement))


def distinct_sources() -> list[str]:
    statement = (
        select(Application.source)
        .where(Application.source.is_not(None), Application.source != "")
        .distinct()
        .order_by(Application.source)
    )
    return list(db.session.scalars(statement))


def parse_application_form(form: Mapping[str, str]) -> tuple[dict, dict[str, str]]:
    errors: dict[str, str] = {}
    values: dict = {}

    for field, label in (("company_name", "Company"), ("position_title", "Position")):
        value = form.get(field, "").strip()
        if not value:
            errors[field] = f"{label} is required."
        elif len(value) > 200:
            errors[field] = f"{label} must be 200 characters or fewer."
        values[field] = value

    enum_fields = {
        "job_type": (JobType, JobType.FULL_TIME),
        "work_setup": (WorkSetup, WorkSetup.FLEXIBLE_OTHER),
        "status": (ApplicationStatus, ApplicationStatus.SAVED),
        "priority": (Priority, Priority.MEDIUM),
    }
    for field, (enum_class, default) in enum_fields.items():
        raw_value = form.get(field, default.value)
        try:
            values[field] = enum_class(raw_value)
        except ValueError:
            errors[field] = "Select a valid option."

    text_limits = {
        "location": 250,
        "source": 100,
        "contact_name": 200,
        "contact_email": 320,
        "contact_phone": 50,
    }
    for field, maximum in text_limits.items():
        value = form.get(field, "").strip()
        if len(value) > maximum:
            errors[field] = f"Must be {maximum} characters or fewer."
        values[field] = value or None
    values["notes"] = form.get("notes", "").strip() or None

    currency = form.get("currency", "PHP").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        errors["currency"] = "Use a three-letter currency code such as PHP or USD."
    values["currency"] = currency

    for field in ("salary_min", "salary_max"):
        raw_value = form.get(field, "").strip()
        try:
            value = Decimal(raw_value) if raw_value else None
            if value is not None and value < 0:
                raise InvalidOperation
            values[field] = value
        except InvalidOperation:
            errors[field] = "Enter a non-negative amount."

    if (
        values.get("salary_min") is not None
        and values.get("salary_max") is not None
        and values["salary_min"] > values["salary_max"]
    ):
        errors["salary_max"] = "Maximum salary must be at least the minimum salary."

    for field in ("date_found", "date_applied"):
        raw_value = form.get(field, "").strip()
        if not raw_value and field == "date_found":
            values[field] = date.today()
        elif not raw_value:
            values[field] = None
        else:
            try:
                values[field] = date.fromisoformat(raw_value)
            except ValueError:
                errors[field] = "Enter a valid date."

    job_url = form.get("job_url", "").strip()
    if job_url:
        parsed = urlparse(job_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors["job_url"] = "Enter a complete http:// or https:// URL."
        elif len(job_url) > 2048:
            errors["job_url"] = "URL is too long."
    values["job_url"] = job_url or None

    email = values.get("contact_email")
    if email and ("@" not in email or email.startswith("@") or email.endswith("@")):
        errors["contact_email"] = "Enter a valid email address."

    raw_resume_id = form.get("resume_id", "").strip()
    if not raw_resume_id:
        values["resume_id"] = None
    else:
        try:
            resume_id = int(raw_resume_id)
        except ValueError:
            errors["resume_id"] = "Select a valid resume."
        else:
            if db.session.get(Resume, resume_id) is None:
                errors["resume_id"] = "The selected resume no longer exists."
            else:
                values["resume_id"] = resume_id

    return values, errors


def save_application(application: Application, values: dict) -> bool:
    for field, value in values.items():
        setattr(application, field, value)
    db.session.add(application)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return False
    return True


def delete_application(application: Application) -> bool:
    from app.services.document_service import (
        finalize_quarantined_files,
        prepare_application_document_deletion,
        restore_quarantined_files,
    )

    try:
        moved_files = prepare_application_document_deletion(application)
    except (OSError, ValueError):
        return False
    db.session.delete(application)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        try:
            restore_quarantined_files(moved_files)
        except OSError:
            pass
        return False
    finalize_quarantined_files(moved_files)
    return True


def update_application_choice(application: Application, field: str, raw_value: str) -> bool:
    allowed = {"status": ApplicationStatus, "priority": Priority}
    enum_class = allowed.get(field)
    if enum_class is None:
        return False
    try:
        new_value = enum_class(raw_value)
    except ValueError:
        return False
    old_value = getattr(application, field)
    setattr(application, field, new_value)
    if field == "status" and new_value != old_value:
        application.timeline_events.append(
            TimelineEvent(
                event_type=TimelineEventType.STATUS_CHANGED,
                event_date=utc_now(),
                notes=f"Status changed from {old_value.value} to {new_value.value}.",
            )
        )
    return save_application(application, {})
