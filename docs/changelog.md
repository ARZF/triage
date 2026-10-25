# Changelog

Record notable project changes here. Keep pending changes under Unreleased;
move them into a dated version section when a release is made.

## Unreleased

### Fixed

- Allow configured providers to retry stored triage fallbacks and upgrade them after valid output; preserve fallback on failure and never overwrite a stored LLM result, including concurrent retries.

### Added

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

- Chat and patient history/deletion now require patient cookie authentication; removed the patient_id creation body/ChatResponse field and old /v1/patients/{patient_id}/... routes.
- Patient history/deletion moved to /v1/me/history and DELETE /v1/me; the demo no longer uses a localStorage patient handle.
- Doctors now come from schema-v3 SQLite rows; doctors.json is seed data without online fields, online presence is computed and scores may be null. Reset the old disposable synthetic database once.

### Changed

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
