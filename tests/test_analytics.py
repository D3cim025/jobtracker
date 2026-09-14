from datetime import date

from app import db
from app.models import Application, ApplicationStatus, JobType, WorkSetup
from app.services.analytics_service import analytics_data


def add_application(company, status=ApplicationStatus.SAVED, applied=None, **values):
    item = Application(
        company_name=company, position_title="Engineer", status=status,
        date_applied=applied, **values,
    )
    db.session.add(item)
    db.session.commit()
    return item


def test_analytics_page_loads_empty_state_without_invalid_numbers(client):
    response = client.get("/analytics")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "No applications to analyze yet" in body
    assert "NaN" not in body and "Infinity" not in body


def test_analytics_total_status_counts_and_rates(app, client):
    with app.app_context():
        statuses = [
            ApplicationStatus.ASSESSMENT, ApplicationStatus.INTERVIEW,
            ApplicationStatus.OFFER, ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        ]
        for index, status in enumerate(statuses):
            add_application(f"Co {index}", status=status, applied=date(2026, 9, 1))
        add_application("Draft", status=ApplicationStatus.SAVED, applied=None)
        data = analytics_data()
        assert data.total == 6 and data.applied_total == 5
        assert {metric.label: metric.count for metric in data.statuses}["Saved"] == 1
        assert all(metric.count == 1 and metric.percentage == 20 for metric in data.rates)
    body = client.get("/analytics").get_data(as_text=True)
    assert "Each rate is the percentage of applications with a date applied" in body
    assert body.count("20.0%") >= 5


def test_missing_applied_dates_are_excluded_from_trends_and_denominator(app, client):
    with app.app_context():
        add_application("Draft Offer", status=ApplicationStatus.OFFER)
        data = analytics_data()
        assert data.applied_total == 0
        assert data.weekly == [] and data.monthly == []
        assert all(rate.percentage is None for rate in data.rates)
    body = client.get("/analytics").get_data(as_text=True)
    assert "No applied applications yet" in body
    assert "Not enough data" in body
    assert "NaN" not in body and "Infinity" not in body


def test_week_and_month_trends_handle_boundaries_and_older_dates(app):
    with app.app_context():
        for value in (date(2025, 12, 31), date(2026, 1, 1), date(2026, 1, 5), date(2026, 2, 1)):
            add_application(str(value), status=ApplicationStatus.APPLIED, applied=value)
        data = analytics_data()
        assert [(point.label, point.count) for point in data.weekly] == [
            ("2026-W01", 2), ("2026-W02", 1), ("2026-W05", 1)
        ]
        assert [(point.label, point.count) for point in data.monthly] == [
            ("2025-12", 1), ("2026-01", 2), ("2026-02", 1)
        ]


def test_job_type_work_setup_and_source_breakdowns(app, client):
    with app.app_context():
        add_application("One", job_type=JobType.CONTRACT, work_setup=WorkSetup.REMOTE, source="Referral")
        add_application("Two", job_type=JobType.CONTRACT, work_setup=WorkSetup.HYBRID, source="")
        add_application("Three", job_type=JobType.FULL_TIME, work_setup=WorkSetup.REMOTE, source=None)
        data = analytics_data()
        assert {x.label: x.count for x in data.job_types}["Contract"] == 2
        assert {x.label: x.count for x in data.work_setups}["Remote"] == 2
        assert {x.label: x.count for x in data.sources} == {"Not specified": 2, "Referral": 1}
    body = client.get("/analytics").get_data(as_text=True)
    assert "Applications by job type" in body and "Applications by work setup" in body
    assert "Not specified" in body


def test_small_dataset_renders_accessible_text_with_local_css_chart(app, client):
    with app.app_context():
        add_application("Solo", status=ApplicationStatus.APPLIED, applied=date.today())
    body = client.get("/analytics").get_data(as_text=True)
    assert "Applications per week" in body and "Applications per month" in body
    assert "1 application" in body
    assert "bar-track" in body
    assert "cdn" not in body.lower()


def test_analytics_is_read_only_and_dashboard_link_is_live(app, client):
    with app.app_context():
        add_application("Unchanged")
    assert client.post("/analytics").status_code == 405
    assert 'href="/analytics"' in client.get("/").get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Application.id))) == 1
