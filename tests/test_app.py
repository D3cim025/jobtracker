from pathlib import Path

from app import create_app


def test_factory_uses_testing_configuration(tmp_path):
    database = tmp_path / "factory.db"
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}"})
    assert app.testing is True
    assert app.config["SQLALCHEMY_DATABASE_URI"].endswith("factory.db")


def test_default_database_is_local_to_instance_directory():
    app = create_app({"TESTING": True})
    expected = (Path(app.instance_path) / "jobtracker.db").as_posix()
    assert app.config["SQLALCHEMY_DATABASE_URI"] == f"sqlite:///{expected}"


def test_home_renders_product_shell_and_local_assets(client):
    response = client.get("/")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Keep your job search clear" in body
    assert 'href="/static/css/app.css"' in body
    assert 'src="/static/js/app.js"' in body
    assert "https://" not in body


def test_health_reports_service_status(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"service": "jobtracker", "status": "healthy"}


def test_unknown_route_has_friendly_404(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert "That page isn’t here" in response.get_data(as_text=True)


def test_required_static_assets_are_served(client):
    css = client.get("/static/css/app.css")
    javascript = client.get("/static/js/app.js")
    assert css.status_code == 200
    assert "--accent" in css.get_data(as_text=True)
    assert javascript.status_code == 200
    assert "jobtracker-theme" in javascript.get_data(as_text=True)

