# Healthcare Agent: Implementation Plan and Specification

Status: Slices 1a, 2a, 2b, 3, 4, 5, 6, 7a, 7b and the independent doctor–Codex assistant approved. Intake, vocabulary, memory, specialty triage, accounts, visits, direct text chat, admin doctor review, shared dashboards, editable profiles/passwords and the independent synthetic-case assistant are in scope; future workflow decisions remain proposals.

## 1. Purpose

Build a FastAPI backend for a healthcare agent. Implement one agreed workflow
at a time, with an explicit API contract and a runnable check for its behavior.

## 2. Current baseline

- Python 3.14 or later; dependencies are FastAPI, Uvicorn, and httpx.
- `src/app/main.py` creates the FastAPI application, owns its lifespan, includes routers, and calls the core logging and exception-handler registration functions.
- `GET /health` returns HTTP 200 with JSON `{"status": "ok"}`.
- The health endpoint checks application responsiveness only.
- FastAPI exposes interactive API documentation at `/docs`.
- The app implements scripted intake, JSON vocabulary, SQLite patient memory, optional AI specialty triage, demo accounts, broadcast visits and direct text chat with the accepting doctor; no patient-facing diagnosis, prescription or appointment scheduling.
- The expanded Persian intake includes height/weight, main complaint, disease/medication histories and food/drug allergies, with multi-item symptom and medicine editors. Schema v4 adds nullable columns without resetting version-3 data.
- Schema v5 adds optional doctor-only context, explicitly excluded from current/prior provider inputs. Final review is an inline Persian card with validated field-specific corrections before confirmation.
- Schema v6 adds visit end timestamps and indexed direct messages. Patient request/message polling is read-only; the doctor alone ends an accepted visit without removing its history.
- Schema v7 adds the configured admin role, synthetic license numbers, doctor review states and a review-only audit. Suspension also ends the doctor's open visits. Admins cannot access patient data.
- Slice 7a adds read-only conversation list/detail routes, shared CSS/JS dashboard assets and one continuous patient/doctor thread. Page loads resume existing conversations. Schema remains v7.
- Slice 7b adds editable profiles and password changes, a dedicated heartbeat, read-only doctor polling and schema v8. Profile edits preserve historical intakes and cannot overwrite a newer profile through stale intake completion. The online window is 90 seconds.
- The independent doctor–Codex assistant adds a verified-doctor-only ephemeral streaming chat without automatic application data or repository context. It reuses existing folders/dependencies and keeps schema v8.
- `src/app/core/config.py` defines frozen settings read from `os.environ`. `APP_LOG_LEVEL` defaults to `INFO`; INFO, WARNING, ERROR, and CRITICAL are accepted (case insensitive). Invalid values fail startup. The application does not load `.env` files.

## 3. Project boundaries

- Put application code in `src/`, runnable checks in `tests/`, and specifications
  and project documentation in `docs/`.
- Do not create additional folders without the user's permission.
- The user approved `src/app/`, `src/app/api/`, `src/app/schemas/`, `src/app/agent/`, `src/app/static/`, `src/app/data/`, `src/app/core/`, and `src/app/services/`.
- `services/` is approved for Slice 4 accounts, doctors and visits; `models/` remains proposed and requires permission.
- Reuse existing code, standard library features, and installed dependencies first.
- Add no speculative abstractions, integrations, or infrastructure.
- Keep this plan consistent with implemented behavior; label proposed behavior clearly.

- Slice 4 below supersedes earlier slice descriptions for identity, ownership, doctor storage/presence, route/response changes and schema version. Earlier entries remain a historical record. Only src/app/services/ was newly approved.
- The expanded Persian intake feature below supersedes earlier question orders, returning-profile fields, single-symptom editor behavior and schema version. No additional folders are approved or created.
- The doctor-only context/inline review feature supersedes the preceding intake's final steps and schema version: optional additional_context precedes confirm; corrections reuse the message route without another endpoint.
- Slice 5 supersedes earlier direct-chat exclusions, schema version and patient-list expiry writes. It uses only existing approved folders; no folders or dependencies are added.
- Slice 6 supersedes earlier admin exclusions, doctor registration requirements and schema version. Review audit is implemented; patient/chat audit remains excluded. It reuses existing folders and dependencies.
- Slice 7a supersedes earlier self-contained dashboard, history-aside and visit-chat-panel descriptions. Only shell.css and shell.js are new files; no folders, dependencies or schema changes. Login remains unchanged.
- Slice 7b supersedes earlier profile/password exclusions, completed-session prefill source, GET presence side effect, 45-second online window and five-second identity refresh. Existing folders/dependencies are reused.
- The independent assistant permits synthetic clinical-option discussion for physician review only in that separate chat. Existing intake/triage prompts, record-access boundaries and clinical-action exclusions remain unchanged.

## 4. Decisions for persistence and future slices

- **Slice 2b decisions:** storage = SQLite; retention = none (manual deletion only).
- **Real-data prerequisites:** authentication, encryption at rest, consent, retention rules, and audit are NOT implemented; all are required before any real patient data.

- **First workflow:** What task should the agent complete, and for whom?
- **Clinical scope:** Is the task administrative, educational, or clinical?
  What outputs and actions are allowed, and what requires human review?
- **Inputs and outputs:** What information does the caller provide, and what
  must the agent return? Supply one concrete request and expected response.
- **Model and tools:** Which provider, if any, is required? Does the workflow
  need external tools or reference material?
- **Conversation state:** Is each request independent, or must sessions persist?
- **Access and data:** Who may call the API? Will it receive identifiable health
  information? What storage, logging, and retention behavior is required?
- **Failure behavior:** What should happen when input is incomplete, a provider
  is unavailable, or the agent cannot safely complete the task?

Do not infer diagnosis, treatment advice, emergency assessment, record access,
or persistent storage from the phrase "healthcare agent" alone.

## 5. Feature specification template

Complete this section for each agreed feature before writing its code:

### Feature: [name]

- **Status:** proposed / approved / implemented.
- **User outcome:** [one concrete task and its expected result].
- **Scope:** [included behavior and explicit exclusions].
- **API contract:** [HTTP method, path, request fields, response fields, status codes].
- **Validation:** [required fields, bounds, and invalid-input behavior].
- **Agent behavior:** [instructions, permitted tools, and completion conditions].
- **Failure behavior:** [timeouts, unavailable dependencies, and user-facing errors].
- **Access and data handling:** [authorization, permitted data, storage, and logging].
- **Configuration:** [required settings and how they are supplied].
- **Acceptance examples:** [normal request, invalid request, and relevant failure case].
- **Runnable check:** [file in `tests/` and exact command to run it].


### Feature: Slice 1a — scripted patient-intake chat and demo

- **Status:** approved.
- **User outcome:** complete a scripted intake using synthetic data in a local demo.
- **Scope:** age, symptoms, duration, severity, medications, allergies, confirm, in that order. No LLM, database, authentication, identifiers, diagnosis, or treatment advice.
- **API contract:** POST /v1/chat/sessions returns 201; POST /v1/chat/sessions/{session_id}/messages accepts {"message": str} and returns 200. Both return {session_id, reply, step, done, emergency, collected}. Session IDs are uuid4 hex. Collected fields age, symptoms, duration, severity, medications, allergies start null. GET /demo serves the packaged static/index.html via FileResponse. Existing /health and /docs remain available.
- **Validation:** message length 1–2000; invalid bodies return 422 ErrorResponse. Trim answers. Age accepts decimal integers 0–120; severity 1–10; other answer fields require non-empty text (including no or none for medications/allergies). Confirmation accepts yes/no case-insensitively. Invalid answers keep state and re-ask with a short hint.
- **Agent behavior:** fixed Persian welcome, questions, hints, reset, completion, and emergency copy are defined in src/app/agent/intake.py. The page uses RTL layout. Confirmation accepts بله/خیر/نه and English yes/no; negative confirmation resets data. Completed states keep their final reply.
- **Red-flag behavior:** before storing symptoms, match the original English phrases and their Persian equivalents from the single RED_FLAGS constant in intake.py. A match stores none of the triggering answer, preserves previous fields, sets emergency=true and done=true, and returns the fixed Persian message directing the person to local emergency services. This starter substring list requires clinical review; it is not a clinical assessment.
- **Failure behavior:** unknown/evicted sessions return 404 ErrorResponse. The demo shows a visible error line on failed requests; it does not automatically retry messages with uncertain outcomes. Reset creates a new session. Input is disabled while pending and after completion.
- **Access and data handling:** unauthenticated synthetic demo only; do not request names or identifiers or log messages/collected data. A process-local dict stores at most 1000 sessions, evicting the oldest created session. State is lost on restart; database persistence belongs to the future EHR slice. Async handlers perform store operations without yielding, limiting use to one process/event loop.
- **Configuration:** no new settings or dependencies. Include static/*.html in package data.
- **Demo:** one Persian RTL self-contained HTML file, inline CSS and vanilla JS, no CDN. Bot/user bubbles, labeled input, Send and Enter submission, Reset, live collected fields, visible “Demo - synthetic data only” banner, keyboard focus indicators, responsive mobile layout. All dynamic text uses textContent; never innerHTML.
- **Acceptance examples:** 30 → mild cough → two days → 3 → none → no → yes completes with all six values; invalid age, blank text, severity, or confirmation re-asks; no at confirm clears fields; CHEST PAIN at symptoms ends immediately with symptoms still null; later messages leave final state unchanged. Unknown session is 404; empty or 2001-character messages are 422; /demo serves text/html.
- **Runnable check:** tests/test_intake.py and tests/test_chat_api.py using unittest; run .\.venv\Scripts\python.exe -m unittest discover tests. Reinstall editable dev package, run the server, and complete one synthetic intake through /demo in a browser.


### Feature: Persian localization of the Slice 1a demo

- **Status:** approved.
- **User outcome:** complete the scripted demo entirely in Persian.
- **Scope:** Persian page text, RTL layout, native system fonts, localized labels, hints, welcome, completion, reset, and emergency replies.
- **API contract:** routes, JSON keys, steps, and error codes retain their existing contracts; scripted replies are Persian. The demo displays transport errors in Persian.
- **Validation:** decimal ASCII, Persian, and Arabic-Indic digits are accepted. Confirmation accepts بله, خیر, نه, and English yes/no. Other non-empty text rules remain in effect.
- **Agent behavior:** Persian fixed copy is defined in src/app/agent/intake.py. The existing English red-flag list remains, with Persian equivalents added to the same constant. Matching normalizes Arabic ي/ك and Persian zero-width non-joiners; collected text keeps the original trimmed answer.
- **Failure behavior:** Persian inline failure messages and Persian required-input hints; Reset starts a new session.
- **Access and data handling:** same synthetic-only, process-local data rules. No new folders, dependencies, external fonts, persistence, or clinical workflow.
- **Configuration:** none.
- **Acceptance examples:** ۳۰, سرفه خفیف, دو روز, ۳, هیچ, ندارد, بله completes; خیر resets; درد قفسه سینه stops without storing symptoms. Persian/Arabic digit bounds and Arabic letter variants are covered.
- **Runnable check:** .\.venv\Scripts\python.exe -m unittest discover tests, including Persian state-machine and API flows.


### Feature: Dropdown answers alongside the Persian chat

- **Status:** approved.
- **User outcome:** select common answers instead of typing every reply.
- **Scope:** native labeled select above the existing reply box, with Persian choices and RTL layout. Ages 0-120, severity 1-10, common duration choices, no-medication/no-allergy responses, and yes/no confirmation. Symptoms come from the JSON dictionary; every step permits custom text.
- **API contract:** submit the selected value through the existing message endpoint; no API or state-machine changes.
- **Validation:** retain server validation. No selection is prefilled or automatically submitted; choose, review, then Send. Numeric option labels and values use Persian digits.
- **Agent behavior:** keep the same step order, red-flag stop, reset, and terminal behavior.
- **Failure behavior:** disable dropdown and input together while pending, failed, or complete. Load the symptom choices from the dictionary endpoint before creating a new session.
- **Access and data handling:** same synthetic-only session behavior; no new collection fields.
- **Configuration:** no new folders or dependencies.
- **Acceptance examples:** select age 30, type synthetic symptoms, select a duration, severity 3, no medications, no allergies, and yes to complete; a custom choice clears the input for typing; no at confirm restarts at age.
- **Runnable check:** existing unittest suite, including a full API intake using the exact dropdown answer values.


### Feature: Slice 2a - JSON symptom and medicine vocabulary

- **Status:** approved.
- **User outcome:** see vocabulary matches for synthetic symptoms and medications in chat responses and Persian demo chips.
- **Scope:** two JSON dictionaries in the approved src/app/data/ folder, each containing 12 starter vocabulary entries. No database, LLM, brands, doses, indications, side effects, interactions, external codes, diagnosis, or treatment advice.
- **API contract:** GET /v1/dictionaries/{kind}?q=&limit= accepts symptoms or medicines, optional q of at most 100 characters, and limit 1-100 (default 50). It returns {kind, entries: [{code, name_fa, name_en, aliases}]}; invalid kind/query/limit returns 422 ErrorResponse. ChatResponse adds matched: {symptoms: [{code, name_fa}], medicines: [{code, name_fa}]}, computed from collected.symptoms and collected.medications on each response. Existing fields and routes keep their contracts.
- **Validation:** JSON document status is 'starter list, not clinically reviewed'. Require unique lowercase slug codes matching ^[a-z0-9_]+$, non-empty Persian and English names, and a list of non-empty alias strings. Bad JSON, unreadable files, malformed documents, and invalid entries raise ValueError naming only the file, code when available, and a safe reason; never dump contents.
- **Agent behavior:** intake.py remains pure and unchanged. Both dictionaries load once during startup, using a standard-library cache. Normalize text and aliases with casefold, the existing TEXT_NORMALIZATION, Persian/Arabic-Indic digits to ASCII, Unicode punctuation to spaces, and collapsed whitespace. name_fa is always an implicit alias; English names are searchable as well. Matching searches padded whole words/phrases, returns each code once, and orders matches by first text position. Dictionary q search uses normalized substrings across names and aliases, retaining file order.
- **Failure behavior:** invalid files stop startup with sanitized ValueError; no partial dictionary load is used. No write endpoint. A non-empty unmatched answer produces no extra chips or 'not found' message.
- **Access and data handling:** synthetic-only session rules continue. Vocabulary recognition is not clinical interpretation. Do not log answers or collected data.
- **Configuration:** JSON files are the source of truth. Edit them locally and restart the server to reload. Include data/*.json as package data; add no dependencies.
- **Acceptance examples:** symptoms 'سرفه و تب خفیف' matches cough then fever; 'تبریز' does not match fever; Arabic letter variants, half-spaces, punctuation, digits, English aliases, and repeated mentions behave consistently. A full intake with matching symptoms and 'هیچ' medications produces symptom chips and no medicine chips.
- **Runnable check:** tests/test_dictionaries.py covers file validation, normalization, matching, API search/bounds, and a full matched intake; all existing 23 tests must still pass. Reinstall the editable dev package, run unittest discovery, start Uvicorn, and complete an intake in /demo to check chips.


### Feature: Dictionary-backed default symptom choices

- **Status:** approved.
- **User outcome:** choose a starter symptom from the dropdown instead of having to type it.
- **Scope:** populate symptoms from the existing JSON-backed endpoint; keep the custom answer option and editable reply box. Add no vocabulary, folders, or dependencies.
- **API contract:** reuse GET /v1/dictionaries/symptoms?limit=100 and the existing message POST; no backend contracts change.
- **Validation:** preserve message validation and symptom matching. Selecting an option fills the input without auto-submitting.
- **Agent behavior:** intake steps and red-flag handling remain unchanged.
- **Failure behavior:** reload symptom choices before creating each new session; dictionary failures use the existing visible error and Reset recovery. Controls remain disabled during loading.
- **Access and data handling:** synthetic-only demo rules continue; dictionary labels use textContent.
- **Configuration:** JSON remains the source of truth. At most 100 choices are loaded; a larger vocabulary will need searchable choices.
- **Acceptance examples:** on the symptom step, the dropdown contains all 12 Persian names plus placeholder/custom entry; choosing cough fills the reply and produces its chip after Send. Reset reloads the options.
- **Runnable check:** unittest discovery includes every default symptom name as a valid matching answer; automated browser verification checks actual options, selection, custom entry, and loading failure.


### Feature: Default medicine choices and editable multi-medicine answer

- **Status:** approved.
- **User outcome:** choose several existing medicines or add custom names before submitting the intake answer.
- **Scope:** load the 12 starter generic names from the existing medicine dictionary. At the medication step, selecting a name appends it to an editable list. Provide Add for custom text, remove controls, none, and Submit list. No brands, doses, clinical advice, folders, or dependencies are added.
- **API contract:** reuse dictionary GET and chat message POST. Submit the completed list as Persian-comma-separated text in the existing message field; collected.medications remains a string and matched.medicines remains the recognized vocabulary list.
- **Validation:** deduplicate identical names case-insensitively; none clears all medicine entries and adding a medicine removes none. Enforce the existing 2000-character message ceiling before changing the list or sending. Preserve a pending typed name on final submit.
- **Agent behavior:** all intake steps, matching, final-state behavior, and red-flag handling remain unchanged.
- **Failure behavior:** use existing request error and Reset recovery. Disable editor controls while pending, failed, or complete. Reset and successful step advancement clear the local draft list.
- **Access and data handling:** draft names exist only in page memory until submitted; same synthetic-only rules and textContent rendering apply.
- **Configuration:** load symptoms and medicines before session creation, at most 100 entries per dictionary. JSON remains the source of truth.
- **Acceptance examples:** select two names and add a custom name, remove one, then submit the remaining names together; repeated selection adds no duplicate; none is exclusive; Reset clears drafts; valid known names produce separate matched chips.
- **Runnable check:** unittest discovery covers all generic default medicine names and a multi-name intake; automated browser checks verify adding, removing, duplicates, none, length validation, keyboard entry, pending input, and mobile layout.


### Feature: Slice 2b - SQLite patient memory, profiles, history, and deletion

- **Status:** approved.
- **User outcome:** a returning synthetic patient can confirm their previous age, medications, and allergies, review prior visits, and delete all stored data.
- **Scope:** stdlib sqlite3 persistence in flat existing folders only; no new dependencies, authentication, LLM, or clinical logic.
- **API contract:** POST /v1/chat/sessions accepts an optional body {patient_id: str|null, max_length: 64}; no body creates a new patient, unknown id returns 404. Chat responses add patient_id and returning. GET /v1/patients/{patient_id}/history?limit= returns a newest-first list of visits, with limit 1-50/default 10. DELETE /v1/patients/{patient_id} returns 204 and cascades through sessions/messages; unknown patients return 404. Shared ErrorResponse applies to HTTP, validation, and storage failures.
- **Validation:** APP_DB_PATH defaults to healthcare_agent.db and must be non-empty; read Settings() at every connection. Existing message, dictionary, and intake validation continues. Tests always override the database path to a temporary file.
- **Agent behavior:** new patients start the existing full intake. A prior completed, non-emergency visit qualifies a returning patient: prefill age/medications/allergies from the most recently completed qualifying visit and start at profile with a fixed Persian welcome-back and age in Persian digits. Yes confirms the profile, sets internal returning_profile=true, and asks symptoms/duration/severity/confirm only. No discards the prefill and starts the full intake at age. Handle profile explicitly outside sequential STEPS; build responses from named public fields.
- **Persistence:** patients, sessions, messages, UTC ISO-8601 timestamps, foreign-key cascades, requested indexes, and user_version=1. Initialize tables idempotently on connection and in lifespan. Use one explicitly closed connection per request and BEGIN IMMEDIATE for each message read/advance/write/log transaction. Completed sessions never update or append messages.
- **Stored vocabulary and logs:** persist symptom/medicine code arrays when the corresponding collected answer changes; history resolves stored codes using current names, falling back to the code if removed. Live chat matches still use current answer matching. Store initial bot reply and each user/bot pair; replace an emergency-triggering user message with a fixed Persian placeholder, never its text.
- **Failure behavior:** rollback failed transactions and explicitly close every connection, including initialization failures. History/deletion reject unknown patients. Stale demo patient ids receive 404, are cleared locally, and retry as a new patient. localStorage access is guarded and the demo works without it.
- **Access and data handling:** synthetic data only. Storage = SQLite; retention = none (manual deletion only). Authentication, encryption at rest, consent, retention rules, and audit are NOT implemented and are required before real patient data. Do not log messages, collected data, or patient ids; disable Uvicorn access logging.
- **Configuration:** APP_DB_PATH controls the local file; ignore *.db and its journal/WAL/shared-memory companions. No new folders. Stdlib single-file SQLite has no migration framework; upgrade to Postgres/SQLAlchemy/Alembic when needed, and code JSON arrays become join tables when code querying is needed.
- **Demo:** persist only patient_id in guarded localStorage; Reset starts another session for the same patient. Show returning note, profile yes/no choices, collapsible visit history with dates/symptoms/matched chips, and a Persian forget-me button that deletes patient data and starts fresh. Use textContent throughout.
- **Acceptance examples:** a completed intake survives fresh connections; reload shows profile and previous values; yes skips medication/allergy questions, no restarts age. Emergency/unfinished visits do not qualify. Red-flag text appears in no table. History retains missing dictionary codes. Forget-me cascades and stale local ids recover.
- **Runnable check:** unittest discovery uses temporary SQLite files for all database-capable tests; cover persistence, profile paths, history/order/bounds, redaction, atomicity, deletion, settings overrides, and no-body compatibility. Reinstall, run Uvicorn, and exercise complete/reload/profile/history/forget-me in the demo.


### Feature: Slice 3 - AI specialty triage and synthetic doctor suggestions

- **Status:** approved.
- **User outcome:** after a completed non-emergency synthetic intake, see a suggested specialty, urgency, notice, and matching fictional doctors; no booking or doctor accounts.
- **Scope:** optional synchronous OpenAI-compatible chat-completions call, structured context, validated JSON, persistent results with retryable fallbacks, and Persian demo cards. No authentication, diagnosis shown to patients, treatment, dosing, or new folders.
- **API contract:** POST /v1/chat/sessions/{session_id}/triage returns 200 with {session_id, source: llm|fallback, specialty: {code, name_fa}, urgency: routine|soon|urgent|emergency|unknown, emergency, reason: str|null, notice, doctors: [{id, name_fa, expertise, score, online}]}. Unknown session returns 404; incomplete or emergency intake returns 409, both using ErrorResponse. Doctor-only fields are never exposed.
- **Validation:** validate provider JSON with Pydantic: one of the nine available specialty codes; urgency routine|soon|urgent|emergency; reason_fa <=300, doctor_summary_fa <=1200, at most five considerations_fa strings of <=200 characters. Ignore unknown fields. Validate doctors.json at startup, including unique slug ids/codes, known specialties, score 0-5, and at least one general-practice doctor.
- **Agent behavior:** fixed system prompt lists allowed specialties with Persian names, treats patient text as untrusted data, defines the JSON contract, and forbids diagnosis claims, treatment and dosing. Context contains current intake and matched names, plus up to three most recent previous completed non-emergency visits with date and triage specialty; no identifiers or transcripts. Each free-text value is capped at 500 characters. Doctors sort online first, score descending, maximum ten.
- **Failure behavior:** unconfigured provider, invalid output, HTTP/transport failure or timeout stores general_practice, urgency unknown, source fallback, null reason and empty doctor-only fields. No network call when unconfigured. Read and close context connection before provider I/O; then INSERT OR IGNORE in a new transaction and return the stored row. A stored LLM row is returned without provider I/O. A stored fallback is returned without provider I/O when unconfigured; when configured, a later request calls the provider once. Valid output updates only WHERE session_id matches AND source='fallback', never an LLM row. Failed retries return the stored result with HTTP 200 without changing it. Every provider call occurs after closing the context connection, outside any SQLite transaction. When no row is stored, retain INSERT OR IGNORE behavior, including storing fallback. Each user retry costs one provider call; no cooldown or rate limit is implemented, and per-session cooldown/rate limiting with authentication is the upgrade path. Emergency provider urgency hides doctors and uses the fixed emergency notice.
- **Access and data handling:** synthetic data only. The provider receives structured health data. Before real data, require a data-processing agreement, a lawful basis, and a data-location decision, plus the existing privacy prerequisites. AI considerations are unverified and doctor-only. Never log prompts, responses, headers, identifiers, credential-bearing URLs or keys; log only outcome categories.
- **Configuration:** optional APP_LLM_BASE_URL (HTTP/HTTPS including any /v1 prefix), APP_LLM_API_KEY (excluded from repr), APP_LLM_MODEL, APP_LLM_TIMEOUT_SECONDS (finite float 1-120, default 30). Configured means URL and model are both set; no .env loading. Move existing httpx to runtime and remove dev extra. SQLite schema version 2 adds triage_results with cascading session foreign key. No new dependencies or folders.
- **Demo:** automatically request triage after non-emergency completion; show loading, Persian specialty/urgency/reason/notice and fictional doctor cards with expertise, online state and Persian scores. Show retry after request failure; render using textContent.
- **Acceptance examples:** no provider produces stored general-practice fallback and doctors; valid mocked output persists and selects sorted doctors; invalid specialty/JSON/timeout falls back; emergency urgency has no doctors; repeated calls after an LLM result avoid provider I/O; fallback then success upgrades the row, failed retries preserve it, unconfigured fallback makes no call, and concurrent first calls keep one row; patient deletion cascades; another connection can BEGIN IMMEDIATE during the provider call.
- **Runnable check:** unittest discovery with temporary databases and httpx.MockTransport, plus a completed synthetic /demo intake without a provider. Attempt real-provider verification only when configured; otherwise explicitly report it unverified.


### Feature: Slice 4 - demo accounts, doctor dashboard and broadcast visit requests

- **Status:** approved.
- **User outcome:** synthetic patients and doctors self-register with username/password; patients request a visit after triage and the first available verified doctor of that specialty accepts it.
- **Scope:** one new approved folder src/app/services/ containing accounts.py, doctors.py and visits.py. Keep existing modules in place. Standard-library scrypt and opaque cookie sessions; no new dependencies, chat, prescriptions or admin role.
- **API contract:** public /health, /docs, dictionaries, GET /v1/specialties and /login, /demo, /doctor pages. POST /v1/auth/register (201), POST /v1/auth/login (200), POST /v1/auth/logout (204) and GET /v1/auth/me require a valid cookie; register/login/me return the named user projection. Patient-role chat endpoints use cookie ownership with no session-creation body or patient_id response field; replace old patient-id routes with GET /v1/me/history and DELETE /v1/me. Patient visit requests: POST/GET /v1/visit-requests, POST /v1/visit-requests/{id}/cancel. Verified doctor endpoints: PUT /v1/doctor/availability, GET /v1/doctor/requests?status=pending|accepted (omission returns both), POST /v1/doctor/requests/{id}/accept. Shared ErrorResponse for 401/403/404/409/422/429.
- **Validation:** role-discriminated registration forbids extra fields. Lowercase username matches ^[a-z0-9_.-]{3,32}$; password 8-128, name_fa 2-60, specialty in SpecialtyCode, expertise 2-3 strings of 2-40 chars. Seed ids reserved, duplicates 409. Client-supplied verified/score/available rejected. Unverified doctors can log in but receive 403 on every doctor data endpoint.
- **Agent behavior:** preserve intake and retryable triage. Doctor lists read verified database rows, computed online state, online-first/score-descending/NULL-last/name ordering, maximum ten. A visit request requires owned non-emergency completed intake, non-emergency stored triage, an online doctor of that specialty and no pending/accepted request for the session. Pending requests broadcast to available verified doctors of the specialty; acceptance is one guarded atomic UPDATE so exactly one doctor wins.
- **Failure behavior:** unknown/not-owned resources 404; unmet visit rules, unavailable doctor, expired/already-claimed/cancelled requests 409. Distinguish creation-rule conflicts using safe error codes. Expire pending requests older than APP_REQUEST_TTL_MINUTES at the start of each visit-request operation. Statuses: pending, accepted, cancelled, expired; cancel pending only. Partial unique index enforces one active request per session. Throttle five failed logins per lowercased username in fifteen minutes, 429 with Retry-After; success clears failures. Bounded per-process memory (10000 keys).
- **Access and data handling:** synthetic data only and demo-grade authentication. Scrypt n=2**14/r=8/p=1 with sixteen-byte random salt and constant-time digest comparison; dummy hash for unknown users. Random token_urlsafe(32) cookies, SHA-256 hashes only in SQLite. HttpOnly/SameSite=Lax/Path=/ and TTL Max-Age, optional Secure. SameSite=Lax supplies the requested demo CSRF defense; no cross-origin access is enabled. GET doctor requests explicitly updates presence and visit-request GET lists persist derived expiry as the requested GET side effects; no GET changes availability, request acceptance or account state. All /v1 responses carry Cache-Control: no-store. No password/token/cookie/username logging.
- **Visibility:** pending doctor items expose only request id/status/date/specialty/urgency and preview age/symptoms/duration/severity, with patient/previous_visits/ai null. Only the accepting doctor gets current intake with matched names, up to three previous visits and AI source/summary/considerations, using build_context. Never expose patient ids or usernames in doctor responses. AI notice is fixed Persian: generated, unverified, not a diagnosis, clinician review only.
- **Configuration:** APP_COOKIE_SECURE=false; APP_SESSION_TTL_HOURS=12 (1-168); optional APP_DEMO_DOCTOR_PASSWORD (8-128, excluded from repr); APP_DOCTOR_AUTO_VERIFY=false; APP_REQUEST_TTL_MINUTES=30 (1-1440). Invalid values name only the variable. No .env loading. Schema v3 adds users, doctors, auth_sessions and visit_requests with foreign-key cascades and required indexes/checks. connect enables foreign_keys and secure_delete and runs schema only below version 3; no migrations framework until a real column change.
- **Seed/presence:** doctors.json becomes seed/catalog data with no online field. Startup upserts fictional doctors verified while preserving existing user_id. Optional demo password creates/refreshes seed doctor accounts whose usernames equal seed ids; without it no seed accounts are created and one safe disabled-logins line is logged. Online means available and verified with last_seen_at within 45 seconds. Seed doctors start offline until dashboards poll; this is single-process SQLite with polling-based presence.
- **Demo:** Persian RTL self-contained login/register tabs and role-specific doctor fields; synthetic-only notice and password autocomplete. Doctor dashboard availability/logout, verification waiting banner, queue previews, accepted details/history/AI box, 409 handling, ten-second visibility-aware polling. Patient demo uses cookie auth, no localStorage patient handle, logout/delete-account, owned history, nullable doctor scores, one broadcast-request button disabled with explanation when no listed doctor is online, and own request status/cancel/accepted-doctor/re-request panel with ten-second pending polling.
- **Acceptance examples:** two online verified doctors see the same preview; concurrent accepts produce one 200 and one 409; the losing queue clears and the patient sees the winner. Different specialty/owner cannot access the request; full details appear only to the accepting doctor. Expired/cancelled requests allow a new request. Patient deletion cascades through users/tokens/intakes/requests. Unverified doctors never count as online.
- **Runnable check:** run unittest discovery before and after with temporary databases and no provider network; register/login helpers use TestClient cookies and preserve existing behavioral assertions. Cover security, config, seed idempotency, auth/roles/ownership, time-controlled presence/expiry, request guards/atomic acceptance/detail isolation, cascades, no-store and pages. Reinstall, run Uvicorn with APP_DOCTOR_AUTO_VERIFY=true, and exercise two doctor browser sessions and one patient session; report automated/manual limits.
- **NOT implemented:** admin approval of doctors, doctor credential checks, doctor account deletion, ratings/reviews, password reset, email verification, MFA, audit log, general rate limiting, HTTPS enforcement, chat or prescriptions. Existing real-data/provider prerequisites remain required.

### Feature: Expanded Persian intake and multiple symptom selection

- **Status:** implemented (approved by the user's intake-question request).
- **User outcome:** record height, weight, main complaint, food/drug allergies, disease history and past medication use, and select several symptoms as easily as several medicines.
- **Scope:** questions in order: age, height_cm, weight_kg, chief_complaint, symptoms, duration, severity, medical_history, medications, medication_history, food_allergies, allergies, confirm. Current medications are labeled «داروهایی که مصرف می‌کنید». The existing allergies field keeps prior data and covers drug/other allergies; food_allergies is separate. No clinical interpretation, BMI, new catalogs, folders or dependencies.
- **API contract:** existing routes and authorization stay unchanged. Collected intake, patient history, bounded provider context and accepted-doctor detail/history gain the six new fields. Pending-doctor previews remain unchanged.
- **Validation:** height in centimeters and weight in kilograms accept positive finite decimal numbers (Persian/Arabic digits and decimal separator included). These are input-format checks, not clinical plausibility checks. All new text answers must be non-empty; «ندارد»/«هیچ» is accepted for histories/allergies. Invalid answers re-ask without saving. Existing 2000-character message bound remains.
- **Agent behavior:** fixed Persian questions; unchanged confirmation/reset behavior. The existing starter red-flag list also checks the new chief complaint before saving, with the same emergency message and redacted transcript behavior. Returning profile confirmation includes all reusable demographic/history fields; an older profile missing the new fields starts a full intake instead of skipping them.
- **Failure behavior:** reuse existing errors. Symptom/medicine editors support add/remove, custom text, case-insensitive deduplication, an exclusive none choice, total length limits and Reset cleanup.
- **Access and data handling:** synthetic data only, existing cookie ownership and accepting-doctor access rules. Atomic SQLite version-4 migration adds nullable columns without deleting old records; historical fields remain null where never answered. No new logging.
- **Configuration:** no new settings.
- **Acceptance examples:** ۳۰ → ۱۷۰٫۵ → ۷۰٫۲ → synthetic complaint → سرفه، تب → duration/severity → histories/current medicines/allergies → بله; symptoms match both cough and fever. Zero, negative, NaN and infinity do not advance measurements; a complaint red flag stores none of that answer.
- **Runnable check:** .\.venv\Scripts\python.exe -m unittest discover tests; state-machine/API/history/context/migration tests and browser checks for symptom multi-selection, custom answers, removal, reset and mobile layout.

### Feature: Doctor-only optional context and inline final review

- **Status:** implemented (approved by the user's optional-context and inline-card request).
- **User outcome:** add optional personal context for the accepting doctor, review grouped answers in the chat, correct one answer without repeating intake, then explicitly confirm.
- **Scope:** add additional_context after allergies and before confirm for new/returning visits. Persian multiline box, optional skip, 2000-character limit. No clinical interpretation of the note. An RTL inline review card groups demographics, complaint/symptoms, history/medicines, allergies and the note; no modal. The question is «اطلاعات ثبت‌شده رو بررسی کردید؟ همه موارد درسته؟» with primary «بله، تأیید می‌کنم» and secondary «ویرایش اطلاعات». Selecting a field reuses its normal controls; save returns to review, cancel leaves data unchanged. Confirmation collapses the card to a confirmed summary and continues existing triage.
- **API contract:** existing message route/body remains compatible, with optional edit_field restricted to collected answer names. Editing is allowed only at unfinished confirm; invalid field/body -> 422, invalid answer -> safe 422, wrong stage/completed -> 409; ownership remains 404. Valid edits preserve all other answers, recompute matching and return confirm. Existing red-flag handling applies to corrected complaint/symptoms. Completed normal messages remain immutable. No new endpoint.
- **Validation:** existing answer validation is reused; the optional note accepts blank/«رد کردن»/skip as no note. No edits to profile/confirm/unknown fields. No note prefilling into a new visit.
- **Agent behavior:** explicit final confirmation remains required after any edit. Negative text confirmation still resets for existing API clients.
- **Failure behavior:** show safe Persian inline errors, keep draft corrections, disable duplicate actions while pending and offer retry. Notes are rendered with textContent, never interpreted as HTML.
- **Access and data handling:** schema v5 atomically adds nullable additional_context without deleting existing data. The patient's own review/history and accepting doctor current/prior visit details can show it; pending/other doctors cannot. Provider context uses an explicit field allowlist excluding the note from both current and previous visits, transcripts and identifiers; only doctor views opt in to notes. No new logging, dependencies or folders.
- **Configuration:** unchanged.
- **Acceptance examples:** fill/skip note -> grouped review; edit age -> one field changes and review returns; edit medicines -> matches update; confirm -> compact success then triage. A unique note marker appears for the accepting doctor but never in the serialized provider request, including subsequent visits.
- **Runnable check:** .\.venv\Scripts\python.exe -m unittest discover tests; note persistence/privacy, field correction/ownership/validation/terminal/concurrency and migration checks, plus RTL desktop/mobile browser verification.

### Feature: Height and weight dropdown choices

- **Status:** implemented (approved by the user's dropdown request).
- **User outcome:** select height or weight instead of typing, including when correcting final-review answers.
- **Scope:** reuse the existing Persian native dropdown: heights 30–250 cm in 1-cm steps and weights 1–300 kg in 1-kg steps, each followed by the custom-answer option. No preselection or automatic submission. Exact decimals and values outside these convenience lists remain editable.
- **API contract:** unchanged; submit the selected numeric text through the existing message/edit flow.
- **Validation:** unchanged positive finite decimal validation; dropdown ranges are convenience choices, not validation bounds.
- **Agent behavior:** existing questions, state transitions, corrections and note privacy stay unchanged.
- **Failure behavior:** reuse current loading, disabled and inline error behavior.
- **Access and data handling:** existing ownership and synthetic-only rules.
- **Configuration:** no new settings, folders or dependencies.
- **Acceptance examples:** select ۱۷۰ cm and ۷۰ kg; custom ۱۷۰٫۵ and ۷۰٫۲ still work; final-review measurement edits offer the same choices.
- **Runnable check:** existing intake/API tests and browser selection/custom-entry/correction checks.
- **Verification (2026-10-26):** .\.venv\Scripts\python.exe -m unittest discover tests -p test_intake.py passed 12 tests; the same command with -p test_chat_api.py passed 13 tests. Browser checks confirmed 221 height choices (30–250) and 300 weight choices (1–300), plus placeholder/custom options; selection requires explicit submission, and custom 170.5/70.2 corrections persist. No browser console errors; git diff --check passed. No new backend behavior, dependencies, folders, commits or pushes.

### Feature: Slice 5 — accepted-visit text chat and doctor-controlled ending

- **Status:** implemented (recorded as approved before application edits).
- **User outcome:** the patient and accepting doctor exchange synthetic text messages and keep history readable after the doctor ends the visit.
- **Scope:** no new folders/dependencies; add services/chats.py, api/chats.py and schemas/chats.py. First remove the expiry sweep from patient_requests: pending rows older than the existing cutoff are projected as expired without updating status/updated_at. Keep sweeps on create/cancel/accept/doctor_requests. Chat reads do not sweep or heartbeat.
- **API contract:** GET /v1/visit-requests/{id}/messages?after=0&limit=50 returns {messages:[{id,sender,content,created_at}],ended,has_more}, ordered ascending with ids > after, limit 1–100; after is a nonnegative SQLite integer. POST the same route with {content:str} returns 201 the created message. Strip before validating 1–2000 characters; forbid extras and derive sender from auth. POST /v1/visit-requests/{id}/end returns {ended:true}, idempotently. PatientVisit/DoctorVisit gain ended; status stays accepted.
- **Validation:** every chat operation requires an accepted request owned by the patient or assigned to the verified doctor; all other requests/callers receive 404. No cookie -> 401. The end route requires a verified doctor (patient/unverified -> 403), with other verified doctors -> 404. Ended chat POST -> 409 visit_ended; at 500 messages -> 409 chat_full. Existing ErrorResponse/no-store rules apply.
- **Agent behavior:** direct human text only; no LLM calls or chat content in provider context. INSERT rechecks participation, ended_at and count inside BEGIN IMMEDIATE. End performs a guarded UPDATE for the accepting doctor only where ended_at IS NULL, then re-reads. Reads remain allowed after ending.
- **Persistence:** atomic, idempotent schema-v6 additive migration checks table_info before adding visit_requests.ended_at, creates visit_messages(id INTEGER PRIMARY KEY AUTOINCREMENT, request_id FK ON DELETE CASCADE, sender_role CHECK patient|doctor, content, created_at) and (request_id,id) index. Fresh/upgraded/concurrent first connections reach the same schema. Patient deletion cascades messages; secure_delete stays enabled.
- **Demo:** both Persian RTL pages get a chat per accepted request, distinct own/other bubbles, multiline input, character counter and Send. Enter sends; Shift+Enter inserts a newline. No duplicate sends. Fixed banner: «این گفتگو برای موارد اورژانسی نیست؛ در شرایط اورژانسی با خدمات اورژانس تماس بگیرید». Doctor ends through an explicit confirmation step. Ended panels lock inputs and retain history.
- **Polling/failure behavior:** poll open visible panels every 3 seconds using after, append new ids only and catch up has_more pages. Pause while closed/hidden; fetch immediately on visibility return. Consecutive errors back off to 10 seconds; success restores 3 seconds. Persian errors distinguish 404, visit_ended, chat_full, validation and network failures; 401 redirects to login. Network read failures retry automatically; ambiguous message-send failures preserve the draft and do not resend automatically without an idempotency key. Scroll down only if already near the bottom or the newly displayed message belongs to the caller. Preserve panel/input/scroll state across dashboard/request refreshes.
- **Access and data handling:** synthetic text only, no message/body/header logging, no other-party usernames/ids or session ids in message responses. textContent only, no CDN. No new retention process or provider integration.
- **Configuration:** existing auth/SQLite settings only; fixed 500-message ceiling and polling intervals.
- **Acceptance examples:** accepting doctor/patient exchange messages; another doctor/patient cannot read/post. End is idempotent, both sides see ended and cannot post; history stays readable. Patient polls leave all database rows unchanged. End/post races never insert after the end.
- **Runnable check:** .\.venv\Scripts\python.exe -m unittest discover tests before/after; migration/authorization/pagination/validation/cap/end/race/read-only/deletion/privacy checks using temporary DBs and patched clocks. Reinstall editable package, run Uvicorn and verify both pages in isolated browser sessions; report manual limits.
- **NOT implemented:** WebSocket/push, attachments, typing/read receipts, unread counts, moderation/reporting, message editing/deletion, retention, audit log, chat export, doctor-to-doctor transfer.

### Feature: Slice 6 — admin doctor review and audit

- **Status:** implemented (recorded as approved before application edits).
- **User outcome:** a configured administrator reviews synthetic doctor registrations, rejects or suspends with a reason, and reinstates through approval; doctors see their status and patients retain ended visit history.
- **UI terminology:** the user approved «شماره نظام پزشکی» for license_number in doctor registration and admin cards, including related hint/error/empty text. Keep synthetic-only/unverified notices and the existing API/storage name and validation.
- **Scope:** no new folders or dependencies. Add services/admin.py, api/admin.py, schemas/admin.py, static/admin.html and tests/test_admin.py. No admin access to patient information, intakes, triage or chat.
- **API contract:** GET /v1/admin/doctors?status=pending&limit=50&offset=0 returns {items:[{id,name_fa,specialty:{code,name_fa},expertise,license_number,registered_at,status,reviewed_at,review_note}],total}. Status is pending|approved|rejected|suspended; limit 1–100 and offset a nonnegative SQLite integer. Pending sorts oldest registration first, other lists newest review first. POST /v1/admin/doctors/{id}/approve returns the updated item; POST reject/suspend takes {note:str}, stripped length 3–300 with extras forbidden. GET /v1/admin/audit?limit=50 returns newest-first {items:[{id,action,doctor_id,doctor_name_fa,from_status,to_status,note,created_at}]}, limit 1–100; missing doctor names are null. GET /admin serves the self-contained page.
- **Validation:** DoctorRegistration requires stripped license_number matching ^[A-Za-z0-9-]{4,20}$; duplicates -> 409 license_unavailable. Reserve the configured admin username, literal admin and seed-doctor ids. Registration cannot supply status/verified or role admin. Public doctor account adds status and review_note; admin display_name is «مدیر سیستم», doctor=null.
- **Agent behavior:** reuse existing auth, cookies and login throttle; admin_user requires role admin. Every patient/doctor data endpoint, including visit chat, rejects admins with 403. Non-admin /v1/admin calls return 403; no cookie -> 401. ErrorResponse and no-store apply. Rejected/suspended doctors may log in but doctor data endpoints remain 403.
- **Persistence:** schema v7 rebuilds users with patient|doctor|admin role CHECK, preserving columns, rows, indexes and foreign-key references. With no transaction: disable foreign keys, BEGIN IMMEDIATE, recheck version, create/copy/drop/rename users, add doctor columns, create unique non-null license index and admin_audit with created_at index, foreign_key_check, set version, commit; restore foreign keys even on failure. Roll back on error and permit retry. Existing verified doctors become approved once; others pending. Concurrent connections cannot downgrade schema. Audit has no foreign keys; store only admin/doctor ids, action, statuses, synthetic review note and timestamp.
- **Transitions:** one guarded UPDATE plus rowcount check under BEGIN IMMEDIATE; unknown -> 404, wrong state -> 409 invalid_transition. Set review_status, matching verified, reviewed_at and review_note together. Approve clears note; reject/suspend clear availability and heartbeat. Suspend ends all accepted unended visits for that doctor at the same timestamp and writes one audit row in the same transaction. Reinstatement leaves ended visits ended and availability off until the doctor opts in. Seed refresh must preserve admin review decisions.

| Action | Allowed from | To | Note |
| --- | --- | --- | --- |
| approve / reinstate | pending, rejected, suspended | approved | cleared |
| reject | pending | rejected | required |
| suspend | approved | suspended | required |

- **Access and data handling:** admins see only doctor registration metadata and review audit, never usernames/passwords/patient data. Patients see only existing owned data and the doctor's public projection; doctors see their own review note via /v1/auth/me. No credentials, review notes or message bodies in logs. License numbers are fake and unverified.
- **Configuration:** APP_ADMIN_USERNAME and APP_ADMIN_PASSWORD are hidden from Settings repr, both or neither; incomplete pair raises ValueError naming both variables. Username ^[a-z0-9_.-]{3,32}$, password 12–128. Startup creates/refreshes only the configured admin, refuses patient/doctor username clashes with variable-only ValueError, and logs admin_disabled without secrets when unset. Disabled/unconfigured admin credentials do not grant access. APP_DOCTOR_AUTO_VERIFY remains false by default; true is a local-demo shortcut bypassing review.
- **Local environment file:** the user approved storing admin credentials in the ignored root .env. Use installed uv with --no-project --env-file .env and the explicit .venv Python to launch Uvicorn; uv populates the child process environment, while Settings remains standard-library/os.environ-only. No application auto-loading, new dependencies or folders. Keep actual credentials out of tracked files and command output. Verified env loading, Settings validation and admin seeding/login using a temporary database; git check-ignore confirms .env is ignored.
- **Demo:** Persian RTL inline CSS/vanilla JS/textContent only. Login adds synthetic license input, waiting message and role redirects. Admin page shows pending count, status/audit tabs, pagination, metadata cards, approve and inline reason/confirmation controls, status-specific errors and conflict refresh; visible-tab refresh every 15 seconds. Doctor page polls own status, displays pending/rejected/suspended notices with safe note text, hides all patient UI and unlocks after approval. Both existing pages redirect admins to /admin.
- **Failure behavior:** preserve review drafts during refresh; do not automatically repeat ambiguous writes. Refresh after conflicts. Doctor suspension clears cached patient UI; patient history remains readable with chat locked. Migration/seeding failure prevents startup without leaking contents.
- **Acceptance examples:** pending registration -> approve -> doctor access; suspend with note -> doctor denied and only that doctor's open visits ended; rejected/suspended -> approve; two concurrent approvals -> one success, one 409, one audit row.
- **Runnable check:** unittest before/after with temporary databases and no network, config/seeding/license/role/transition/audit/concurrency/migration rollback and preservation checks; reinstall editable package and browser walkthrough with distinct synthetic accounts. Report actual private-window and browser limitations.
- **NOT implemented:** real license verification, admin user management and self-service password reset, multi-admin roles, admin MFA, per-IP rate limiting, alerting on admin actions.

### Feature: Slice 7a — shared dashboard shell and continuous conversations

- **Status:** approved.
- **User outcome:** resume an existing conversation and continue intake, triage, requesting, acceptance and direct chat in one thread; navigate patient, doctor and admin dashboards through a shared accessible RTL sidebar.
- **Scope:** add only static/shell.css and static/shell.js in existing folders. Reuse current tokens/type, auth, intake/review/editing, triage, visit and chat rules. No schema changes, dependencies, profile/password features or login-page changes.
- **API contract:** patient-only GET /v1/chat/sessions?limit=20 (1–50) returns newest-first {session_id,created_at,summary,step,done,emergency,status,specialty,request_id} items. Summary is first 80 characters of complaint, otherwise symptoms, otherwise null. One joined SQL query with the latest request per session; no per-item queries. GET /v1/chat/sessions/{id}, owned_session protected, returns {session:ChatResponse,transcript:[{role,content,created_at}] in stored order/max 200,triage:TriageResponse|null,request:PatientVisit|null}. Stored triage only through patient_response, never run_triage/provider or doctor-only fields. Unknown/other-patient -> 404; doctor/admin -> 403. Both GETs are read-only and no-store.
- **Visit projections:** PatientVisit adds session_id, accepted_at and ended_at; DoctorVisit adds accepted_at and ended_at. Nullable timestamps reflect existing stored data; no writes or schema changes.
- **Status precedence:** emergency intake wins; otherwise use the latest request (accepted becomes ended when ended_at exists); overdue pending projects expired with the same TTL cutoff without writes; then done -> triage, else intake. Specialty is stored triage specialty, otherwise latest request specialty, otherwise null.

| Status | Persian label |
| --- | --- |
| intake | در حال ارزیابی |
| triage | پیشنهاد پزشک |
| pending | در انتظار پزشک |
| accepted | در گفت‌وگو با پزشک |
| ended | ویزیت پایان‌یافته |
| expired | منقضی‌شده |
| cancelled | لغوشده |
| emergency | توقف اضطراری |

- **Shared shell:** explicit allowlisted GET /assets/shell.css (text/css) and /assets/shell.js (text/javascript), Cache-Control:no-cache; unknown/traversal -> 404 ErrorResponse. Package CSS/JS. Role-neutral Shell API handles top bar, display name/logout slot, labeled sidebar nav, active links and hash/back/forward/default routing. Desktop >=900px defaults open and safely persists toggle preference; mobile defaults closed without persistence, inline-start drawer/backdrop/Esc/focus trap/focus return/body scroll lock. Respect reduced motion and visible keyboard focus. Use existing forest tokens/system fonts; no design.md or additional design files/folders.
- **Patient routes and loading:** #/new and #/c/<session_id>; list, new-conversation button and confirmed account deletion in sidebar. On load list then reopen newest; create only if none. Confirm leaving an unfinished intake for New, retaining it in the list. Refresh after state changes and every 10 seconds while visible if anything is pending. Keep history API but stop calling it in the UI.
- **Thread order:** collected-data disclosure first, then stored/live intake bubbles and editable inline final review, one in-place triage bot card with doctor cards/retry/request, request/cancel/expiry/re-request system item, acceptance/doctor profile item, direct messages, finally ended system line/New CTA. One scrollable log and one composer whose modes are intake, triage/waiting, doctor chat, read-only ended/full/emergency. Keep required Persian copy and synthetic/emergency notices.
- **Doctor routes:** #/queue and #/patient/<request_id>. Sidebar queue badge, accepted active-first/ended-last visits with urgency/specialty/age/symptom excerpt, availability/presence and name. Accept opens thread; conflict refreshes queue. Thread starts with «گزارش سامانهٔ پذیرش» and accepting-doctor-only fields/history/AI warning, followed by direct messages and end confirmation. Keep 10-second heartbeat poll and five-second review-status poll; unapproved states have no patient UI.
- **Admin routes:** #/pending, #/approved, #/rejected, #/suspended, #/audit. Existing tabs become sidebar items; preserve notes/confirmations/paging/conflict refresh and 15-second visible polling.
- **Failure behavior:** chat retains 3-second visible/open-only cursor polling, deduplication, has_more catch-up, consecutive-error 10-second backoff, uncertain-POST draft preservation/no automatic resend, status errors, 500-message cap and 2000-character bound. Stop polling on navigation; avoid late responses updating another thread. Scroll only near bottom or for own sends. Preserve drafts/scroll across list refreshes. All dynamic text uses textContent; no HTML injection/eval APIs.
- **Access and data handling:** synthetic data only; owned conversations and existing accepted participants only, no other-user identifiers in responses. Shared assets contain no credentials or role-specific policy. Existing auth redirects/logging/no-store remain in force.
- **Configuration:** none; existing .env/uv launch path and Settings behavior unchanged.
- **Acceptance examples:** reload mid-intake resumes without another session; sidebar switches thread and pauses old chat polling; full patient/doctor flow stays in one thread; ended history is readable; keyboard/mobile drawer and admin routes work.
- **Runnable check:** baseline/final unittest discovery with temporary databases/no network; add list/detail/status/ownership/stored-triage/redaction/read-only/visit-field/asset/static checks to existing test files. Reinstall and test real browser at 1280/390px plus smaller responsive widths; report unverified cases.
- **NOT implemented:** unread counts, push, per-conversation deletion, conversation search, unfinished-session cleanup/caps, profile or password features (Slice 7b).

### Feature: Slice 7b — profiles, password change and dedicated heartbeat

- **Status:** approved.
- **User outcome:** patients edit a reusable health profile without changing past assessments; doctors edit their professional profile with review safeguards; patient/doctor accounts change passwords and sign out other sessions; verified doctors remain present while working in another tab.
- **Scope:** existing folders/dependencies, synthetic data only. Reuse existing shell, validators, password hashing/throttle helpers, profile fields, dictionary matching and transactional SQLite patterns. Do not commit or push.
- **Heartbeat contract:** POST /v1/doctor/heartbeat, verified doctor only (403 otherwise), no body, 204. One BEGIN IMMEDIATE updates that doctor's last_seen_at and sweeps expired pending requests. This POST is the only presence refresh; existing offline-clearing operations remain. GET /v1/doctor/requests is read-only, excludes overdue pending rows using the existing TTL cutoff, and performs no sweep. ONLINE_SECONDS=90; browser heartbeat every 20 seconds regardless of visibility, immediately after identity load and availability-on; 403 refreshes identity and transient failures are ignored. Request refresh remains 10 seconds/visible-only; identity refresh becomes 15 seconds/visible-only.
- **Database:** additive schema-v8 migration creates patient_profiles with patient_id PK/cascading patient FK; nullable age INTEGER, height_cm/weight_kg REAL and five profile text fields; medication_codes TEXT NOT NULL DEFAULT '[]', updated_at TEXT NOT NULL. Add nullable doctors.resubmitted_at after checking table_info. Backfill once from each patient's latest completed, non-emergency session having all PROFILE_FIELDS non-null, ordered updated_at/created_at/rowid descending; copy stored medication_codes. Fresh/upgraded schemas match, concurrent first connections are safe, failed migration rolls back and can retry. Deletion cascades with secure_delete enabled.
- **Patient API:** GET/PATCH /v1/patient/profile, patient only, returns {profile:{age,height_cm,weight_kg,medical_history,medications,medication_history,food_allergies,allergies},updated_at:str|null,complete:bool}; unset values are null. PATCH forbids extras/nulls, requires at least one field, age integer 0–120, positive finite height/weight through a shared pure intake parser (Persian decimal accepted), stripped text 1–2000. Recompute medication_codes when medications changes; set updated_at. No red-flag screening on profile fields.
- **Prefill and completion:** new sessions use patient_profiles only; complete profiles get the current welcome-back/profile-confirmation flow. Completion of a non-emergency intake upserts profile fields/codes in the same transaction only if the existing profile updated_at is not newer than the session created_at. Emergency stops never update profiles. Profile edits never modify old sessions, transcript/history, doctor context or stored triage; only new assessments use edits.
- **Doctor API:** GET/PATCH /v1/doctor/profile, any doctor account. GET returns exactly {name_fa,specialty:{code,name_fa},expertise,license_number,score,status,review_note,resubmitted_at}. PATCH forbids extras/protected fields/nulls and requires at least one field: name_fa stripped 2–60, expertise 2–3 stripped strings of 2–40, SpecialtyCode specialty_code, stripped ASCII license ^[A-Za-z0-9-]{4,20}$. Check duplicate license and update within BEGIN IMMEDIATE; duplicate -> 409 license_unavailable. Keep verified=(review_status='approved') in the same UPDATE. Admin review projections gain resubmitted_at; pending cards show «ارسال مجدد پس از تغییر مشخصات» plus date.

| Doctor status | Profile edit rule |
| --- | --- |
| approved | Name/expertise edits remain approved. Actual specialty/license changes require no accepted unended visits (409 active_visits, atomic no-op otherwise); move to pending, verified/available=0, presence/note cleared, resubmitted_at=now. Auto-verify keeps approval and bypasses the active-visit restriction. |
| pending | Any editable field may change; status remains pending. |
| rejected | Any actual change resubmits to pending (or approved with auto-verify), clears note, sets resubmitted_at, preserves reviewed_at. |
| suspended | 403 profile_locked; password changes remain allowed. |

- **Password API:** POST /v1/me/password {current_password,new_password}, extras forbidden; new 8–128 characters and different (422). Admin and doctors.json-id usernames -> 409 password_managed with server-configuration message. Verify current password using security.verify_password; wrong -> 401 invalid_current_password without login redirect. Reuse throttle under 'pw:'+username: five failures/15 minutes, 429 with Retry-After, success clears. Atomically update hash and delete other auth sessions while preserving current-cookie session and cookie; 204. Never log passwords.
- **Pages:** patient #/profile is an explicit allowed route/sidebar item, increments routeVersion, disposes live chat and hides thread/composer; navigating back restores conversation. Editable health form has Persian labels, field/general errors, success/incomplete states and past-conversation disclaimer; account deletion with confirmation moves here. Doctor #/profile remains available while unverified/waiting; form has specialty catalog, name/expertise/license, read-only score/status/note and password form. Confirm specialty/license re-review, map active_visits/license_unavailable/profile_locked to clear Persian errors and refresh identity after save. Shared password form checks confirmation, uses correct autocomplete, handles 401/422/429 Retry-After and managed-password 409 without redirect; success says other devices signed out. Admin has no profile page. TextContent-only rendering, existing forest tokens, RTL and responsive/focus behavior remain.
- **Acceptance examples:** edit patient profile then start new intake and see edited welcome-back; finish stale unfinished intake without overwriting a newer profile edit; change password while another browser session becomes unauthorized; freely edit approved doctor name/expertise, reject specialty change during active visits, then resubmit after ending and see admin marker; doctor stays online during two minutes in another tab.
- **Runnable check:** baseline and final full unittest suites, temporary databases/no network. Cover migration/backfill/rollback/concurrency/equivalence, heartbeat-only presence/read-only GET/89–91-second bounds, patient validation/ownership/stale completion/history preservation/cascade, every doctor status/auto-verify/uniqueness/sync rule, password hash/throttle/session/log privacy, static route/sink checks. Editable install and real-browser walkthrough; report anything unverified.
- **NOT implemented:** email/phone fields, password reset by email, MFA, account recovery, doctor account deletion, profile change history/audit, profile photos.

### Feature: independent doctor–Codex assistant chat

- **Status:** approved.
- **User outcome:** verified doctors open «دستیار پزشک» in their dashboard and independently discuss synthetic clinical cases with Codex, using the server operator's dedicated login.
- **Scope:** Persian RTL streaming chat at #/assistant; no automatic intake, profile, visit, previous-task or repository context. No record retrieval, browsing, prescriptions, patient-facing responses or workflow actions. No new folders, dependencies or schema migration (schema stays v8).
- **API contract:** POST /v1/doctor/assistant/messages accepts {messages:[{role:user|assistant,content:str}]} with completed alternating pairs followed by the latest user message. Verified doctors only. SSE delta {text}, done {}, error {error:{code,message}}; only final assistant answer text is forwarded. Before streaming, existing ErrorResponse: 401/403 authorization, 422 validation, 429 concurrency, 503 missing/unusable/unsafe runtime, 504 deadline.
- **Validation:** forbid extra fields and system/developer roles, require nonempty stripped content and valid order; user messages at most 4,000 characters, at most 40 submitted messages and 40,000 total characters. Never silently truncate history. Bound generated output at 20,000 characters and request a new chat when history is full.
- **Agent behavior:** one server-owned prompt in agent/doctor_assistant.py instructs Persian clinical decision support for physician review, focused questions, uncertainty, no invented findings/references/record access, urgent-situation limitations, no confirmed diagnoses/final prescriptions, untrusted conversation data and no tools. Use the approved prompt verbatim with one format instruction for the submitted JSON transcript.
- **Runtime/isolation:** use stdlib subprocess stdio with codex app-server, a dedicated APP_CODEX_HOME outside this repository and the developer's Codex home, and an empty temporary working directory. APP_CODEX_MODEL optionally overrides the operator's model. Check installed protocol isolation fields, strict configuration and an ephemeral thread with no environments/capability/workspace roots. Disable shell/files, MCP/apps/plugins/skills/hooks/search/memories/delegation; reject unexpected tools/approvals and fail closed when isolation cannot be enforced. No existing threads are resumed or credentials copied by the application.
- **Failure behavior:** 120-second deadline, no automatic retries, safe Persian UI messages, Stop/navigation/disconnection interrupts and terminates/reaps the subprocess. One active call per doctor and two globally per application process; ponytail comments describe process-local scaling and subprocess overhead ceilings.
- **Access and data handling:** no database/log transcript writes or browser storage. Page memory retains completed turns across navigation; reload/logout/New Chat clears them. Interrupted turns are visibly marked and excluded from future context. Provider-side handling is separate from application persistence. Never log credentials, raw Codex output, prompts or answers.
- **Demo:** reuse forest tokens, responsive layout and synthetic banner. Doctor/assistant bubbles, labeled multiline composer (Enter sends, Shift+Enter newline), Send/Stop/New Chat, clear loading/errors and «پاسخ هوش مصنوعی پیشنهادی است و نیاز به بررسی پزشک دارد.» Render textContent only.
- **Acceptance examples:** first answer streams; follow-up includes only this chat's completed turns; navigation aborts while retaining completed history; New Chat/reload clears it; unverified doctors cannot call it; unavailable login/runtime displays a safe failure without affecting existing dashboard/heartbeat.
- **Runnable check:** baseline/final full unittest suites; new mocked-protocol checks for validation/access/isolation/ephemeral streaming/failures/cancellation/deadline/cleanup/concurrency/privacy; desktop/mobile browser checks and a synthetic live Codex check only if a dedicated login is available. Report all unverified behavior. Do not commit or push.

## 6. Coding and verification rules

- Trace the affected flow and callers before changing shared behavior.
- Validate untrusted inputs at API and external-service boundaries.
- Use explicit request and response models when a feature introduces structured data.
- Handle external-service failures without exposing credentials or sensitive payloads.
- Define timeouts for external calls when integrations are introduced.
- Keep secrets out of code; document required settings in `.env.example` and
  `README.md` when configuration is implemented.
- Use synthetic examples and test data for healthcare workflows.
- Leave one small runnable check for non-trivial logic. Prefer an assert-based
  check or the standard library's `unittest`; trivial one-liners need no test.
- Fix root causes in shared functions instead of adding duplicate caller guards.
- Mark deliberate shortcuts with a `ponytail:` comment stating their ceiling
  and the upgrade path.

## 7. Implementation checklist

- [x] Create `src/`, `tests/`, and `docs/`.
- [x] Add dependency configuration, setup instructions, and a minimal FastAPI app.
- [x] Add this starter specification.
- [x] Move the application into the approved `app` package and remove `src/main.py`.
- [x] Add environment settings, typed responses, a health router, generic HTTP/validation errors, and basic logging.
- [x] Add unittest checks and the optional `httpx` dev dependency.
- [x] Verify installation, tests, and live `/health` and `/docs` responses for the skeleton.
- [x] Define the first workflow: Slice 1a scripted synthetic intake.
- [x] Write and approve the Slice 1a specification before implementation.
- [x] Implement Slice 1a state machine, bounded sessions, chat API, and single-file demo.
- [x] Add intake/API checks and run all 23 unittest checks, including Persian localization and dropdown answers.
- [x] Update setup, structure, API, and demo usage documentation.
- [x] Reinstall the editable dev package and verify static HTML in package sources.
- [x] Verify live /health, /docs, /demo, full HTTP intake, red-flag stop, and inline JavaScript syntax.
- [ ] Complete a synthetic intake manually through /demo; blocked by the browser-control runtime failure.

## 8. Definition of done for a feature

The agreed acceptance examples work, the relevant runnable check passes, errors
follow the documented contract, and configuration and usage instructions are
current. Report any unverified behavior or remaining limitations explicitly.

## 9. Package structure and verification

- `src/app/__init__.py`, `src/app/api/__init__.py`, and `src/app/schemas/__init__.py`: package markers.
- `src/app/main.py`: app creation, lifespan, and router registration.
- `src/app/core/__init__.py`: approved core package marker.
- `src/app/core/config.py`: frozen environment settings.
- `src/app/core/db.py`: SQLite schema, connections, message inserts, and UTC timestamps.
- `src/app/core/errors.py`: HTTP, validation, and SQLite exception handlers and registration.
- `src/app/core/llm.py`: synchronous provider transport with safe outcome categories.
- `src/app/agent/context.py`, `triage.py`, `doctors.py`: bounded context, stored results, and fictional directory.
- `src/app/schemas/triage.py` and `src/app/data/doctors.json`: triage contracts and synthetic doctors.
- `tests/test_llm.py` and `tests/test_triage.py`: network-free Slice 3 checks.
- `src/app/core/logging_config.py`: logging configuration and shared access-log disabling at import and lifespan startup.
- `src/app/api/health.py`: health endpoint. `chat.py` provides intake/triage POSTs and owned read-only conversation list/detail GETs; `demo.py` serves the pages and two explicit no-cache shared assets.
- `src/app/static/shell.css`, `shell.js`: shared RTL dashboard navigation, responsive drawer and reusable direct-chat rendering; packaged alongside HTML. Login remains self-contained.
- `src/app/schemas/common.py`: `HealthResponse`, `ErrorResponse`, and its nested error model.
- `src/app/services/chats.py`, `api/chats.py`, `schemas/chats.py`: accepted-visit participation, message pagination/insertion and doctor-controlled ending; distinct from scripted intake in api/chat.py.
- `src/app/services/visits.py`, `schemas/visits.py`: read-only patient expiry projection, doctor heartbeat/sweep, broadcast/acceptance and ended visit items.
- `tests/test_chats.py`: schema-v6 migration, direct-chat access, limits, concurrency, read-only polling and deletion/privacy checks.
- `src/app/services/admin.py`, `api/admin.py`, `schemas/admin.py`, `static/admin.html`: configured admin seeding, doctor review/audit projections and Persian panel, without patient data access.
- `tests/test_admin.py`: admin configuration, seeding, license/role boundaries, transitions, audit, suspension, schema-v7 preservation/concurrency/rollback checks.
- `tests/test_health.py`: health and settings checks.
- `tests/test_errors.py`: unknown path, validation privacy, and HTTP exception privacy checks.

`HealthResponse` fixes status to `ok`. HTTP errors use the shared error shape
`{"error": {"code": "http_404", "message": "Not Found"}}` with the actual status
and standard status message. Validation errors return HTTP 422 with code
`validation_error` and message `Request validation failed`. Handlers do not
return exception details or request input. Basic logging does not log request
bodies or headers; HTTP client debug logging is suppressed.

From the project root in PowerShell (create `.venv` first if absent):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover tests
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir src
```

With the server running, use another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
(Invoke-WebRequest http://127.0.0.1:8000/docs).StatusCode
```

Expected: health returns `status: ok`; documentation responds with HTTP 200.
The virtual environment and installer outputs are generated tooling artifacts,
not additional application architecture folders.

Verification completed on 2026-10-25 with Python 3.14.7: editable dev install
succeeded, all five unittest checks passed, and live /health and /docs returned HTTP 200. The installed Starlette version warns that its httpx
TestClient integration is deprecated; the requested httpx dependency is retained.

## 10. Slice 1a implementation details

- `src/app/agent/intake.py`: immutable dataclass state and pure `advance(state, message)` returning state and reply.
- `src/app/agent/sessions.py`: bounded dict. Async chat handlers call synchronous store operations without yielding; use one process/event loop.
- `src/app/schemas/chat.py`: typed message/session models; collected fields reuse the intake dataclass.
- `src/app/api/chat.py` and `demo.py`: routers included by `src/app/main.py`.
- `src/app/static/index.html`: self-contained demo included as setuptools package data.
- `tests/test_intake.py`: all steps, validation hints, numeric boundaries, reset, every red flag, and terminal immutability.
- `tests/test_chat_api.py`: API contracts, invalid bodies, isolation, oldest-session eviction, and HTML delivery.
- Normal completion keeps step=confirm; an emergency stop keeps step=symptoms. Reset creates a fresh session; old sessions remain until eviction/restart.
- This phase makes no commits and does not push.

### Slice 1a verification (2026-10-25)

Editable installation succeeded with the previously approved process-only proxy
bypass. All 19 unittest checks passed. Live /health, /docs, and /demo returned
HTTP 200; creating a session returned 201. A full synthetic intake completed
over HTTP, final-state immutability passed, and a red-flag stop returned
emergency=true with symptoms=null. Node's syntax check passed for the inline
JavaScript, and setuptools SOURCES.txt includes static/index.html.

Manual browser interaction, mobile layout, and visual rendering remain unverified:
the computer-use Node runtime failed twice because its kernel.js file is missing.
Opening the demo in Codex was queued. The installed Starlette/httpx deprecation
warning remains; no dependencies were changed. No commits or pushes were made.

### Persian localization verification (2026-10-25)

All 22 unittest checks passed. The Persian demo returned HTTP 200 with UTF-8
and RTL markup; inline JavaScript passed the Node syntax check. A full Persian
intake completed over live HTTP using Persian digits and confirmation, and a
Persian red-flag answer with Arabic letter variants stopped without storing
symptoms. The local demo server was restarted to load the translated replies.
Visual and manual browser checks remain unverified because the previously
reported browser-control runtime is unavailable. No new folders or dependencies
were added, and no commits or pushes were made.

### Dropdown verification (2026-10-25)

All 23 unittest checks passed. An automated headless Chrome check against the
live demo passed: numeric dropdown choices, custom entry, a full intake through
the page, disabled controls on completion/failure, Reset, inert rendering of
HTML-like synthetic input, and no horizontal overflow at widths 320, 375, 414,
and 768 pixels. A temporary browser profile was removed after testing; no
folders or dependencies were added to the repository. This was an automated
browser check, not a manual visual inspection. No commits or pushes were made.

## 11. Slice 2a implementation checklist

- [x] Record the approved specification before implementing code.
- [x] Approve only src/app/data/ and add the two 12-entry JSON vocabulary files.
- [x] Add sanitized validation, cached startup loading, shared normalization, whole-phrase matching, and substring search.
- [x] Add the read-only dictionary API, typed responses, computed chat matches, and Persian side-panel chips.
- [x] Keep intake.py unchanged and preserve the existing 23 tests.
- [x] Add dictionary checks; all 39 unittest tests pass.
- [x] Update README, changelog, and package-data configuration.
- [x] Reinstall the editable dev package and verify JSON packaging.
- [x] Restart Uvicorn and complete a synthetic intake in /demo to verify chips (automated browser).
- [x] Record final checks and the manual visual-inspection limitation; stop after this slice.

### Slice 2a verification (2026-10-25)

- Editable dev installation succeeded using the previously approved process-only proxy bypass.
- All 39 unittest tests passed, including the original 23; Starlette's existing httpx deprecation warning remains.
- Setuptools SOURCES.txt includes data/symptoms.json and data/medicines.json.
- Uvicorn started successfully with cached dictionary validation during lifespan startup.
- An automated headless Chrome intake showed cough/fever chips for the Persian symptom answer and no medicine chips for the none answer.
- A generic medicine alias displayed its Persian chip; unmatched symptoms showed no chips, and Reset cleared previous chips.
- Existing dropdown, terminal/error-state, inert text rendering, and widths 320/375/414/768 checks passed in the browser.
- intake.py is unchanged. No new dependencies, commits, or pushes were made.
- The browser check was automated; no manual visual inspection was performed.

### Default symptom dropdown verification (2026-10-25)

All 40 unittest tests passed. The automated browser check confirmed all 12
JSON-backed Persian symptom names in the dropdown, selected-answer submission
and its resulting chip, custom entry, Reset, dictionary-loading failure
handling, a complete intake, and mobile widths 320/375/414/768. No folders,
dependencies, commits, or pushes were added.

### Multi-medicine editor verification (2026-10-25)

All 42 unittest tests passed, including every default medicine name and a
multi-medicine answer with preserved custom text. The automated Chrome check
verified the 12 JSON-backed names, multi-add/remove, case-insensitive duplicate
prevention, custom Add/Enter input, exclusive none, 2000-character total limit,
Reset cleanup, pending-control locks, retention of unfinished input across
choice changes, final submission, and separate matched medicine chips.
Mobile widths 320/375/414/768 and the earlier symptom/chip flows passed.
No API fields, intake behavior, folders, or dependencies were changed.
No commits or pushes were made. No manual visual inspection was performed.

## 12. Slice 2b implementation checklist

- [x] Record approved SQLite/manual-deletion/privacy decisions before implementation.
- [x] Add DB-path settings, ignore rules, schema, UTC timestamps, indexes, and explicit connection cleanup.
- [x] Replace the in-memory store with atomic SQLite transactions and redacted message logs.
- [x] Add pure profile confirmation, returning-patient lookup, stored-code history, and cascade deletion.
- [x] Convert chat routes to synchronous handlers and build named public response fields.
- [x] Add guarded demo patient memory, profile choices, history, and forget-me.
- [x] Convert all database-capable tests to temporary files and remove the obsolete eviction test.
- [x] Run 61 unittest checks, including rollback, initialization cleanup, and concurrent-message coverage.
- [x] Reinstall editable dev package and run the final full suite.
- [x] Verify complete/reload/profile/history/forget-me and unavailable storage in the browser.
- [x] Record verification output and stop without commits or pushes.

### Slice 2b verification (2026-10-25)

- Editable dev installation succeeded with no new dependencies.
- All 61 unittest tests passed using temporary databases only. The default healthcare_agent.db file was never opened or created by verification.
- Covered persisted sessions, ordered messages/codes, profile yes/no paths, emergency/unfinished exclusions, stored-code fallback, history bounds/order/404, cascade deletion, no-body compatibility, connection cleanup, atomic rollback, and concurrent messages.
- Uvicorn started with a dedicated temporary APP_DB_PATH for browser verification.
- Automated Chrome completed an intake, reloaded into the same patient's Persian profile, displayed prefilled data/history/chips, verified profile confirmation/rejection, and used forget-me to remove the old patient's history and start fresh.
- Stale/corrupt stored ids and localStorage throwing on read/write/remove were exercised; intake, same-patient Reset, and forget-me continued working.
- Mobile widths 320/375/414/768 passed overflow checks. Uvicorn access logging is disabled.
- The installed Starlette/httpx deprecation warning remains. Manual visual inspection was not performed.
- No folders, commits, or pushes were added. The review server uses a temporary verification database; ordinary startup uses APP_DB_PATH or its documented default.

## 13. Core infrastructure refactor

- [x] Approve only src/app/core/ and move config.py and db.py with git mv, without compatibility shims.
- [x] Move the three exception-handler signatures and bodies verbatim; centralize registration.
- [x] Move logging setup and share access-log disabling between import-time configuration and lifespan startup.
- [x] Update all source/test imports and the documented package structure.
- [x] Run the same unittest discovery before and after: 61 tests pass in both runs.
- [x] Reinstall the editable dev package and verify live /health, /docs, and /demo return HTTP 200.

### Refactor verification (2026-10-25)

Before editing: Ran 61 tests in 5.176s; OK. After editing: Ran 61 tests in
8.082s; OK. The existing Starlette/httpx deprecation warning remains.
Editable installation succeeded using the previously approved process-only
proxy bypass. Uvicorn started successfully using a dedicated temporary
APP_DB_PATH; the default database was not created.

Source comparisons confirmed verbatim handler signatures/bodies, unchanged
settings, and only an import change within the moved database module.
Invalid APP_LOG_LEVEL still fails at import; HTTP exception headers and
import-time logging settings are preserved. Searching repository files found
no old import paths. No behavior, endpoint, schema, setting, error code, or
message changes were made. No commits or pushes were made.

## 14. Slice 3 implementation checklist

- [x] Record the approved section 5 specification before application edits.
- [x] Add secret-safe LLM settings, synchronous transport, strict result validation and outcome-only logging.
- [x] Add and validate 12 fictional doctors across nine specialties at startup.
- [x] Build bounded identifier-free context and persist the first result after closing the context connection.
- [x] Add schema version 2, cascading deletion, the triage endpoint, fallback and emergency response behavior.
- [x] Add Persian loading, specialty/urgency/reason/notice, doctor cards, retry and Reset/forget-me cleanup.
- [x] Promote httpx to runtime, remove the dev extra and update install commands and configuration examples.
- [x] Run all existing and new unittest checks with temporary databases and no provider network calls.
- [x] Reinstall, start Uvicorn and verify fallback through the demo in an automated browser.

### Slice 3 verification (2026-10-25)

- Baseline: Ran 61 tests in 7.976s; OK. Final: Ran 84 tests in 11.182s; OK. The existing Starlette/httpx deprecation warning remains.
- The requested pip install -e . succeeded, using the previously approved process-only proxy bypass. Package sources include doctors.json and all new modules; no folders or additional libraries were introduced.
- Network-free tests cover request URL/auth/body/timeout, safe failure logging, settings, strict result bounds, doctors validation/order/limit, bounded context, v1-to-v2 schema initialization, persistence, repeat calls, emergency/404/409 paths, public field exclusion, cascade deletion and concurrent requests.
- During a stubbed provider call, all context connections are closed and another connection can BEGIN IMMEDIATE. Deleting a patient during that call does not recreate data.
- Uvicorn started with a dedicated temporary APP_DB_PATH. Live /health, /docs and /demo returned HTTP 200; OpenAPI exposes the public triage contract without doctor-only fields. The default healthcare_agent.db was not created.
- Headless Chrome completed a Persian intake with no provider configured and showed the general-practice fallback, two fictional doctors, Persian scores, unknown urgency and fixed notice.
- Automated page checks passed loading, failed-request Retry/recovery, Reset cleanup, inert rendering of HTML-like provider text, doctor-only field exclusion, and widths 320/375/414/768. Emergency-stop intake made no triage request.
- No real provider was configured, so no real-provider result was tested. The native/browser UI-control runtimes could not initialize because their runtime files were missing; the demo check used installed headless Chrome. Manual visual inspection was not performed.
- No commits or pushes were made. Stop after Slice 3.

## 15. Stored fallback retry fix

- [x] Keep stored LLM results immutable and return them without another provider call.
- [x] Retry a stored fallback only when the provider is configured; valid output conditionally updates only source=fallback.
- [x] Preserve stored results after failed retries and keep the original INSERT OR IGNORE path for first calls.
- [x] Keep context connections closed and SQLite transactions absent during first and retry provider calls.
- [x] Document the per-retry provider-call cost and the cooldown/rate-limit upgrade path.
- [x] Run the full unittest suite before and after the fix, using temporary databases and no provider network calls.

### Fallback retry verification (2026-10-25)

Command: .\.venv\Scripts\python.exe -m unittest discover tests

Before editing: Ran 84 tests in 13.243s; OK.
After editing: Ran 88 tests in 13.731s; OK.

The four new tests cover failed-provider fallback followed by success,
failed retries preserving every stored fallback field, no provider call for
unconfigured stored fallback, and delayed concurrent success/failure retries
that cannot overwrite or return an older fallback after an LLM result wins.
Existing tests still cover LLM reuse and two concurrent first calls keeping
one row. Connection/transaction checks now exercise both first calls and
fallback retries.

The existing Starlette/httpx deprecation warning remains. Provider calls
were mocked; no live-provider or browser check was run for this fix.
No schema, endpoint, folder or dependency changes, commits or pushes.

## 16. Slice 4 implementation checklist

- [x] Record the approved feature before code and approve only src/app/services/.
- [x] Add schema v3, secure_delete, version-gated initialization, required checks/indexes and cascades.
- [x] Implement scrypt, dummy verification, hashed cookie sessions, bounded login throttle and no-store responses.
- [x] Add role-discriminated registration, cookie login/logout/me, patient ownership and verified-doctor dependencies.
- [x] Seed database doctors with optional disabled-by-default seed accounts and polling presence.
- [x] Add broadcast creation/cancellation/expiry and guarded atomic acceptance, with private data only for the accepting doctor.
- [x] Update the Persian login, patient and doctor pages, nullable scores, visible-tab polling, owned history and account deletion.
- [x] Adapt the existing regression tests through cookie-jar registration/login and add auth/security/visit/concurrency checks.
- [x] Update configuration, PowerShell examples, demo-grade limits and breaking-change documentation.
- [x] Verify editable installation, the full suite, live routes, package data and an automated three-context browser walkthrough.

### Slice 4 verification (2026-10-25)

Commands:
- .\.venv\Scripts\python.exe -m unittest discover tests
- .\.venv\Scripts\python.exe -m pip install -e .
- APP_DOCTOR_AUTO_VERIFY=true with .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir src

Before editing: Ran 88 tests in 11.890s; OK.
Final after editing: Ran 115 tests in 67.016s; OK.
The adapted original 88 checks and 27 new auth/security/visit checks pass with
temporary databases and no real-provider network calls. The existing
Starlette/httpx deprecation warning remains.

Editable installation succeeded with the previously approved process-only proxy
bypass and no dependency changes. Package sources include all services and new
HTML pages. Uvicorn started with auto-verification enabled and a dedicated
temporary synthetic APP_DB_PATH. The default healthcare_agent.db was not created
or deleted. Live /health, /docs, /demo, /login, /doctor and /v1/specialties returned
200. Auth me/logout without a cookie returned 401 with no-store. OpenAPI has no
old patient-id routes, patient_id ChatResponse field or session-creation body.
JavaScript syntax checks and git diff --check passed.

The installed headless Chrome ran the flow in three isolated private browser
contexts: two self-registered general-practice doctors and a patient. Full
Persian intake/triage, two-doctor preview polling, simultaneous Accept actions,
one winner/one conflict, the losing queue clearing, accepting-doctor-only full
details/history/AI, and patient polling to the accepting doctor all passed.
The browser check also covered nullable score labels, a returning profile and
previous-visit Persian specialty labels, availability, logout/auth redirection
and horizontal overflow at widths 320/375/414/768. Screenshots were inspected.

The requested manual interactive private-window walkthrough could not be run:
the browser-control runtime fails to initialize because kernel.js is missing.
The browser evidence above is automated, not a claim of manual verification.
No real provider was tested; fallback was used. No commits or pushes were made.
Stop after Slice 4.

### Files changed in Slice 4

- `.env.example`
- `AGENTS.md`
- `README.md`
- `docs/changelog.md`
- `docs/plan.md`
- `src/app/agent/doctors.py`
- `src/app/agent/triage.py`
- `src/app/api/auth.py`
- `src/app/api/chat.py`
- `src/app/api/demo.py`
- `src/app/api/deps.py`
- `src/app/api/patients.py`
- `src/app/api/visits.py`
- `src/app/core/config.py`
- `src/app/core/db.py`
- `src/app/core/errors.py`
- `src/app/core/security.py`
- `src/app/data/doctors.json`
- `src/app/main.py`
- `src/app/schemas/auth.py`
- `src/app/schemas/chat.py`
- `src/app/schemas/triage.py`
- `src/app/schemas/visits.py`
- `src/app/services/__init__.py`
- `src/app/services/accounts.py`
- `src/app/services/doctors.py`
- `src/app/services/visits.py`
- `src/app/static/doctor.html`
- `src/app/static/index.html`
- `src/app/static/login.html`
- `tests/helpers.py`
- `tests/test_auth.py`
- `tests/test_chat_api.py`
- `tests/test_dictionaries.py`
- `tests/test_persistence.py`
- `tests/test_triage.py`
- `tests/test_visits.py`

## 17. Expanded Persian intake verification (2026-10-26)

- [x] Added height_cm, weight_kg, chief_complaint, medical_history, medication_history and food_allergies across intake, persistence, patient history, bounded context and accepting-doctor current/previous details.
- [x] Reused the medicine editor for multiple symptoms and updated Persian questions/labels, profile confirmation and doctor display.
- [x] Added atomic schema-v4 migration and checks for concurrent upgrades, preserved accounts/history, missing legacy profile fields and rollback/retry after a migration failure.
- [x] Kept pending-doctor previews unchanged and reused redaction for chief-complaint red flags.
- Command: .\.venv\Scripts\python.exe -m unittest discover tests. Baseline: Ran 115 tests in 82.316s; OK. Final: Ran 120 tests in 81.382s; OK. The original sandboxed Python run stalled after a Python-location warning and was stopped; these passing runs used the repository virtual environment outside the sandbox. The existing Starlette/httpx deprecation warning remains.
- Started .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir src --port 8001 using a separate temporary synthetic database and no configured provider. No existing database was opened or reset for verification.
- Browser walkthrough completed the expanded Persian intake with height/weight, separate complaint/histories/allergies and two selected symptoms/medicines. Checked custom additions, removal, deduplication, none replacing other selections, total-length rejection retaining selections, Reset cleanup and returning-profile confirmation. No browser console errors; widths 320/375/414/768 had no horizontal overflow. Screenshot inspected.
- Provider calls in the suite were mocked; no live provider was tested. Doctor projections and previous-visit fields were checked through API tests. No new folders/dependencies, commits or pushes.

## 18. Optional context and final-review verification (2026-10-26)

- [x] Add optional per-visit additional_context after allergies, including returning visits; blank/skip remains empty and old notes are not prefilled.
- [x] Persist schema-v5 notes through an atomic additive upgrade from v3/v4, preserving existing accounts/history with rollback/retry on failure.
- [x] Use an explicit provider field allowlist; a mocked full provider-request test proves both current and previous note markers/field names are absent. Only accepting-doctor detail/history opts in to full notes; queues remain unchanged.
- [x] Add optional edit_field to the existing message route, validate with the same state machine, preserve other fields, refresh matches and serialize concurrent corrections. Reject invalid/unauthorized/late edits without writing data; retain emergency redaction on corrected complaint/symptoms.
- [x] Render a Persian RTL inline grouped card with native long-text disclosure, a collapsible earlier transcript, field-specific editing/cancel, safe inline errors, pending controls and a compact confirmed summary. No modal, CDN, new dependency or folder.
- .\.venv\Scripts\python.exe -m unittest discover tests: Ran 127 tests in 69.788s; OK. The existing Starlette/httpx deprecation warning remains. The prior expanded-intake suite had 120 passing tests; seven additional checks cover optional notes, corrections, provider privacy, migration and concurrent edits.
- Restarted the review server using a new temporary synthetic database and .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir src --port 8001. Existing databases were not opened or reset for this verification.
- Browser automation verified the optional multiline box, skip, fresh note on a returning visit, grouped summary, editing/cancellation, invalid-answer recovery, symptom-match updates, inert HTML-like text, expandable long notes, confirmed-card collapse and continuing fallback triage. Checked widths 320/375/414/768: no horizontal overflow or clipped button labels; no browser console errors. Screenshot inspected and saved outside the repo.
- Reused the existing palette/type/spacing through Hallmark at component scope. Text contrast on white: primary/secondary 7.68:1, body 12.08:1, muted 5.69:1, error 7.60:1. No decorative motion added.
- git diff --check passed. Real provider calls were not made; provider payload exclusion was verified through mocks. No commit or push.

## 19. Slice 5 implementation and verification (2026-10-26)

- [x] Record the approved feature before implementation; reuse existing folders and dependencies.
- [x] Make patient request expiry a read-only projection and retain mutation/doctor sweeps.
- [x] Add atomic schema-v6 migration, end timestamps, cascading direct messages and request/id index; keep secure_delete enabled.
- [x] Add participant-scoped read/post/end contracts, stripped validation, cursor pagination, message cap, guarded ending and ended visit items.
- [x] Add Persian chat panels, polling/catch-up, read retries/backoff, retained drafts, safe rendering, multiline input and inline doctor end confirmation.
- [x] Cover migration preservation/concurrent bootstrap/rollback, authorization, pagination, validation, concurrent cap/end, read-only rows, deletion and response/log privacy with temporary-database tests.
- [x] Reinstall, run the full suite, check JavaScript syntax and live routes, and complete an automated two-account browser walkthrough.

PowerShell command: .\.venv\Scripts\python.exe -m unittest discover tests

```text
Before editing:
Ran 127 tests in 94.623s
OK

Final after editing:
Ran 139 tests in 102.893s
OK
```

The initial post-change run caught an accidentally changed legacy transcript
count assertion; its original five-message expectation was restored before the
final passing run. Twelve new tests cover Slice 5. Provider calls are mocked;
the existing Starlette/httpx deprecation warning remains.

.\.venv\Scripts\python.exe -m pip install -e . completed successfully:
Successfully built healthcare-agent; Successfully installed healthcare-agent-0.1.0.
It used the previously approved process-only proxy bypass, then restored the
previous environment. No dependency or packaging changes were required.

With APP_DOCTOR_AUTO_VERIFY=true and a dedicated temporary synthetic APP_DB_PATH,
the requested Uvicorn command reached startup but could not bind port 8000
(WinError 10048: address already in use). The existing listener was left alone.
Running the same command with --port 8002 succeeded. /health, /docs, /demo and
/doctor returned HTTP 200. Existing project databases were not opened or reset
for verification. Access logs remain disabled. The temporary port-8002 server
was stopped after verification; existing listeners were left running.

Browser automation used separate patient.localhost and doctor.localhost cookie
origins on that test server. It completed registration, the full synthetic
intake/fallback triage, broadcast and acceptance; messages arrived in both
directions within a few seconds. Enter sent, Shift+Enter retained a newline,
empty Send was disabled, repeated reads did not duplicate messages, and a draft
survived dashboard refreshes. A closed patient panel retained its old message
count, then fetched the missing doctor message immediately on reopening.
Inline end confirmation locked both inputs, retained all three messages and
showed the Persian read-only note. No browser console errors were observed.
A 375-pixel doctor view wrapped without horizontal overflow; a screenshot of
the completed chat was inspected and saved outside the repository.

Unverified browser checks: literal manual/private windows, actual tab-hidden
visibilitychange pause/resume, network-error retry/backoff timing, full-history
scroll behavior and patient mobile viewport sizing. The available browser
controls did not provide isolated private windows or reliable tab-visibility
simulation. Authorization, read-only behavior and race outcomes are covered by
API tests; this is not a claim of manual browser verification. No live provider
was called, and direct chat has no provider integration. No commit or push.

Files changed: README.md, docs/plan.md, docs/changelog.md;
src/app/main.py, core/db.py, schemas/visits.py, services/visits.py;
new api/chats.py, schemas/chats.py, services/chats.py;
static/index.html and static/doctor.html;
new tests/test_chats.py and existing tests/test_auth.py,
test_persistence.py, test_triage.py and test_visits.py.

## 20. Slice 6 implementation and verification (2026-10-26)

- [x] Record the approved contract before application changes; add only the five approved files in existing folders.
- [x] Add paired secret-safe admin settings, startup hashing/seeding, reserved usernames and required unique synthetic license numbers.
- [x] Add atomic schema-v7 users rebuild, doctor review columns/license index and review audit; restore foreign keys on success/failure and preserve references/indexes/data.
- [x] Add role boundaries, doctor status/note projection, guarded review transitions and atomic suspension/visit ending/audit writes.
- [x] Preserve seed-doctor admin decisions and serialize availability/heartbeat writes with suspension.
- [x] Add the Persian admin panel, inline notes/counters, status/audit tabs/paging, conflict refresh and visible-tab polling; update login and doctor/patient redirects.
- [x] Add temporary-database tests for config/seeding, licenses, all transition/role boundaries, audit, suspension/rollback and concurrent/failed migrations; retain all previous tests.
- [x] Update setup/API/privacy/breaking-change docs; reinstall and verify tests, JavaScript, live routes and automated browser flow.

PowerShell command: .\.venv\Scripts\python.exe -m unittest discover tests

```text
Before editing:
Ran 139 tests in 105.796s
OK

After implementation:
Ran 155 tests in 115.540s
OK
```

The original 139 tests also passed after the initial backend changes. Sixteen
new tests cover the admin slice, including v6-to-v7 row/link/index preservation,
foreign-key enforcement/check failure, rollback/retry, equivalent fresh/upgraded
schemas, concurrent bootstrap/approval and suspension rollback if audit insertion
fails. All tests use temporary databases and no provider network calls.
The installed Starlette/httpx deprecation warning remains. A first isolated admin
test run exposed resource warnings from a double-entered TestClient context;
the redundant context entry was removed before the final full suite.

.\.venv\Scripts\python.exe -m pip install -e . succeeded:
Successfully built healthcare-agent; Successfully installed healthcare-agent-0.1.0.
The previously authorized process-only proxy bypass was restored afterwards;
no global packages, dependencies or new folders were added. Inline JavaScript
syntax checks passed for index.html, doctor.html, login.html and admin.html.
git diff --check passed.

Uvicorn verification set APP_ADMIN_USERNAME=admin_demo and a synthetic 12+
character APP_ADMIN_PASSWORD, removed APP_DOCTOR_AUTO_VERIFY and used a unique
temporary APP_DB_PATH without touching existing project databases. The requested
default-port command reached startup but failed with WinError 10048 because
port 8000 was already occupied; the existing listener was left alone. The same
command with --port 8002 started successfully. /health, /docs, /login, /demo,
/doctor and /admin returned HTTP 200 with the expected content types.
The temporary port-8002 server was stopped after verification; existing
listeners were left running.

Browser automation used three separate localhost cookie origins for a synthetic
doctor, administrator and patient. It verified the required fake-license field,
pending waiting notice with no patient UI, admin login/role redirect, pending
count, approval and automatic doctor-dashboard unlock without reloading. After
an intake/fallback triage and accepted visit, the doctor sent a synthetic message.
Admin suspension required an inline note and confirmation; a two-character note
kept confirmation disabled. Suspension displayed the note on the doctor page and
removed its patient UI, while the patient saw an ended, locked chat with history
retained. The audit tab showed approval and suspension in newest-first order.
Admin visits to /demo and /doctor redirected to /admin. A 375-pixel admin view
wrapped without horizontal overflow; screenshots were inspected and the audit
proof was saved outside the repo. No browser console errors were observed.

Unverified: a literal manual/private-window walkthrough, real browser hidden-tab
timing, rejection/reinstatement through the UI, multi-page UI pagination and the
409 automatic-refresh UI path. Their API contracts are covered by tests where
applicable. Browser work was automated in isolated cookie origins, not private
windows. No real credentials, license verification or live provider were used.
No commit or push. Stop after Slice 6.

Files changed:
- .env.example, README.md, docs/plan.md and docs/changelog.md.
- src/app/main.py, core/config.py and core/db.py.
- src/app/api/admin.py (new), chats.py, demo.py and deps.py.
- src/app/schemas/admin.py (new) and auth.py.
- src/app/services/admin.py (new), accounts.py, chats.py, doctors.py and visits.py.
- src/app/static/admin.html (new), login.html, doctor.html and index.html.
- tests/test_admin.py (new), helpers.py, test_auth.py, test_chats.py,
  test_persistence.py and test_triage.py.

## 21. Slice 7a implementation and verification (2026-10-26)

- [x] Specify Slice 7a as approved in section 5 before implementation.
- [x] Add owned read-only conversation list/detail APIs, joined list query,
  stored-only patient triage, ordered/redacted transcript and latest request.
- [x] Expose existing session/lifecycle fields in visit projections; retain schema v7.
- [x] Package and explicitly serve shell.css/shell.js with no-cache; no directory mount.
- [x] Use one role-neutral RTL shell and shared cursor-chat renderer, preserving
  forest colors/fonts, desktop preference and an accessible mobile drawer.
- [x] Resume patient conversations; keep summary, intake/review, triage, visit
  state, direct messages and ending in one log with one composer.
- [x] Move doctor queue/active-ended visits and admin status/audit navigation
  into the sidebar, retaining heartbeat/review/polling and permission gates.
- [x] Preserve returning profiles, multi-item choices, review corrections,
  doctor-only optional notes, red flags, request rules and read-only ended history.
- [x] Update existing tests, README, structure and changelog. No new folders,
  dependencies, profile/password features, database schema changes or commits.

PowerShell verification from the repository root:

```text
.\.venv\Scripts\python.exe -m unittest discover tests
Before editing: Ran 155 tests in 106.225s — OK
After implementation: Ran 162 tests in 83.571s — OK

.\.venv\Scripts\python.exe -m pip install -e .
Successfully built healthcare-agent
Successfully installed healthcare-agent-0.1.0
```

Seven added tests cover list status precedence/order/limits/summary/ownership,
one-query loading, latest request and stored-specialty precedence, read-only
snapshots, configured-provider non-invocation for stored LLM/fallback results,
transcript cap/order/redaction, lifecycle timestamps and asset allowlisting.
Existing UI-delivery assertions now require the shared local assets; login
remains self-contained. Static checks reject unsafe HTML/text execution APIs.
Node syntax checks pass for shell.js and all three dashboard inline scripts;
git diff --check passes. The installed Starlette/httpx deprecation warning remains.
Editable package sources include both shared assets. The prior authorized
process-only NO_PROXY bypass was restored after installation.

Started using the README's uv --env-file command, with --port 8002 and a unique
temporary APP_DB_PATH plus synthetic admin overrides, auto-verification off and
provider configuration disabled. Existing listeners/databases and the ignored
.env were left untouched. /health, /docs, /demo, /doctor and /admin returned 200;
shell.css and shell.js returned 200 with text/css and text/javascript respectively,
both Cache-Control:no-cache. The temporary verification server was stopped.

Real-browser automation used isolated localhost cookie origins for patient,
doctor and admin tabs. At 1280px it verified new patient registration, full
intake, dropdown/review edit cancellation, automatic fallback triage, pending
doctor approval and automatic unlock, visit broadcast, queue-to-thread acceptance,
two-way messages and inline ending. Patient and doctor reloads retained their
conversation routes. At 390px a returning-profile intake resumed mid-way after
reload, then completed through request, acceptance, two-way multiline chat and
ending. Old visits reopened read-only, Back returned to the newer thread, and
confirmed New retained unfinished intakes in the sidebar. Doctor labels, matched
chips, fixed AI/emergency notices and the doctor-only note were displayed.

Desktop keyboard collapse expanded main to full width and survived reload.
Mobile defaults closed; keyboard opening, forward/backward focus wrap, Escape,
visible close control, focus return, background scroll lock and close-on-link
were checked. Admin status/audit sidebar navigation worked at desktop/mobile
widths. No horizontal overflow at 1280, 390, 320, 375, 414 and 768px. Final
desktop/mobile screenshots were saved outside the repository.

Unverified in the browser: literal separate/private windows (isolated cookie
origins were used), forced offline/ambiguous-send/backoff timing, hidden-tab
poll timing, unavailable localStorage, 500-message UI saturation, expiry/409
conflict races and multi-page admin paging. Existing/new API tests cover the
corresponding server rules where applicable. No live provider or real patient
data was used. Stop after Slice 7a; do not commit or push.

Files changed: README.md, docs/plan.md, docs/changelog.md, pyproject.toml;
agent/sessions.py, api/chat.py, api/demo.py, schemas/chat.py, schemas/visits.py,
services/visits.py under src/app; static/index.html, doctor.html, admin.html,
shell.css and shell.js; tests/test_chat_api.py, test_visits.py, test_auth.py and
test_admin.py. Only shell.css and shell.js are new files.

## 22. Slice 7b implementation and verification (2026-10-26)

- [x] Specify Slice 7b as approved in section 5 before implementation.
- [x] Add the transactional doctor heartbeat, 90-second presence window,
  read-only request GET and separate 20/10/15-second browser timers.
- [x] Add atomic schema-v8 migration/backfill, cascading patient profiles and
  doctor resubmission timestamp, including concurrent bootstrap/rollback checks.
- [x] Use saved complete profiles for new intakes, share measurement parsing,
  preserve history/context and guard completion against newer profile edits.
- [x] Add validated, role-limited patient/doctor profile APIs and every doctor
  status, active-visit, duplicate-license and auto-verification rule.
- [x] Add password verification/throttling and atomic other-session revocation;
  preserve the current cookie and reject stale-password login races.
- [x] Add Persian RTL patient/doctor profile forms, password controls, moved
  patient deletion section and the admin resubmission marker.
- [x] Preserve linked seed doctors' edited metadata through startup seeding.
- [x] Update README/changelog and leave 23 added unittest checks. No new folders
  or dependencies; no commit or push.

PowerShell verification from the repository root:

```text
.\.venv\Scripts\python.exe -m unittest discover tests
Before editing: Ran 162 tests in 91.327s
OK
After implementation: Ran 185 tests in 109.439s
OK

.\.venv\Scripts\python.exe -m pip install -e .
Successfully built healthcare-agent
Successfully installed healthcare-agent-0.1.0
```

The suite covers profile validation/ownership, immutable prior sessions/context,
stale completion/emergency protection, cascade deletion, migration backfill and
rollback/retry/equivalent structures/concurrency, read-only polling, heartbeat
atomicity and presence boundaries, doctor status/active-visit rules, managed
passwords, separate throttles, session revocation/rollback, password-log privacy,
login races, seed-edit persistence and static route/rendering constraints.
All 162 existing tests remain and pass with updated schema/presence/prefill
expectations. The installed Starlette/httpx deprecation warning remains.
Node syntax checks pass for shell.js and all three dashboard inline scripts;
git diff --check passes. The authorized process-only proxy bypass was restored
after installation. Project Python and loopback checks needed sandbox escalation.

Started with the README's uv --env-file command, --port 8002, a unique temporary
APP_DB_PATH, synthetic admin/seed credentials, auto-verification off and provider
configuration disabled. Existing databases/listeners and the ignored .env were
left untouched. /health, /docs, /demo, /doctor, /admin and both shared assets
returned HTTP 200. The temporary verification server was stopped afterwards.

Real-browser automation used isolated localhost cookie origins for a patient,
doctor, administrator and second patient login. Patient profile edits accepted
Persian/Arabic-Indic measurements and appeared in a new welcome-back before any
previous intake had completed. New intake, fallback triage, request acceptance
and ending still worked. Returning from profile restored the conversation.
Approved doctor name/expertise edits retained approval; a specialty change during
an active visit displayed the Persian conflict, while the same change after
ending produced the review banner and admin resubmission marker/date. Admin
approval returned the doctor to service. After more than four minutes working
in other tabs, the patient still saw the doctor online.

A live local-API password change returned 204, retained that client's cookie,
rejected the old password and accepted the new one. Reloading an independently
logged-in browser session displayed login after revocation. At 390px the patient
profile rejected age 121 with a Persian field hint, saved a correction and
reloaded it. Desktop 1280px/mobile 390px profiles had no horizontal overflow;
screenshots were inspected and saved outside the repository. No console errors
were observed in the final patient mobile, doctor or admin tab checks.

Unverified in the browser: actual hidden-tab timer throttling (the in-app browser
reports all tabs visible), literal private windows, and password-form submission.
The password change itself and browser-session revocation were checked through
the live local API plus browser reload; credential entry in the change form
requires user handoff under the computer-use policy. Managed-password/throttle
form messages and transient heartbeat failure handling were not exercised in
the browser; server contracts are covered by tests. No live provider or real
patient data was used.

Known shortcut: the immutable first welcome-message prefix records whether a
session was created with profile prefill. It avoids an additional schema field;
the ponytail comment requires an explicit creation flag before changing that
prefix. Password throttling remains bounded and process-local; shared storage
is the upgrade path when scaling.

Files changed:
- README.md, docs/plan.md and docs/changelog.md.
- src/app/agent/intake.py and sessions.py.
- src/app/api/auth.py, deps.py, patients.py and visits.py.
- src/app/core/db.py and security.py.
- src/app/schemas/admin.py, auth.py and patients.py.
- src/app/services/accounts.py, admin.py, doctors.py and visits.py.
- src/app/static/index.html, doctor.html, admin.html, shell.css and shell.js.
- tests/test_profiles.py (new), test_admin.py, test_auth.py, test_chats.py,
  test_persistence.py, test_triage.py and test_visits.py.

Stop after Slice 7b. Do not commit or push.

## 23. Independent doctor–Codex assistant implementation and verification (2026-10-26)

- [x] Add the approved section-5 feature before implementation.
- [x] Add the verified-doctor assistant endpoint, strict transcript models and
  bounded SSE answer/error/done contract, preserving existing ErrorResponse.
- [x] Add one independent prompt and isolated ephemeral Codex bridge with
  dedicated operator home/model settings, no record reads or thread resumption.
- [x] Check installed protocol capabilities, strict disabled-tool configuration,
  empty environments/capability/workspace roots and empty instruction sources.
- [x] Bound per-process concurrency/output/deadline and interrupt/reap on failure,
  Stop and disconnect; leave ponytail comments for deployment ceilings.
- [x] Add the Persian RTL assistant route, streamed bubbles, keyboard controls,
  Stop/New Chat, memory-only completed history and marked/excluded partial turns.
- [x] Preserve triage, heartbeat and schema v8; add no dependencies or repository
  folders. Do not commit or push.

PowerShell from the repository root:

```text
.\.venv\Scripts\python.exe -m unittest discover tests
Before editing: Ran 185 tests in 125.562s
OK
Final: Ran 202 tests in 108.057s
OK
```

Seventeen new tests cover roles, transcript bounds/order/extras, no record writes,
explicit-only context, one prompt, isolation flags/metadata, old-runtime refusal,
safe SSE success/failure, notifications preceding RPC replies, exclusion of
reasoning/commentary, malformed/oversized output, timeout, cancellation/interrupt,
terminate/kill/reap, concurrency slots, environment filtering and log privacy.
All previous tests remain. Node syntax checks passed for shell.js and all three
dashboard inline scripts; git diff --check passed. The existing Starlette/httpx
deprecation warning remains. Project Python/loopback checks used sandbox escalation.

Installed Codex 0.164.0-alpha.11.1 was checked using a temporary credential-free
home, generated protocol schema and stdio initialize/thread-start calls. This
caught and corrected the installed sandbox enum to read-only. Thread creation
reported ephemeral=true, zero instruction sources and zero workspace roots.
The probe intentionally stubbed the login check and stopped before turn/start:
it sent no inference input and is not a live model-answer test. Codex creates
its own bundled skills/.system directory; this is allowed while custom skills
are rejected and skill discovery/capability/environment access are disabled.

Browser automation used the real dashboard/API with an explicitly synthetic
test-only stream replacing Codex methods in a temporary server process. Its
answer was visibly labeled as a UI test, not Codex output. It verified Send and
Enter, Shift+Enter multiline drafts, streaming controls, follow-up payload counts,
profile/queue navigation preserving completed history, Stop and navigation
cancellation, marked partial replies omitted from the next request, New Chat
during generation, reload clearing and a Persian unavailable-runtime message.
No automatic resends occurred. Desktop 1280px and mobile 390px views had no
horizontal overflow; screenshots were inspected/saved outside the repository.
No browser console errors were observed in final tab checks. Heartbeat timestamps
continued updating after registration during the browser walkthrough.

The synthetic server was stopped and the unmocked app was started using the
normal Uvicorn command with --port 8002 and a disposable temporary database.
/health, /docs, /doctor, /demo, /admin and both shared assets returned 200.
With APP_CODEX_HOME unset, the actual assistant returned 503 assistant_unavailable
without affecting the dashboard. Schema remained 8. Temporary servers/tabs were
stopped/closed, the viewport reset and existing listeners/databases/.env left alone.

Unverified: live Codex inference/clinical answer quality, because no dedicated
operator login was configured; true hidden-tab throttling, real mobile keyboard
behavior and a browser wait through the full 120-second timeout. Protocol/API
tests cover deadlines and failures; the browser stream was synthetic. No real
patient information or production credentials were used. The operator must
complete the dedicated Codex login described in README before real inference.

Files changed: .env.example, README.md, docs/plan.md, docs/changelog.md;
src/app/core/config.py, main.py, static/doctor.html and static/shell.css;
new src/app/agent/doctor_assistant.py, api/assistant.py, schemas/assistant.py
and tests/test_assistant.py. No commit or push.

## 24. Codex user-message lifecycle correction (2026-10-26)

The first real authenticated connectivity test exposed a bridge bug: Codex emits
item/started and item/completed for its normal userMessage before answering.
The bridge treated that legitimate input lifecycle as tool execution and ended
the SSE stream with assistant_unavailable. Ignore those lifecycle events without
forwarding their content; continue rejecting tool items and approval requests.
Add a regression test covering both input events followed by a successful answer.

Before editing, all 17 assistant tests passed, demonstrating the missing real
protocol case. After the correction, a synthetic live request emitted only final
assistant answer deltas and ended with turn status completed and SSE done.
Only event types, phases and safe outcome categories were inspected; neither the
user's medical text nor credentials were printed/copied into diagnostics.
Historical section-23 live-inference limitations describe that earlier run;
this later connectivity check confirms transport only, not clinical quality.

Verification: .\.venv\Scripts\python.exe -m unittest discover tests -p
test_assistant.py passed 18 tests in 2.110s. The full command
.\.venv\Scripts\python.exe -m unittest discover tests passed 203 tests in
137.521s. git diff --check passed; no folders/dependencies/schema changes.

The running port-8000 server has no --reload flag. Leave its operator-provided
environment and process intact; restart it from the same configured PowerShell
window to load the correction. Changes: agent/doctor_assistant.py,
tests/test_assistant.py, README.md, docs/plan.md and docs/changelog.md. No commit
or push.
