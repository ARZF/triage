# Healthcare Agent: Implementation Plan and Specification

Status: Slices 1a, 2a, 2b, 3, and 4 approved. Scripted intake, Persian demo, JSON vocabulary matching, and SQLite patient memory, and optional AI specialty triage are in scope; future workflow decisions remain proposals.

## 1. Purpose

Build a FastAPI backend for a healthcare agent. Implement one agreed workflow
at a time, with an explicit API contract and a runnable check for its behavior.

## 2. Current baseline

- Python 3.14 or later; dependencies are FastAPI, Uvicorn, and httpx.
- `src/app/main.py` creates the FastAPI application, owns its lifespan, includes routers, and calls the core logging and exception-handler registration functions.
- `GET /health` returns HTTP 200 with JSON `{"status": "ok"}`.
- The health endpoint checks application responsiveness only.
- FastAPI exposes interactive API documentation at `/docs`.
- The app implements scripted intake, JSON vocabulary, SQLite patient memory, optional AI specialty triage, demo patient/doctor accounts and broadcast visit requests; no patient-facing diagnosis, direct chat, prescription or appointment scheduling.
- The expanded Persian intake includes height/weight, main complaint, disease/medication histories and food/drug allergies, with multi-item symptom and medicine editors. Schema v4 adds nullable columns without resetting version-3 data.
- Schema v5 adds optional doctor-only context, explicitly excluded from current/prior provider inputs. Final review is an inline Persian card with validated field-specific corrections before confirmation.
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
- `src/app/api/health.py`: health endpoint. `chat.py` adds the two /v1/chat POST routes; `demo.py` serves /demo.
- `src/app/schemas/common.py`: `HealthResponse`, `ErrorResponse`, and its nested error model.
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
