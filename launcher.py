"""Windows launcher for the standalone JobTracker package."""

from __future__ import annotations

import os
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from werkzeug.serving import make_server


HOST = "127.0.0.1"
PORT = 5000
URL = f"http://{HOST}:{PORT}"
HEALTH_URL = f"{URL}/health"


def show_startup_error() -> None:
    """Show a concise native error because windowed builds have no console."""

    message = (
        "JobTracker could not start. Port 5000 may already be in use, "
        "or the local data folder may be unavailable."
    )
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            None,
            message,
            "JobTracker",
            0x00000010,
        )
    except (AttributeError, OSError):
        # This fallback is useful when running launcher.py directly on a
        # non-Windows development system. The packaged target is Windows.
        return


def data_root() -> Path:
    """Return a stable writable data directory outside any bundle extraction."""

    configured = os.environ.get("JOBTRACKER_DATA_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = str(Path.home() / "AppData" / "Local")
    return (Path(local_app_data) / "JobTracker").resolve()


def configure_persistent_paths(root: Path) -> None:
    instance_path = root / "instance"
    upload_path = root / "uploads"
    instance_path.mkdir(parents=True, exist_ok=True)
    upload_path.mkdir(parents=True, exist_ok=True)
    os.environ["JOBTRACKER_INSTANCE_PATH"] = str(instance_path)
    os.environ["JOBTRACKER_UPLOAD_ROOT"] = str(upload_path)


def jobtracker_is_running(timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=timeout) as response:
            return response.status == 200 and b'"service":"jobtracker"' in response.read()
    except (OSError, urllib.error.URLError):
        return False


def wait_and_open_browser(timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if jobtracker_is_running():
            webbrowser.open(URL, new=1)
            return
        time.sleep(0.25)


def create_packaged_app(root: Path):
    configure_persistent_paths(root)

    # Import only after persistent paths are configured. This keeps all writable
    # state out of PyInstaller's bundle and temporary extraction directories.
    from app import create_app, db

    application = create_app()
    with application.app_context():
        db.create_all()
    return application


def main() -> int:
    if jobtracker_is_running():
        webbrowser.open(URL, new=1)
        return 0

    root = data_root()
    try:
        application = create_packaged_app(root)
        server = make_server(HOST, PORT, application, threaded=True)
    except (Exception, SystemExit):
        show_startup_error()
        return 1

    if os.environ.get("JOBTRACKER_OPEN_BROWSER", "1") != "0":
        browser_thread = threading.Thread(target=wait_and_open_browser, daemon=True)
        browser_thread.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
