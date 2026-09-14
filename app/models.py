from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Text, event, inspect
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app import db


def utc_now() -> datetime:
    """Return a naive UTC value, which SQLite stores consistently."""

    return datetime.now(UTC).replace(tzinfo=None)


class ValueEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ApplicationStatus(ValueEnum):
    SAVED = "Saved"
    APPLIED = "Applied"
    ASSESSMENT = "Assessment"
    INTERVIEW = "Interview"
    OFFER = "Offer"
    REJECTED = "Rejected"
    WITHDRAWN = "Withdrawn"


class Priority(ValueEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class JobType(ValueEnum):
    FULL_TIME = "Full-time"
    PART_TIME = "Part-time"
    INTERNSHIP = "Internship"
    CONTRACT = "Contract"
    FREELANCE = "Freelance"
    TEMPORARY = "Temporary"
    OTHER = "Other"


class WorkSetup(ValueEnum):
    REMOTE = "Remote"
    HYBRID = "Hybrid"
    ON_SITE = "On-site"
    FLEXIBLE_OTHER = "Flexible / Other"


class DocumentType(ValueEnum):
    RESUME = "Resume"
    COVER_LETTER = "Cover Letter"
    PORTFOLIO = "Portfolio"
    CERTIFICATE = "Certificate"
    JOB_DESCRIPTION = "Job Description"
    ASSESSMENT = "Assessment"
    OTHER = "Other"


class TimelineEventType(ValueEnum):
    APPLICATION_SUBMITTED = "Application submitted"
    ASSESSMENT_RECEIVED = "Assessment received"
    ASSESSMENT_COMPLETED = "Assessment completed"
    INTERVIEW_SCHEDULED = "Interview scheduled"
    INTERVIEW_COMPLETED = "Interview completed"
    FOLLOW_UP_SENT = "Follow-up sent"
    OFFER_RECEIVED = "Offer received"
    REJECTION_RECEIVED = "Rejection received"
    STATUS_CHANGED = "Status changed"
    CUSTOM = "Custom event"


class ReminderType(ValueEnum):
    FOLLOW_UP = "Follow-up"
    INTERVIEW = "Interview"
    ASSESSMENT_DEADLINE = "Assessment deadline"
    APPLICATION_DEADLINE = "Application deadline"
    CUSTOM = "Custom"


def enum_type(enum_class: type[ValueEnum], name: str) -> SqlEnum:
    return SqlEnum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )


class Application(TimestampMixin, db.Model):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint("salary_min IS NULL OR salary_min >= 0", name="ck_application_salary_min"),
        CheckConstraint("salary_max IS NULL OR salary_max >= 0", name="ck_application_salary_max"),
        CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max",
            name="ck_application_salary_range",
        ),
        Index("ix_application_company_position", "company_name", "position_title"),
        Index("ix_application_status_priority", "status", "priority"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    position_title: Mapped[str] = mapped_column(String(200), nullable=False)
    job_type: Mapped[JobType] = mapped_column(
        enum_type(JobType, "job_type"), default=JobType.FULL_TIME, nullable=False
    )
    location: Mapped[str | None] = mapped_column(String(250))
    work_setup: Mapped[WorkSetup] = mapped_column(
        enum_type(WorkSetup, "work_setup"), default=WorkSetup.FLEXIBLE_OTHER, nullable=False
    )
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="PHP", nullable=False)
    job_url: Mapped[str | None] = mapped_column(String(2048))
    source: Mapped[str | None] = mapped_column(String(100), index=True)
    date_found: Mapped[date] = mapped_column(Date, default=date.today, nullable=False, index=True)
    date_applied: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[ApplicationStatus] = mapped_column(
        enum_type(ApplicationStatus, "application_status"),
        default=ApplicationStatus.SAVED,
        nullable=False,
    )
    priority: Mapped[Priority] = mapped_column(
        enum_type(Priority, "application_priority"), default=Priority.MEDIUM, nullable=False
    )
    contact_name: Mapped[str | None] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    contact_phone: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="RESTRICT"), index=True
    )

    resume: Mapped[Resume | None] = relationship(back_populates="applications")
    documents: Mapped[list[Document]] = relationship(
        back_populates="application", cascade="all, delete-orphan", passive_deletes=True
    )
    timeline_events: Mapped[list[TimelineEvent]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TimelineEvent.event_date, TimelineEvent.id",
    )
    reminders: Mapped[list[Reminder]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Reminder.reminder_date, Reminder.id",
    )

    @validates("company_name", "position_title")
    def validate_required_text(self, key: str, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError(f"{key.replace('_', ' ').title()} is required.")
        return cleaned

    @validates("currency")
    def validate_currency(self, _key: str, value: str) -> str:
        cleaned = (value or "").strip().upper()
        if len(cleaned) != 3 or not cleaned.isalpha():
            raise ValueError("Currency must be a three-letter code.")
        return cleaned


class Resume(TimestampMixin, db.Model):
    __tablename__ = "resumes"
    __table_args__ = (
        Index("ix_resume_display_version", "display_name", "version_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    original_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_file_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    version_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    target_role: Mapped[str | None] = mapped_column(String(200), index=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), index=True)

    applications: Mapped[list[Application]] = relationship(
        back_populates="resume",
        passive_deletes=True,
        order_by="Application.created_at.desc()",
    )

    @validates("display_name", "original_file_name", "stored_file_name", "version_name")
    def validate_required_text(self, key: str, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError(f"{key.replace('_', ' ').title()} is required.")
        return cleaned

    @validates("file_hash")
    def validate_file_hash(self, _key: str, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = value.strip().lower()
        if len(cleaned) != 64 or any(character not in "0123456789abcdef" for character in cleaned):
            raise ValueError("File hash must be a SHA-256 hexadecimal digest.")
        return cleaned


@event.listens_for(Resume, "before_update")
def preserve_resume_file_identity(_mapper, _connection, resume: Resume) -> None:
    """A stored resume file is immutable after its version record is created."""

    state = inspect(resume)
    immutable_fields = ("original_file_name", "stored_file_name", "file_hash")
    if any(state.attrs[field].history.has_changes() for field in immutable_fields):
        raise ValueError(
            "Resume file identity cannot be changed. Upload a new resume version instead."
        )


class Document(db.Model):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_document_application_type", "application_id", "document_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    document_type: Mapped[DocumentType] = mapped_column(
        enum_type(DocumentType, "document_type"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    original_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    application: Mapped[Application] = relationship(back_populates="documents")

    @validates("file_path", "original_file_name")
    def validate_required_text(self, key: str, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError(f"{key.replace('_', ' ').title()} is required.")
        return cleaned


class TimelineEvent(db.Model):
    __tablename__ = "timeline_events"
    __table_args__ = (Index("ix_timeline_application_date", "application_id", "event_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[TimelineEventType] = mapped_column(
        enum_type(TimelineEventType, "timeline_event_type"), nullable=False
    )
    event_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    application: Mapped[Application] = relationship(back_populates="timeline_events")


class Reminder(db.Model):
    __tablename__ = "reminders"
    __table_args__ = (
        Index("ix_reminder_completed_date", "completed", "reminder_date"),
        Index("ix_reminder_application_date", "application_id", "reminder_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    reminder_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reminder_type: Mapped[ReminderType] = mapped_column(
        enum_type(ReminderType, "reminder_type"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    completed: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    application: Mapped[Application] = relationship(back_populates="reminders")


class Setting(TimestampMixin, db.Model):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    @validates("key")
    def validate_key(self, _key: str, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("Setting key is required.")
        return cleaned
