# JobTracker

JobTracker is a local-first job application management system built with Flask, SQLite, and vanilla JavaScript. It keeps applications, hiring progress, exact resume versions, supporting documents, reminders, and offline analytics together in one private workspace.

## Why it exists

Job searches quickly spread across bookmarks, spreadsheets, calendars, and folders. JobTracker provides one structured record of what you applied for, what you sent, what happened next, and which deadlines still need attention. The computer running JobTracker remains the source of truth.

## Features

- Application creation, editing, search, filtering, sorting, status, and priority tracking
- Application detail pages with contacts, compensation, notes, and job links
- Immutable Resume Library versions with SHA-256 fingerprints and usage history
- Separate, application-specific supporting documents
- Chronological timeline events and automatic status-change history
- Upcoming, overdue, completed, interview, and assessment reminders
- Apply Again workflow that preserves the original application's history
- Dashboard summaries and recent activity
- Read-only weekly/monthly analytics, rates, and breakdowns
- Responsive light and dark interfaces that work fully with local assets
- CSRF protection, guarded file paths, validated uploads, and local security headers

## Technology

- Python 3.12+
- Flask and Flask-WTF
- Flask-SQLAlchemy and SQLite
- Jinja templates
- Vanilla HTML, CSS, and JavaScript
- pytest

No Node.js toolchain, frontend framework, CDN, external API, or cloud service is required.

## Local setup

From PowerShell in the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If script activation is unavailable, use `.\.venv\Scripts\python.exe` directly.

Initialize a fresh database:

```powershell
.\.venv\Scripts\python.exe -m flask --app run.py init-db
```

This creates only missing tables. It never drops or replaces existing data and is not a schema-upgrade command.

Start JobTracker:

```powershell
.\.venv\Scripts\python.exe run.py
```

Open `http://127.0.0.1:5000` and stop the server with `Ctrl+C`. The normal server binds only to the local computer and does not enable debug mode.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pip check
```

Tests use isolated SQLite databases and temporary upload directories.

## Local data and file behavior

- The SQLite database lives at `instance/jobtracker.db`.
- A generated installation secret lives at `instance/.secret_key` unless `JOBTRACKER_SECRET_KEY` is supplied.
- Resume versions live under `uploads/resumes/` with generated storage names.
- Application documents live under `uploads/documents/<application-id>/`.
- Original filenames remain available for display and downloads, but are never used as storage paths.
- Uploading a new resume creates a new immutable version; it never replaces the version linked to an existing application.

The `instance/`, `uploads/`, and `backups/` directories are ignored by Git. Do not move, rename, or delete runtime files manually.

## Security model

JobTracker is intended for one user on one trusted local computer. It uses server-side validation, SQLAlchemy parameter binding, CSRF protection, POST-only mutations, generated upload names, file signature/type checks, resolved-path containment, defensive response headers, and a persistent random installation secret.

Set `JOBTRACKER_SECRET_KEY` before startup only when you need to manage the secret externally. Keep debug mode disabled for real data. JobTracker has no authentication and must not be exposed to a public network.

## Project structure

```text
app/
  __init__.py       Application factory, extensions, and security headers
  models.py         SQLAlchemy entities, constraints, and relationships
  routes/           HTTP blueprints and request handling
  services/         Validation, queries, storage, and business operations
  templates/        Jinja pages and error states
  static/           Offline CSS and vanilla JavaScript
tests/               Behavioral and regression tests
config.py            Local configuration defaults
run.py               Development entry point
PROJECT_SPECIFICATION.md
requirements.txt
```

## Current limitations

- Single-user and local-computer use only; there is no authentication or cloud synchronization.
- No backup, restore, export, LAN, PWA, or notification-delivery workflow is included.
- Reminder dates use the computer's local wall-clock time.
- SQLite and filesystem changes cannot be perfectly atomic across a sudden process or power failure.
- `init-db` initializes an empty installation but does not migrate an existing database schema.

See `PROJECT_SPECIFICATION.md` for the detailed behavior and completed development stages.
