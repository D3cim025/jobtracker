import os
import secrets
from pathlib import Path

import click
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

from config import Config, sqlite_uri

db = SQLAlchemy()
csrf = CSRFProtect()


def installation_secret(instance_path: str) -> str:
    secret_path = Path(instance_path) / ".secret_key"
    try:
        secret = secret_path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        secret = secrets.token_hex(32)
        try:
            with secret_path.open("x", encoding="ascii") as secret_file:
                secret_file.write(secret)
        except FileExistsError:
            try:
                secret = secret_path.read_text(encoding="ascii").strip()
            except OSError as error:
                raise RuntimeError("JobTracker could not read its local secret key.") from error
        except OSError as error:
            raise RuntimeError("JobTracker could not create its local secret key.") from error
    if len(secret) < 32:
        raise RuntimeError("JobTracker's local secret key is invalid.")
    return secret


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    """Make SQLite enforce the foreign keys declared by the models."""

    if dbapi_connection.__class__.__module__ == "sqlite3":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_app(test_config: dict | None = None) -> Flask:
    """Create and configure a JobTracker application instance."""

    instance_path = os.environ.get("JOBTRACKER_INSTANCE_PATH")
    app = Flask(
        __name__,
        instance_relative_config=True,
        instance_path=instance_path,
    )
    app.config.from_object(Config)
    if upload_root := os.environ.get("JOBTRACKER_UPLOAD_ROOT"):
        app.config["UPLOAD_ROOT"] = upload_root
    app.config.from_mapping(SQLALCHEMY_DATABASE_URI=sqlite_uri(app.instance_path))

    if test_config:
        app.config.from_mapping(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = installation_secret(app.instance_path)
    (Path(app.config["UPLOAD_ROOT"]) / "resumes").mkdir(parents=True, exist_ok=True)
    (Path(app.config["UPLOAD_ROOT"]) / "documents").mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)

    # Importing the models registers their tables with SQLAlchemy metadata.
    from app import models  # noqa: F401

    from app.routes.main import main_bp
    from app.routes.applications import applications_bp
    from app.routes.resumes import resumes_bp
    from app.routes.documents import documents_bp
    from app.routes.timeline import timeline_bp
    from app.routes.reminders import reminders_bp
    from app.routes.analytics import analytics_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(applications_bp)
    app.register_blueprint(resumes_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(timeline_bp)
    app.register_blueprint(reminders_bp)
    app.register_blueprint(analytics_bp)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.cli.command("init-db")
    def init_db_command():
        """Create missing database tables without replacing existing data."""

        db.create_all()
        click.echo("Initialized the JobTracker database.")

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(_error):
        return render_template("errors/500.html"), 500

    return app
