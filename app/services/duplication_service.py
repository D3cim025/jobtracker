from __future__ import annotations

from datetime import date
from typing import Mapping

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import Application, ApplicationStatus
from app.services.application_service import parse_application_form


def duplication_defaults(source: Application) -> dict[str, str]:
    """Return only fields that are safe to offer for reuse."""
    return {
        "company_name": "",
        "position_title": source.position_title,
        "job_type": source.job_type.value,
        "work_setup": source.work_setup.value,
        "location": source.location or "",
        "salary_min": str(source.salary_min) if source.salary_min is not None else "",
        "salary_max": str(source.salary_max) if source.salary_max is not None else "",
        "currency": source.currency,
        "priority": source.priority.value,
        "source": source.source or "",
        "resume_id": str(source.resume_id) if source.resume_id is not None else "",
        "notes": "",
    }


def parse_duplication_form(
    form: Mapping[str, str], source: Application
) -> tuple[dict, dict[str, str]]:
    """Validate reusable input while forcing non-reusable fields to safe defaults."""
    reusable = {
        name: form.get(name, "")
        for name in (
            "company_name", "position_title", "job_type", "work_setup", "location",
            "salary_min", "salary_max", "currency", "priority", "source", "resume_id", "notes",
        )
    }
    if form.get("reuse_notes") == "1":
        reusable["notes"] = source.notes or ""
    reusable.update(
        status=ApplicationStatus.SAVED.value,
        date_found=date.today().isoformat(),
        date_applied="",
        job_url="",
        contact_name="",
        contact_email="",
        contact_phone="",
    )
    return parse_application_form(reusable)


def duplicate_matches(values: dict) -> list[Application]:
    company = values.get("company_name", "").strip().lower()
    position = values.get("position_title", "").strip().lower()
    if not company or not position:
        return []
    statement = select(Application).where(
        func.lower(Application.company_name) == company,
        func.lower(Application.position_title) == position,
    ).order_by(Application.id)
    return list(db.session.scalars(statement))


def create_duplicate(values: dict) -> Application | None:
    """Create a fresh application whose owned historical collections start empty."""
    application = Application(**values)
    db.session.add(application)
    try:
        db.session.commit()
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        return None
    return application
