# Changelog

Record notable project changes here. Keep pending changes under Unreleased;
move them into a dated version section when a release is made.

## Unreleased

### Fixed

- Ignore normal Codex userMessage lifecycle events in the doctor assistant
  instead of rejecting them as tool execution and aborting every reply.

- Keep verified doctors present with a dedicated visibility-independent heartbeat
  and a 90-second online window; doctor request GETs no longer write presence/expiry.
- Prevent completed stale intakes from overwriting a newer patient-profile edit;
  reject an in-flight old-password login if credentials changed before session issuance.
- Preserve linked seed doctors' edited profile fields during startup seeding.

- Allow configured providers to retry stored triage fallbacks and upgrade them after valid output; preserve fallback on failure and never overwrite a stored LLM result, including concurrent retries.

### Added

- Independent Persian doctor-Codex assistant tab with streamed answers, Stop/New
  Chat and page-memory-only history; no automatic patient or development context.
- Verified-doctor assistant SSE endpoint with strict transcript bounds, dedicated
  operator login, ephemeral isolated Codex processes, cancellation/cleanup and
  per-process concurrency limits. Existing triage and schema v8 stay unchanged.
- Mocked protocol/API checks for assistant access, isolation, privacy, failures
  and streaming lifecycle; dedicated runtime setup in the README.

- Slice 7b: editable patient health and doctor profiles, own-profile endpoints,
  Persian profile/password forms and admin resubmission markers.
- Additive schema-v8 profile table/backfill and doctor resubmission timestamp,
  with migration, validation, ownership, status, race and cascade checks.
- Password change with current-password verification, separate throttling and
  atomic revocation of other sessions while retaining the current cookie.

- Slice 7a: read-only owned conversation list/detail endpoints, stored intake
  transcripts and triage, latest visit projections and lifecycle timestamps.
- Explicit no-cache shared CSS/JS asset routes and packaged dashboard assets.
- Shared Persian RTL sidebar with hash navigation, desktop preference, accessible
  mobile drawer and role-specific navigation for patient, doctor and admin.

- Document local admin credentials in the ignored .env and an optional uv
  --env-file launch command using the existing virtual environment.

- Slice 6: configured admin login and Persian doctor-review panel with pending,
  approved, rejected and suspended lists, paging and review audit.
- Atomic schema-v7 users rebuild and doctor review/license columns; preserve
  account/session/visit references and restore foreign-key enforcement on failure.
- Admin-only review transitions and audit endpoints; suspension ends the doctor's
  open accepted visits while preserving readable patient history.

- Slice 5: authenticated patient/accepting-doctor text chat, cursor pagination,
  a 500-message ceiling and idempotent doctor-controlled visit ending.
- Persian inline visit-chat panels on both pages, three-second visible-panel
  polling, read-error backoff, multiline composition and readable ended history.
- Atomic schema-v6 migration for visit end timestamps and cascading indexed
  visit messages, with migration, authorization, race and privacy checks.

- Persian height/weight dropdown choices in intake and final-review corrections, retaining custom decimal entry.

- Optional multiline context for the accepting doctor, persisted through schema v5 and excluded from all current/prior provider inputs through an explicit allowlist.
- Persian RTL inline final-review card with grouped answers, expandable long text, per-field corrections/cancellation, pending/error states and a compact confirmed summary before triage.

- Persian intake questions for height (cm), weight (kg), main complaint, disease history, past medication use and food allergies, with separate drug/other allergy wording and positive decimal measurement validation.
- Atomic SQLite v3-to-v4 migration preserving existing records, expanded history/provider/accepting-doctor data and migration rollback/legacy-profile checks.

- Slice 4: demo-grade patient/doctor self-registration, scrypt passwords, hashed cookie sessions, login throttle, role/verification/ownership dependencies and no-store API responses.
- Database-backed seeded/self-registered doctors, polling presence, public specialties, Persian login and doctor dashboard.
- Broadcast visit requests with expiry/cancellation, a partial active-request index, atomic first acceptance and accepted-doctor-only intake/history/AI projections.
- Secure-delete/version-gated SQLite initialization, auth/request settings and temporary-database security/authorization/concurrency checks.


- Slice 3: optional OpenAI-compatible specialty triage, bounded structured context, validated provider JSON, persistent fallback and idempotent results.
- Synthetic doctor directory with startup validation, specialty filtering, online/score ordering, and Persian demo cards with loading and retry.
- LLM environment settings with secret-safe repr and outcome-only logging; network-free config/client/context/triage checks.


- Slice 2b: SQLite patients, sessions, redacted message logs, stored vocabulary codes, UTC timestamps, schema initialization, indexes, and cascade deletion.
- Returning-patient profile confirmation, public patient ids, stored-code visit history, and forget-me endpoints.
- Guarded demo patient-id storage, Persian welcome-back, collapsible history, and forget-me behavior.
- APP_DB_PATH, ignored SQLite artifacts, temporary-database tests, rollback/concurrency checks, and explicit synthetic-only privacy prerequisites.

- JSON-backed default medicine choices and an editable multi-medicine list with custom names, removal, duplicate prevention, exclusive none, and message-length validation.

- Connected the symptom dropdown to the JSON-backed dictionary endpoint, showing the starter symptom names while preserving custom entry.

- Slice 2a: validated starter JSON symptom/medicine dictionaries, cached startup loading, shared normalization, whole-phrase matching, and a read-only search endpoint.
- Response-time matched vocabulary in chat responses and Persian plain-text chips in the demo.
- Dictionary validation, matching, cache, query/limit, and intake regression tests; approved data/ folder and packaged JSON files.

- Persian dropdown answers for age, duration, severity, medications, allergies, and confirmation, with custom text still available.

- Slice 1a scripted synthetic intake, immutable state machine, fixed red-flag stop, and bounded sessions.
- Versioned chat endpoints and a responsive single-file /demo page with live collected fields.
- Intake/API unittest checks for privacy, validation, terminal behavior, isolation, and eviction.
- Approved agent/ and static/ folders with packaged static HTML.

- Repository-wide `AGENTS.md` rules for reading docs before edits, scoped Conventional Commits, implementation boundaries, and virtual-environment verification.

- Approved `app`, `api`, and `schemas` packages, environment settings, response models, and generic error handlers.
- Standard-library unittest checks and optional `httpx` dev dependency.

- Separate `src/`, `tests/`, and `docs/` folders.
- Minimal FastAPI application with a `GET /health` endpoint.
- Project dependencies, setup instructions, Git ignore rules, and configuration placeholder file.
- Implementation specification and feature template in `docs/plan.md`.
- This changelog in `docs/changelog.md`.

### Breaking

- Doctor self-registration now requires a unique synthetic license_number
  (4–20 ASCII letters/digits/hyphens). It is not real credential verification.

- Chat and patient history/deletion now require patient cookie authentication; removed the patient_id creation body/ChatResponse field and old /v1/patients/{patient_id}/... routes.
- Patient history/deletion moved to /v1/me/history and DELETE /v1/me; the demo no longer uses a localStorage patient handle.
- Doctors now come from schema-v3 SQLite rows; doctors.json is seed data without online fields, online presence is computed and scores may be null. Reset the old disposable synthetic database once.

### Changed

- Refine the Persian Triage login and role dashboards with one forest design
  system, responsive layouts, consistent controls, keyboard skip links and
  clearer busy/empty/error states. Remove duplicated global page styles and
  define previously missing spacing tokens.
- Replace current demo/test-version branding with product copy while retaining
  fictional-data notices and unchanged legacy routes/configuration/seed IDs.
  Recognize both welcome prefixes so existing returning sessions stay intact.
- Refresh public setup/limitations documentation and ignore local authentication
  caches, logs and alternate SQLite filenames; no readiness or compliance claims.

- New intakes prefill from saved complete profiles; profile edits preserve past
  sessions/history/provider contexts. Doctor identity edits follow explicit
  re-review/active-visit rules; suspended profiles stay locked.
- Doctor identity polling is 15 seconds; request reads remain visible-only every
  10 seconds, while heartbeat POSTs run every 20 seconds regardless of visibility.
- Patient account deletion moves into the profile danger section. Admin and
  seeded-doctor passwords remain managed by server configuration.

- Patient loads resume the latest conversation; intake/review, triage, visit
  status and doctor messages now share one thread and bottom composer.
- Doctor acceptance opens a patient thread; accepted visits are listed in the
  sidebar, active first. Admin status/audit tabs move into the same shell.
- Shared direct-chat client retains cursor polling, draft preservation and ended
  history while stopping polling when navigating away from a conversation.

- Label the doctor registration identifier «شماره نظام پزشکی» consistently in
  signup/admin UI, keeping synthetic-only notices and the license_number contract.

- Doctor accounts expose review status/note; pending, rejected and suspended
  dashboards hide patient UI and poll for review changes. Admins are denied all
  patient/doctor data routes, and login/page redirects now handle three roles.
- Preserve seed-doctor review decisions on restart; document auto-verification
  as a local-demo shortcut bypassing admin review.

- Patient request polling now projects expired status without writing rows;
  direct-message reads also leave database rows and doctor presence unchanged.
- Patient/doctor visit items now expose ended while preserving accepted status.
- Concurrent database bootstrap and earlier migration steps cannot lower the
  schema version after another connection has upgraded it.

- Allow validated corrections through optional edit_field on the existing message route during final review only; preserve other answers and refresh matches atomically. Completed sessions remain immutable.

- Symptoms now reuse the medicine multi-item editor: default choices, custom entries, removal, deduplication, exclusive none and a shared total length limit.
- Label current medicines «داروهایی که مصرف می‌کنید»; include new demographic/history fields in returning-profile confirmation and re-collect profiles missing them. Check chief complaints with the existing red-flag list before storing them.

- Gate schema initialization below version 3 and enable secure_delete on every connection.
- Retain existing intake/triage behavior while applying account ownership; doctor-only AI fields are now visible only through an accepted request.


- Promoted existing httpx to a runtime dependency, removed the dev extra, and updated installation commands.
- Bumped SQLite schema version to 2 with cascading triage_results; patient deletion also removes triage data.


- Moved settings, SQLite infrastructure, exception handlers, and logging setup into the approved core package; updated imports without changing runtime contracts.

- Replaced the capped in-memory session store with per-request closed SQLite connections and atomic message transactions.
- Moved chat endpoints into FastAPI's threadpool and disabled access logging of patient-id URLs.

- Localized the demo and scripted intake replies into Persian with RTL layout, Persian number display, Persian/Arabic-Indic input digits, Persian confirmation answers, and translated red-flag phrases.

- Moved the application from `src/main.py` to `src/app/main.py` and switched to package discovery.
- Updated configuration examples, run/test instructions, and the implementation plan.

- Raised the minimum Python version from 3.11 to 3.14.
- Updated the README and implementation plan to match the Python requirement.
