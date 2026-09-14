from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select

from app import db
from app.models import Application, ApplicationStatus, JobType, WorkSetup


@dataclass(frozen=True)
class Metric:
    label: str
    count: int
    percentage: Decimal | None


@dataclass(frozen=True)
class TrendPoint:
    label: str
    count: int
    relative_width: int


@dataclass(frozen=True)
class AnalyticsData:
    total: int
    applied_total: int
    weekly: list[TrendPoint]
    monthly: list[TrendPoint]
    rates: list[Metric]
    statuses: list[Metric]
    job_types: list[Metric]
    work_setups: list[Metric]
    sources: list[Metric]


def _percentage(count: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return (Decimal(count * 100) / Decimal(denominator)).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )


def _metrics(rows, labels: list[str], total: int) -> list[Metric]:
    counts = {str(label): count for label, count in rows}
    return [Metric(label, counts.get(label, 0), _percentage(counts.get(label, 0), total)) for label in labels]


def _trend_points(buckets: dict[str, int]) -> list[TrendPoint]:
    maximum = max(buckets.values(), default=0)
    return [
        TrendPoint(label, count, round(count * 100 / maximum) if maximum else 0)
        for label, count in sorted(buckets.items())
    ]


def analytics_data() -> AnalyticsData:
    total = db.session.scalar(select(func.count(Application.id))) or 0
    applied_total = db.session.scalar(
        select(func.count(Application.id)).where(Application.date_applied.is_not(None))
    ) or 0

    status_rows = db.session.execute(
        select(Application.status, func.count(Application.id)).group_by(Application.status)
    ).all()
    status_counts = {status: count for status, count in status_rows}
    statuses = [
        Metric(status.value, status_counts.get(status, 0), _percentage(status_counts.get(status, 0), total))
        for status in ApplicationStatus
    ]
    rate_statuses = (
        ApplicationStatus.ASSESSMENT, ApplicationStatus.INTERVIEW, ApplicationStatus.OFFER,
        ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN,
    )
    applied_status_rows = dict(db.session.execute(
        select(Application.status, func.count(Application.id))
        .where(Application.date_applied.is_not(None), Application.status.in_(rate_statuses))
        .group_by(Application.status)
    ).all())
    rates = [
        Metric(f"{status.value} rate", applied_status_rows.get(status, 0), _percentage(applied_status_rows.get(status, 0), applied_total))
        for status in rate_statuses
    ]

    date_rows = db.session.execute(
        select(Application.date_applied, func.count(Application.id))
        .where(Application.date_applied.is_not(None))
        .group_by(Application.date_applied)
    ).all()
    weekly_buckets: dict[str, int] = {}
    monthly_buckets: dict[str, int] = {}
    for applied_date, count in date_rows:
        iso_year, iso_week, _ = applied_date.isocalendar()
        week_label = f"{iso_year}-W{iso_week:02d}"
        month_label = applied_date.strftime("%Y-%m")
        weekly_buckets[week_label] = weekly_buckets.get(week_label, 0) + count
        monthly_buckets[month_label] = monthly_buckets.get(month_label, 0) + count

    job_rows = db.session.execute(
        select(Application.job_type, func.count(Application.id)).group_by(Application.job_type)
    ).all()
    work_rows = db.session.execute(
        select(Application.work_setup, func.count(Application.id)).group_by(Application.work_setup)
    ).all()
    source_label = func.coalesce(func.nullif(func.trim(Application.source), ""), "Not specified")
    source_rows = db.session.execute(
        select(source_label, func.count(Application.id)).group_by(source_label).order_by(source_label)
    ).all()
    return AnalyticsData(
        total=total,
        applied_total=applied_total,
        weekly=_trend_points(weekly_buckets),
        monthly=_trend_points(monthly_buckets),
        rates=rates,
        statuses=statuses,
        job_types=_metrics(job_rows, [item.value for item in JobType], total),
        work_setups=_metrics(work_rows, [item.value for item in WorkSetup], total),
        sources=[Metric(label, count, _percentage(count, total)) for label, count in source_rows],
    )
