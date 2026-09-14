from pathlib import Path

from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

from config import Config, sqlite_uri

db = SQLAlchemy()
csrf = CSRFProtect()


def create_app(test_config: dict | None = None) -> Flask:
    """Create and configure a JobTracker application instance."""

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    app.config.from_mapping(SQLALCHEMY_DATABASE_URI=sqlite_uri(app.instance_path))

    if test_config:
        app.config.from_mapping(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)

    from app.routes.main import main_bp

    app.register_blueprint(main_bp)

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(_error):
        return render_template("errors/500.html"), 500

    return app

