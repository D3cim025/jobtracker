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


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    """Make SQLite enforce the foreign keys declared by the models."""

    if dbapi_connection.__class__.__module__ == "sqlite3":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_app(test_config: dict | None = None) -> Flask:
    """Create and configure a JobTracker application instance."""

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    app.config.from_mapping(SQLALCHEMY_DATABASE_URI=sqlite_uri(app.instance_path))

    if test_config:
        app.config.from_mapping(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
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

    app.register_blueprint(main_bp)
    app.register_blueprint(applications_bp)
    app.register_blueprint(resumes_bp)
    app.register_blueprint(documents_bp)

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
