import os
from pathlib import Path


class Config:
    """Default local configuration. Override values through the app factory."""

    SECRET_KEY = os.environ.get("JOBTRACKER_SECRET_KEY", "local-development-only-change-me")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    UPLOAD_ROOT = str(Path(__file__).resolve().parent / "uploads")


def sqlite_uri(instance_path: str) -> str:
    database_path = Path(instance_path) / "jobtracker.db"
    return f"sqlite:///{database_path.as_posix()}"
