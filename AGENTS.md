# JobTracker Agent Guide

## Scope and stack

- Build a local-first, offline-first single-user job application tracker.
- Use Python 3.12+, Flask application factory, Flask-SQLAlchemy, SQLite, Jinja, local CSS/JavaScript, and pytest.
- Do not add frontend frameworks, Node.js, cloud services, remote databases, CDNs, or external APIs without prior discussion.
- Work one stage at a time. Do not implement a later stage before it is requested.

## Architecture

- Keep route handlers small and place reusable business logic in `app/services/`.
- Put blueprints in `app/routes/`, templates in `app/templates/`, and local assets in `app/static/`.
- Store runtime data in `instance/`, uploads in `uploads/`, and archives in `backups/`; do not commit private/runtime data.
- Keep the app factory configurable so tests can use isolated temporary databases and directories.

## Data and file safety

- Preserve historical records, especially the exact resume version attached to each application.
- Never overwrite an older resume version. Do not delete a referenced resume without an explicit safe policy.
- A duplicated application must receive a new ID and empty timeline/reminders; it must reset company, URL, contacts, dates, and status as specified.
- Use SQLAlchemy parameters, server-side validation, CSRF protection, generated storage names, safe filename handling, allowlisted file types, and guarded file-serving routes.
- Never expose arbitrary filesystem paths, upload directories, databases, document contents, or secrets.

## Quality workflow

- Read `PROJECT_SPECIFICATION.md` before changing behavior and keep it synchronized with the implementation.
- Add behavioral tests for every feature and regression. Never delete or weaken a test merely to pass.
- Run the full pytest suite after each major stage and report collected, passed, and failed counts.
- Preserve existing behavior and unrelated user changes. Check `git status` before commits.
- Make small logical commits only when the suite passes; do not commit private data or broken functionality.
- Keep the UI responsive, keyboard accessible, usable without color alone, and fully functional offline.

