# JobTracker

JobTracker is a private, local-first job application tracker built with Flask and SQLite. The current version includes application management and a local, version-preserving Resume Library; remaining workflows will be added incrementally.

## Requirements

- Windows 10 or 11
- Python 3.12 or newer
- PowerShell

No internet connection is required to run the installed application. Internet is needed initially to download Python packages.

## Installation

From the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, you can run `.venv\Scripts\python.exe` directly instead. Do not recreate a healthy environment unnecessarily.

## Running locally

```powershell
.\.venv\Scripts\python.exe run.py
```

Open `http://127.0.0.1:5000`. Stop the server with `Ctrl+C`. The default run mode does not enable Flask debug mode.

Initialize a new local database before first use. This creates missing tables and does not replace existing records:

```powershell
.\.venv\Scripts\python.exe -m flask --app run.py init-db
```

`init-db` initializes a fresh database; it is deliberately not an upgrade command. Future schema changes will use committed, sequential migrations with a backup-first policy. Never delete or recreate `instance/jobtracker.db` to apply an upgrade.

## Offline usage

JobTracker uses local templates, CSS, JavaScript, SQLite data, and files—no required CDN, cloud service, or external API. Once dependencies are installed, core features are designed to work offline. External job-posting links still require internet when opened.

## iPhone access on trusted Wi-Fi

1. Connect the Windows computer and iPhone to the same trusted Wi-Fi network.
2. In PowerShell, run `ipconfig` and find the active adapter's IPv4 address (often `192.168.x.x`).
3. Start JobTracker for LAN access:

   ```powershell
   $env:JOBTRACKER_HOST = "0.0.0.0"
   .\.venv\Scripts\python.exe run.py
   ```

4. If Windows Firewall asks, allow access on **Private networks only**.
5. In iPhone Safari, open `http://<computer-ipv4>:5000`.

This mode has no authentication in the initial local version. Use it only on a trusted private network. Do not configure router port forwarding or expose JobTracker to the public internet.

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Tests use isolated configuration and temporary SQLite paths.

## Data, backup, and restore

The default database will live at `instance/jobtracker.db`; future uploads will live under `uploads/`, and generated archives under `backups/`. These private runtime directories are ignored by Git.

The backup and restore workflow is planned for Stage 12. Restore will require explicit confirmation and will document whether current data is replaced or merged; never replace the database or upload folders casually.

## Configuration

- `JOBTRACKER_SECRET_KEY`: persistent private secret for form security (set before storing real data).
- `JOBTRACKER_HOST`: defaults to `127.0.0.1`; use `0.0.0.0` only for trusted-LAN access.
- `JOBTRACKER_PORT`: defaults to `5000`.
- `JOBTRACKER_DEBUG`: set to `1` only during local development; never for LAN use.

Resume files are stored with generated names under `uploads/resumes`; their original names and SHA-256 fingerprints remain in the database. Do not rename or move stored files manually. Referenced resume versions must remain available to preserve application history.

## Project structure

```text
app/
  __init__.py       Application factory and Flask extensions
  models.py         SQLAlchemy entities, constraints, and relationships
  routes/           HTTP blueprints
  services/         Reusable business logic (later stages)
  templates/        Jinja pages and friendly errors
  static/           Offline CSS and JavaScript
tests/               pytest fixtures and behavioral tests
config.py            Default local configuration
run.py               Development entry point
AGENTS.md            Rules for future coding agents
PROJECT_SPECIFICATION.md
requirements.txt
```

See `PROJECT_SPECIFICATION.md` for requirements and the staged roadmap.
