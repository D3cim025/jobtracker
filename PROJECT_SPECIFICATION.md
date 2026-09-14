# JobTracker Project Specification

## 1. Purpose and target user

JobTracker is a private, local-first job-search workspace for one user. It records applications, the exact resume and supporting files sent, status history, interviews, assessments, follow-ups, reminders, and useful job-search statistics. The Windows computer running JobTracker is the source of truth. Core behavior must remain available without internet access.

The initial implementation uses Python 3.12+, Flask, SQLAlchemy, SQLite, Jinja templates, local HTML/CSS/JavaScript, and pytest. Authentication and cloud synchronization are outside the first version.

## 2. Current implementation status

Stages 1 through 11 provide the Flask foundation, application records, resumes, documents, exact-version tracking, timelines, reminders, Apply Again, the dashboard, and read-only offline analytics. Analytics uses applied-date trends, clearly defined current-status rates, and database-backed breakdowns with accessible local charts.

## 3. Functional requirements

### Applications

An application records company, position, job type, location, work setup, salary range and currency, job URL, source, found/applied dates, status, priority, contacts, notes, timestamps, and the exact resume used. Supported initial statuses are Saved, Applied, Assessment, Interview, Offer, Rejected, and Withdrawn. Priorities are Low, Medium, and High.

Users can create, inspect, update, explicitly confirm deletion, search, filter, and sort applications. Search covers company, position, location, contact name, and notes. Filters cover status, priority, job type, work setup, source, and applied date. Application detail pages show all metadata, resume, documents, timeline, and reminders.

### Resume library and document management

Each resume version is an independent immutable file record with display name, original file name, version, description, target role, timestamps, storage path, and file hash where practical. Uploading a new version never replaces an older one or changes existing application relationships. Resume detail shows every application that used that version.

Applications can own documents categorized as Resume, Cover Letter, Portfolio, Certificate, Job Description, Assessment, or Other. Files remain local. Storage uses generated names while retaining original display names. File routes must enforce database-backed authorization, path containment, allowlisted types, and safe response headers. Referenced resumes cannot be silently deleted.

### Timeline and reminders

Timeline events belong to exactly one application and contain type, event date, notes, and creation time. Initial types include submission, assessment received/completed, interview scheduled/completed, follow-up, offer, rejection, status change, and custom. They display chronologically.

Reminders belong to an application and contain date/time, type, notes, completion state, and creation time. Types include follow-up, interview, assessment deadline, application deadline, and custom. Views distinguish upcoming, overdue, and completed reminders. No remote notification service is required.

### Duplicate Application / Apply Again

Duplication first presents an editable review form. It may prefill position, job type, work setup, location, currency, priority, source, selected resume, and explicitly chosen reusable notes. It does not copy company, URL, applied date, contacts, timeline events, reminders, interview dates, or assessment deadlines. Date found defaults to today and status resets to Saved. The new record has its own ID and changes never affect the source. Cover-letter reuse requires an explicit user choice.

### Dashboard and analytics

The dashboard shows counts by status, applications this week/month, upcoming interview/assessment/follow-up reminders, overdue reminders, recent activity, and quick actions. Analytics includes weekly/monthly volume; interview, assessment, offer, rejection, and withdrawal rates; and breakdowns by status, job type, work setup, and source. Any charts use local assets and accessible text alternatives.

### Backup, restore, export, and settings

A backup archive includes a consistent SQLite snapshot plus all referenced resume and application files while preserving relative relationships. Restore is an explicit, warned workflow and never silently overwrites current data. CSV export is required; JSON export is planned. Settings remain local and cover theme, default currency/job type/work setup, backup/export access, and application version.

## 4. Planned data entities

- `Application`: job metadata, state, contacts, notes, timestamps, and nullable resume-version relationship.
- `Resume`: one row and stored file per version, metadata, hash, and timestamps.
- `Document`: application relationship, category, generated storage path, original name, notes, and upload time.
- `TimelineEvent`: application relationship, event type/date, notes, and creation time.
- `Reminder`: application relationship, reminder date/type, notes, completion flag, and creation time.
- `Setting`: local key/value preferences where server-side persistence is appropriate.

Foreign keys and transactions preserve relationships. Destructive behavior must be explicit and must not erase history through unintended cascades.

## 5. Offline behavior and LAN access

All required templates, styles, scripts, icons, database operations, files, search, analytics, backup, export, and theme behavior work locally with no CDN or API dependency. Stored external job URLs remain visible offline, though opening them needs internet.

The development server may bind to `0.0.0.0` for access from an iPhone on the same trusted Wi-Fi network. The user opens `http://<windows-ipv4>:5000` and may need to permit Python on private networks in Windows Firewall. JobTracker must not be port-forwarded or exposed to the public internet. Future PWA support may add a manifest/service worker, but it is not part of the current stage.

## 6. Security, privacy, and accessibility

- Use CSRF protection on state-changing forms and validate all input server-side.
- Use SQLAlchemy rather than interpolated SQL and handle transaction failures visibly.
- Keep secret keys configurable, disable debug in normal use, and show friendly 404/500 pages.
- Do not serve the database or upload tree as public static content or log document contents.
- Validate URLs reasonably and file names/types/sizes strictly; prevent traversal with resolved-path containment.
- Use semantic HTML, associated labels, visible keyboard focus, sufficient contrast, readable status text, responsive layouts, and touch-friendly controls.
- Persist light/dark preference locally and apply it in the document head to avoid theme flash.

## 7. Testing and acceptance

pytest tests run against isolated configuration and temporary paths. Tests must assert behavior, relationships, validation, file safety, duplication invariants, backup contents, export contents, error handling, and chronological classifications—not only successful status codes. The complete suite runs after every major stage and must pass before proceeding.

Stage 2 acceptance: the app factory retains all Stage 1 behavior; the six specified entities initialize in SQLite; enums and database constraints protect valid values and salary ranges; foreign keys are enforced; owned child records cascade only when an application is explicitly deleted; referenced resumes are protected; resume versions coexist; relationships are bidirectional and timeline/reminder collections are chronological; and initialization is repeatable without replacing data.

Stage 3 acceptance: application management provides server-validated create, detail, edit, explicit POST-only delete, status, and priority operations. List queries search company, position, location, contact, and notes; filter status, priority, job type, work setup, source, and applied-date range; and sort only by allowlisted columns. Invalid input preserves the submitted form without changing stored data, missing records return a friendly 404, and user content is escaped in HTML.

Stage 4 acceptance: each upload creates a new resume row and generated local filename, preserves its original display filename, and records a SHA-256 fingerprint. PDF, DOC, DOCX, ODT, and TXT uploads are checked by extension, media type, and basic file signature; unsafe names and path traversal are rejected. File access is database-backed and contained within the configured resume root. Metadata edits never replace file identity. Application-to-resume selection and usage history are bidirectional, and referenced versions cannot be deleted.

Stage 5 acceptance: application documents support Resume, Cover Letter, Portfolio, Certificate, Job Description, Assessment, and Other categories while remaining distinct from Resume Library versions. Files use generated names beneath an application-specific directory, preserve original names in the database, and are checked by extension, media type, signature, and resolved-path containment. Access and POST-only deletion are database-backed. Deleting a document or its owning application removes its local file transactionally; unrelated applications, documents, and resume relationships remain unchanged.

Stage 6 acceptance: an application stores a nullable foreign key to one exact Resume Library version. Creation and editing allow explicit assignment, reassignment, or clearing after validating the referenced record. Uploading or editing metadata for another resume cannot alter existing application foreign keys. A persisted resume version's original filename, generated storage filename, and SHA-256 fingerprint are immutable; changing the file requires uploading a new version. Multiple applications may reference one version, its usage history links to each application, and application-specific documents never modify this relationship.

Stage 7 acceptance: every specified timeline event type can be added to one application with a required valid local date/time and optional validated notes. Events display from earliest to latest and may be edited or deleted without affecting other applications. Destructive actions are POST-only and CSRF-protected. A real status transition appends a dated Status changed event in the same transaction; unchanged or invalid status submissions do not add history. Existing resume and document relationships remain intact.

Stage 8 acceptance: every specified reminder type can be created for one application with a required valid local date/time, optional validated notes, an incomplete default, and creation timestamp. Application-scoped routes verify both parent and reminder IDs. Upcoming reminders sort earliest-first, overdue reminders sort nearest-to-now first, and completed reminders remain visible and sort latest-first. Completion and deletion are POST-only and CSRF-protected, deletion is explicitly confirmed, and reusable service queries support an optional application scope for later dashboard consumption.

Stage 9 acceptance: Apply Again starts with an editable review and creates only through POST. The new application has a new ID, Saved status, today's found date, blank applied date, company, URL, and contacts, plus empty document, timeline, and reminder collections. Reusable job details and the exact Resume Library version may be selected without copying a file; original notes require an explicit choice. Matching company and position values trigger a non-blocking confirmation warning. The source application and all of its relationships remain unchanged.

Stage 10 acceptance: the root page is a responsive dashboard with live total and per-status counts, calendar-week and calendar-month added/applied summaries, existing reminder-service classifications, upcoming interview and assessment records, recent applications and status changes, useful empty states, and links to existing workflows. Dashboard aggregation remains in a service layer, eagerly loads related applications where needed, and adds no schema or analytics implementation.

Stage 11 acceptance: the read-only Analytics page groups applications with a date applied by ISO calendar week and calendar month; missing applied dates never enter trends or rate denominators. Assessment, interview, offer, rejection, and withdrawal rates are explicitly defined as current-status shares of dated applications and show an insufficient-data state for a zero denominator. Status, job-type, work-setup, and normalized source breakdowns use database aggregation and accessible offline CSS charts without external dependencies.

For the initial empty installation, `init-db` is the schema baseline and uses SQLAlchemy metadata to create only missing tables. It is not an upgrade mechanism. Once released databases can contain user data, every schema change must ship as an explicit, sequential migration that first requires a verified backup, runs transactionally where SQLite permits, records its schema version, and is covered by upgrade tests. A future stage must introduce that first versioned migration before changing this baseline; `drop_all` or automatic destructive recreation must never be used for user data.

## 8. Delivery roadmap

1. Foundation and tests (complete).
2. SQLAlchemy entities, relationships, schema initialization, and model tests (complete).
3. Application CRUD, status/priority, search, filters, and sorting (complete).
4. Resume library and version-safe file storage (complete).
5. Application documents and secure delivery (complete).
6. Exact resume tracking verification (complete).
7. Timeline events and history (complete).
8. Reminders and date classifications (complete).
9. Duplicate/Application Again review workflow and invariants (complete).
10. Dashboard summaries and recent activity (complete).
11. Offline analytics (complete).
12. Consistent backup, warned restore, and CSV/JSON export (next stage).
13. Responsive desktop/mobile refinement.
14. Persistent theme, empty/error states, confirmations, and accessibility polish.
15. Trusted-LAN/iPhone documentation and validation.
16. Full security, privacy, quality, and offline review.
17. Portfolio documentation and UI consistency.

Future options include authentication for broader remote access, reusable application templates, PWA installation/offline caching, and opt-in synchronization. None may compromise local ownership or historical accuracy.
