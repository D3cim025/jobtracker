from datetime import date

from app import create_app, db
from app.models import Application, ApplicationStatus, JobType, Priority, WorkSetup


def valid_form(**overrides):
    data = {
        "company_name": "Acme Labs",
        "position_title": "Backend Developer",
        "job_type": "Full-time",
        "work_setup": "Remote",
        "salary_min": "50000",
        "salary_max": "75000",
        "currency": "php",
        "job_url": "https://example.com/jobs/123",
        "source": "Company Website",
        "date_found": "2026-09-10",
        "date_applied": "2026-09-12",
        "status": "Applied",
        "priority": "High",
        "location": "Manila",
        "contact_name": "Alex Recruiter",
        "contact_email": "alex@example.com",
        "contact_phone": "+63 900 000 0000",
        "notes": "Python and SQL role",
    }
    data.update(overrides)
    return data


def add_application(**overrides):
    values = {"company_name": "Acme Labs", "position_title": "Backend Developer"}
    values.update(overrides)
    application = Application(**values)
    db.session.add(application)
    db.session.commit()
    return application


def test_application_list_has_empty_state_and_create_action(client):
    response = client.get("/applications")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "No applications found" in body
    assert "/applications/new" in body


def test_create_application_persists_validated_fields(app, client):
    response = client.post("/applications/new", data=valid_form(), follow_redirects=False)
    assert response.status_code == 302
    with app.app_context():
        application = db.session.scalar(db.select(Application))
        assert application.company_name == "Acme Labs"
        assert application.currency == "PHP"
        assert application.status is ApplicationStatus.APPLIED
        assert application.priority is Priority.HIGH
        assert application.job_type is JobType.FULL_TIME
        assert application.work_setup is WorkSetup.REMOTE
        assert application.date_applied == date(2026, 9, 12)
        assert response.headers["Location"].endswith(f"/applications/{application.id}")


def test_create_rejects_missing_required_fields(app, client):
    response = client.post(
        "/applications/new",
        data=valid_form(company_name=" ", position_title=""),
    )
    assert response.status_code == 200
    assert "Company is required" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Application.id))) == 0


def test_create_rejects_invalid_enum_url_email_salary_and_date(app, client):
    response = client.post(
        "/applications/new",
        data=valid_form(
            status="Pending",
            job_url="javascript:alert(1)",
            contact_email="invalid",
            salary_min="90000",
            salary_max="50000",
            date_found="not-a-date",
        ),
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Select a valid option" in body
    assert "complete http:// or https:// URL" in body
    assert "valid email address" in body
    assert "Maximum salary" in body
    assert "valid date" in body
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Application.id))) == 0


def test_validation_preserves_submitted_values(client):
    response = client.post(
        "/applications/new", data=valid_form(company_name="", notes="Keep this text")
    )
    body = response.get_data(as_text=True)
    assert "Keep this text" in body
    assert "Backend Developer" in body


def test_detail_displays_application_information(app, client):
    with app.app_context():
        application_id = add_application(
            location="Cebu", source="Referral", notes="Contact after Friday"
        ).id
    response = client.get(f"/applications/{application_id}")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Acme Labs" in body
    assert "Backend Developer" in body
    assert "Cebu" in body
    assert "Referral" in body
    assert "Contact after Friday" in body


def test_missing_application_returns_friendly_404(client):
    response = client.get("/applications/9999")
    assert response.status_code == 404
    assert "That page isn’t here" in response.get_data(as_text=True)


def test_edit_updates_existing_application_without_creating_another(app, client):
    with app.app_context():
        application_id = add_application().id
    response = client.post(
        f"/applications/{application_id}/edit",
        data=valid_form(company_name="Updated Co", position_title="Platform Engineer"),
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        application = db.session.get(Application, application_id)
        assert application.company_name == "Updated Co"
        assert application.position_title == "Platform Engineer"
        assert db.session.scalar(db.select(db.func.count(Application.id))) == 1


def test_invalid_edit_does_not_change_persisted_application(app, client):
    with app.app_context():
        application_id = add_application().id
    response = client.post(
        f"/applications/{application_id}/edit",
        data=valid_form(company_name=""),
    )
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(Application, application_id).company_name == "Acme Labs"


def test_delete_requires_post_and_removes_selected_application(app, client):
    with app.app_context():
        application_id = add_application().id
    assert client.get(f"/applications/{application_id}/delete").status_code == 405
    response = client.post(
        f"/applications/{application_id}/delete", follow_redirects=True
    )
    assert response.status_code == 200
    assert "Application deleted" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Application, application_id) is None


def test_status_change_updates_only_status(app, client):
    with app.app_context():
        application = add_application(priority=Priority.HIGH)
        application_id = application.id
    response = client.post(
        f"/applications/{application_id}/status",
        data={"status": "Interview"},
        follow_redirects=True,
    )
    assert "Status updated" in response.get_data(as_text=True)
    with app.app_context():
        application = db.session.get(Application, application_id)
        assert application.status is ApplicationStatus.INTERVIEW
        assert application.priority is Priority.HIGH


def test_priority_change_and_invalid_choice_handling(app, client):
    with app.app_context():
        application_id = add_application().id
    response = client.post(
        f"/applications/{application_id}/priority",
        data={"priority": "High"},
        follow_redirects=True,
    )
    assert "Priority updated" in response.get_data(as_text=True)
    invalid = client.post(
        f"/applications/{application_id}/priority",
        data={"priority": "Urgent"},
        follow_redirects=True,
    )
    assert "Select a valid priority" in invalid.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Application, application_id).priority is Priority.HIGH


def test_search_matches_each_supported_text_field(app, client):
    with app.app_context():
        add_application(
            company_name="Northstar",
            position_title="Data Engineer",
            location="Davao",
            contact_name="Morgan Lee",
            notes="Uses Snowflake",
        )
        add_application(company_name="Unrelated", position_title="Designer")
    for term in ("northstar", "Data Engineer", "Davao", "Morgan", "Snowflake"):
        body = client.get("/applications", query_string={"q": term}).get_data(as_text=True)
        assert "Northstar" in body
        assert "Unrelated" not in body


def test_filters_status_priority_job_type_work_setup_and_source(app, client):
    with app.app_context():
        add_application(
            company_name="Target Co",
            status=ApplicationStatus.INTERVIEW,
            priority=Priority.HIGH,
            job_type=JobType.CONTRACT,
            work_setup=WorkSetup.HYBRID,
            source="LinkedIn",
        )
        add_application(company_name="Other Co", source="Referral")
    response = client.get(
        "/applications",
        query_string={
            "status": "Interview",
            "priority": "High",
            "job_type": "Contract",
            "work_setup": "Hybrid",
            "source": "LinkedIn",
        },
    )
    body = response.get_data(as_text=True)
    assert "Target Co" in body
    assert "Other Co" not in body


def test_date_applied_range_filter(app, client):
    with app.app_context():
        add_application(company_name="Inside", date_applied=date(2026, 9, 15))
        add_application(company_name="Before", date_applied=date(2026, 8, 31))
        add_application(company_name="After", date_applied=date(2026, 10, 1))
        add_application(company_name="Not Applied", date_applied=None)
    body = client.get(
        "/applications",
        query_string={"date_from": "2026-09-01", "date_to": "2026-09-30"},
    ).get_data(as_text=True)
    assert "Inside" in body
    assert "Before" not in body
    assert "After" not in body
    assert "Not Applied" not in body


def test_sorting_uses_whitelisted_column_and_direction(app, client):
    with app.app_context():
        add_application(company_name="Zulu")
        add_application(company_name="Alpha")
    ascending = client.get(
        "/applications", query_string={"sort": "company", "direction": "asc"}
    ).get_data(as_text=True)
    descending = client.get(
        "/applications", query_string={"sort": "company", "direction": "desc"}
    ).get_data(as_text=True)
    assert ascending.index("Alpha") < ascending.index("Zulu")
    assert descending.index("Zulu") < descending.index("Alpha")
    assert client.get(
        "/applications", query_string={"sort": "company_name; DROP TABLE applications"}
    ).status_code == 200


def test_list_escapes_user_controlled_content(app, client):
    with app.app_context():
        add_application(company_name="<script>alert(1)</script>")
    body = client.get("/applications").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body


def test_application_mutations_require_csrf_when_protection_is_enabled(tmp_path):
    protected_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "csrf-test-secret",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'csrf.db').as_posix()}",
        }
    )
    response = protected_app.test_client().post("/applications/new", data=valid_form())
    assert response.status_code == 400
