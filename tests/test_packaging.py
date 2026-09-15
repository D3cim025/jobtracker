from pathlib import Path

from sqlalchemy import inspect

import launcher
from app import create_app, db


def test_factory_honors_packaged_persistent_paths(monkeypatch, tmp_path):
    instance_path = tmp_path / "persistent" / "instance"
    upload_path = tmp_path / "persistent" / "uploads"
    monkeypatch.setenv("JOBTRACKER_INSTANCE_PATH", str(instance_path))
    monkeypatch.setenv("JOBTRACKER_UPLOAD_ROOT", str(upload_path))

    application = create_app({"TESTING": True, "SECRET_KEY": "packaging-test"})

    assert Path(application.instance_path) == instance_path
    assert Path(application.config["UPLOAD_ROOT"]) == upload_path
    assert (upload_path / "resumes").is_dir()
    assert (upload_path / "documents").is_dir()


def test_packaged_first_launch_initializes_database_without_replacing_it(monkeypatch, tmp_path):
    root = tmp_path / "JobTrackerData"
    monkeypatch.setenv("JOBTRACKER_DATA_ROOT", str(root))

    first_app = launcher.create_packaged_app(root)
    with first_app.app_context():
        assert inspect(db.engine).has_table("applications")
        database_path = Path(first_app.instance_path) / "jobtracker.db"
        assert database_path.is_file()
        original_bytes = database_path.read_bytes()

    second_app = launcher.create_packaged_app(root)
    with second_app.app_context():
        assert inspect(db.engine).has_table("applications")
        assert database_path.read_bytes() == original_bytes


def test_launcher_uses_local_app_data_and_loopback_only(monkeypatch, tmp_path):
    monkeypatch.delenv("JOBTRACKER_DATA_ROOT", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert launcher.data_root() == (tmp_path / "JobTracker").resolve()
    assert launcher.HOST == "127.0.0.1"
    assert launcher.URL == "http://127.0.0.1:5000"


def test_duplicate_launch_opens_existing_page_without_creating_app(monkeypatch):
    opened = []
    monkeypatch.setattr(launcher, "jobtracker_is_running", lambda: True)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url, new: opened.append((url, new)))
    monkeypatch.setattr(
        launcher,
        "create_packaged_app",
        lambda _root: (_ for _ in ()).throw(AssertionError("must not create another app")),
    )

    assert launcher.main() == 0
    assert opened == [(launcher.URL, 1)]


def test_startup_failure_uses_native_error_path(monkeypatch, tmp_path):
    errors = []
    monkeypatch.setattr(launcher, "jobtracker_is_running", lambda: False)
    monkeypatch.setattr(launcher, "data_root", lambda: tmp_path)
    monkeypatch.setattr(
        launcher,
        "create_packaged_app",
        lambda _root: (_ for _ in ()).throw(OSError("private technical detail")),
    )
    monkeypatch.setattr(launcher, "show_startup_error", lambda: errors.append("shown"))

    assert launcher.main() == 1
    assert errors == ["shown"]
