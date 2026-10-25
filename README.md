# Healthcare Agent

Slices 1a, 2a, 2b, and 3 provide scripted intake, vocabulary matching, SQLite
patient memory, and optional AI specialty triage using synthetic data only.
No authentication, patient-facing diagnosis, booking, or treatment advice is implemented.

## Setup

Requires Python 3.14 or later. From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir src
```

Open [the demo](http://127.0.0.1:8000/demo) or
[API documentation](http://127.0.0.1:8000/docs). SQLite stores visits across page reloads and server restarts.

## Demo walkthrough (Persian)

Use made-up answers only, without names or other identifiers. The steps are
age, symptoms, duration, severity, medications, allergies, then confirmation.
The demo, scripted questions, hints, and final messages are in Persian with right-to-left layout.
Try `۳۰`, `سرفه خفیف`, `دو روز`, `۳`, `هیچ`, `ندارد`, `بله`, in order.

«ارسال» or Enter submits a message. Collected fields update live. Invalid answers
re-ask the current question with a hint. At confirmation, `خیر` or `نه` clears collected
data and returns to age; `بله` completes intake and disables input. English yes/no remain accepted.
«شروع دوباره» (Reset) creates a new session. If a request fails, an error line appears; use
Reset to recover without blindly retrying a message whose outcome may be unknown.

Before saving symptoms, a fixed phrase list in Persian and English can stop the
intake with a message to contact local emergency services. That answer is not
stored; earlier answers remain. The starter list needs clinical review and is
not a clinical assessment. Valid later messages leave completed state unchanged.

Dropdowns offer the 12 starter symptoms from the JSON dictionary, exact ages
(0-120), severity scores (1-10), common durations,
no-medication/no-allergy answers, and confirmation. Choosing an answer fills the
reply box; press Send to submit it. Custom text remains available for every
step, including symptoms and details not represented by the choices.
The symptom options load from `/v1/dictionaries/symptoms?limit=100` when a
session starts or Reset is used. Choose a symptom, review the filled reply,
then press Send; type additional details or multiple symptoms as needed.
Medicine choices also load from `/v1/dictionaries/medicines?limit=100`.
At the medicine step, selecting a generic name adds it to an editable list.
Add more names from the dropdown, or type a custom name and press Add or Enter.
Remove an item with its Delete button, then press Submit list when ready.
Repeated names are not added twice. Selecting none clears other entries;
adding a medicine replaces none. Any pending typed name is included on submit or before selecting another medicine; choosing custom entry preserves unfinished text.
The combined answer stays within the existing 2000-character message limit.
The API still receives one comma-separated text answer, and recognized names
appear separately in the side panel. These choices record synthetic input;
they do not recommend taking any medicine.
The list remains starter vocabulary that has not been clinically reviewed.

## API

- `GET /health`: 200 with `{"status": "ok"}`; responsiveness only.
- `POST /v1/chat/sessions`: 201 with a new session and welcome message; optional
  body `{patient_id: str|null}` (maximum 64 characters), unknown id returns 404.
- `POST /v1/chat/sessions/{session_id}/messages`: accepts `{"message": "30"}`
  (1-2000 characters) and returns 200 with the updated session.
- `GET /v1/dictionaries/{kind}?q=&limit=`: read-only symptom or medicine vocabulary.
  `kind` is `symptoms` or `medicines`; optional `q` is at most 100 characters;
  `limit` is 1-100, default 50. Invalid values return 422 in the shared error shape.
  The response is `{kind, entries: [{code, name_fa, name_en, aliases}]}`.
- `GET /demo`: packaged self-contained HTML; inline CSS/JS, no CDN or build step.
- `GET /docs`: interactive API documentation.

Both chat POST routes return `{session_id, patient_id, returning, reply, step, done, emergency, collected, matched}`.
`matched` contains `symptoms` and `medicines` lists, each containing only
`{code, name_fa}` entries. Matches are computed from the accepted symptom and
medication answers for every response; the intake state machine is unchanged.
The demo shows these names as plain chips in the side panel. Unmatched answers
produce no extra chips or message.
Session IDs are uuid4 hex. Collected fields `age`, `symptoms`, `duration`,
`severity`, `medications`, and `allergies` start null. Age and severity become
integers; other values become trimmed strings. Age accepts 0-120; severity 1-10.
Text must be non-empty; `no` and `none` are valid medication/allergy answers.
Persian and Arabic-Indic digits are accepted alongside ASCII digits. Confirmation accepts بله/خیر/نه and English yes/no. Normal completion keeps
`step=confirm`; a red-flag stop keeps `step=symptoms`.

Unknown sessions or patients return 404; invalid bodies return 422. All HTTP and
validation errors use `{"error": {"code": "...", "message": "..."}}`.
HTTP errors use code `http_<status>` and the standard status message.
Validation uses `validation_error` and `Request validation failed`.
Handlers do not echo input or exception details.


## Returning patients and stored history

Session creation optionally accepts `{"patient_id": "existing-id"}`; no body
still creates a patient. Responses include `patient_id` and `returning`.
The demo keeps only this opaque id in localStorage, guarded with try/catch.
If storage is unavailable, the current page still works using memory. Reset
starts another session for the same patient. An unknown stored id is cleared
after a 404 and session creation retries without it.

A previous completed, non-emergency visit qualifies a patient for the
`profile` step. The Persian welcome-back shows their previous age in Persian
digits, medications, and allergies. Confirming with yes skips directly through
symptoms, duration, severity, and final confirmation. Rejecting the profile
clears the prefill and starts a full intake at age. Emergency and unfinished
visits do not qualify. The internal `returning_profile` field is never exposed.

`GET /v1/patients/{patient_id}/history?limit=10` returns a newest-first list of
visits; limit is 1-50. Each visit contains session_id, created_at, done,
emergency, collected, matched, and messages (role, content, created_at).
The demo's collapsible history excludes its current session and shows prior
dates, symptoms, and vocabulary chips. History uses stored dictionary codes;
removed codes remain visible using the code as the name. Live chat matching
continues to use current dictionaries.

`DELETE /v1/patients/{patient_id}` returns 204 and removes the patient and all
associated sessions and messages; unknown ids return 404. The demo's Persian
forget-me button calls this endpoint, clears its local id, and starts fresh.
This handle is not authentication.

SQLite saves an initial bot message and each later user/bot pair. A symptom
answer that triggers the fixed red-flag stop is replaced in the message log
by a fixed Persian placeholder; the triggering text is not stored in collected
data or code arrays. Further messages to completed sessions change nothing.


## AI specialty triage (Slice 3)

After a non-emergency intake completes, the demo automatically calls
`POST /v1/chat/sessions/{session_id}/triage`. It shows a loading line, then
the specialty, urgency, optional reason, a fixed notice that this is a
suggestion rather than a medical diagnosis, and matching fictional doctors.
Cards show expertise, online status and scores in Persian digits. Request
failures offer Retry. Reset and forget-me clear the displayed suggestion.
There is no booking, doctor account, authentication or treatment advice.

The response is `{session_id, source, specialty: {code, name_fa}, urgency,
emergency, reason, notice, doctors: [{id, name_fa, expertise, score, online}]}`.
An unknown session returns 404; unfinished and emergency-stop intakes return
409 in ErrorResponse format. Provider urgency emergency returns no doctors
and uses the existing emergency notice. Doctors sort online first, then by
descending score, with at most ten results.

Without a configured provider, or if it times out or returns an invalid
result, a general-practice fallback is stored with source=fallback,
urgency=unknown and no reason. A stored result is reused on every later call
for that session, including fallback results; Retry recovers an HTTP failure
rather than rerunning an already stored result. A new intake can create a
new result.

The provider receives only the current structured intake and up to three
previous completed non-emergency visits, with dates, matched vocabulary names
and any previous triage specialty. Free text is capped at 500 characters.
Patient/session identifiers and transcripts are excluded. The database
connection closes before the synchronous provider call; a later transaction
stores the first result. Concurrent first requests may duplicate provider
work, but only one result is stored.

**Synthetic data only.** The provider receives structured health data.
A data-processing agreement, a lawful basis and a data-location decision are
required before real data, alongside authentication, encryption, consent,
retention rules and audit. AI considerations are unverified and doctor-only.
The stored doctor summary and considerations are never returned by the
patient endpoint. Only outcome categories are logged.

`src/app/data/doctors.json` contains 12 obviously fictional doctors and nine
specialties, labeled `synthetic demo data, not real doctors`. Edit the file
locally and restart the server; validation runs at startup. IDs/codes are
unique lowercase slugs, specialties must be known, scores are 0-5, and at
least one general-practice doctor is required.

Optional settings, read from the process environment without loading .env:

- `APP_LLM_BASE_URL`: HTTP/HTTPS base URL, including any /v1 prefix. Do not
  put credentials, query strings or fragments in it.
- `APP_LLM_MODEL`: model identifier. URL and model together enable calls.
- `APP_LLM_API_KEY`: optional bearer key, excluded from Settings repr.
- `APP_LLM_TIMEOUT_SECONDS`: finite float from 1 to 120; default 30.

Invalid LLM settings raise ValueError naming only the variable. For a
synthetic local provider, set its actual model identifier before startup:

```powershell
$env:APP_LLM_BASE_URL = "http://127.0.0.1:8080/v1"
$env:APP_LLM_MODEL = "your-model-id"
$env:APP_LLM_API_KEY = "" # Set only if your provider requires a key.
$env:APP_LLM_TIMEOUT_SECONDS = "30"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir src
```

Leave URL and model unset to test fallback. Never commit a real key.

## Vocabulary dictionaries

`src/app/data/symptoms.json` and `medicines.json` each contain 12 generic
vocabulary entries and the status `starter list, not clinically reviewed`.
**These lists are not clinically reviewed.** Matching recognizes words only;
it does not establish a diagnosis or make treatment recommendations.

To edit vocabulary, update the JSON files directly, keeping the existing shape:
`{status, entries: [{code, name_fa, name_en, aliases}]}`. Codes must be unique
within each file and match `^[a-z0-9_]+$`. Names must be non-empty strings;
aliases must be a list of non-empty strings. Use only spelling/transliteration
and wording variants. Do not add brands, doses, indications, side effects,
interactions, external codes, or broad clinical categories.

The files load and validate once at startup. **Restart the server after editing**;
invalid files stop startup with an error naming the file and code, without
dumping the document. There is no write endpoint.

Both sides are normalized identically: casefold, Arabic letter variants,
half-spaces, Persian/Arabic-Indic digits, punctuation, and whitespace. Chat
matching uses whole words/phrases, returns each code once, and orders results
by first appearance. Dictionary search uses normalized substrings and returns
entries in file order. Persian names are always implicit aliases.

Try synthetic symptoms `سرفه و تب خفیف` and medications `هیچ`: the side panel
shows cough and fever chips and no medicine chips. For a medicine vocabulary
example, enter the generic name `استامینوفن` instead; it is vocabulary only.

## Structure

- `AGENTS.md`: docs-first workflow, project boundaries, semantic commits.
- `src/app/main.py`: app creation, lifespan, and router wiring.
- `src/app/core/config.py`: frozen environment settings.
- `src/app/core/db.py`: SQLite schema, per-operation connections, and UTC timestamps.
- `src/app/core/errors.py`: shared exception handlers and registration.
- `src/app/core/llm.py`: synchronous OpenAI-compatible provider client.
- `src/app/core/logging_config.py`: logging setup and access-log disabling.
- `src/app/api/health.py`, `chat.py`, `demo.py`, `dictionaries.py`, `patients.py`: HTTP routes.
- `src/app/schemas/common.py`, `chat.py`, `dictionaries.py`, `patients.py`: request/response models.
- `src/app/agent/intake.py`: pure immutable scripted state machine.
- `src/app/agent/context.py`, `triage.py`, `doctors.py`: bounded context, stored specialty triage, and validated fictional doctors.
- `src/app/schemas/triage.py`: provider-output and patient-response contracts.
- `src/app/data/doctors.json`: fictional demo doctor directory.
- `tests/test_llm.py`, `test_triage.py`: network-free provider, context, doctor and triage checks.
- `src/app/agent/sessions.py`: transactional session storage, history, and deletion.
- `src/app/agent/dictionaries.py`: validated loading, normalization, matching, and search.
- `src/app/data/symptoms.json`, `medicines.json`: starter vocabulary sources.
- `src/app/static/index.html`: responsive demo page.
- `tests/test_health.py`, `test_errors.py`: health, settings, and error checks.
- `tests/test_intake.py`, `test_chat_api.py`: intake, chat, and demo checks.
- `tests/test_dictionaries.py`: dictionary validation, caching, matching, and API checks.
- `tests/test_persistence.py`: temporary-database persistence, profile, history, cascade, and transaction checks.
- `docs/plan.md`: approved specifications and implementation checklist.
- `docs/changelog.md`: notable changes.

## Configuration and session lifetime

`APP_LOG_LEVEL` defaults to `INFO`; allowed values are INFO, WARNING, ERROR,
and CRITICAL (case insensitive). Invalid values fail startup. Set it in the
process environment, for example `$env:APP_LOG_LEVEL = "WARNING"`.
Logging settings are read at import; `.env` files are not loaded. See `.env.example`.
Keep credentials out of source control. Message contents, collected data,
and request bodies/headers are not logged.

`APP_DB_PATH` defaults to `healthcare_agent.db` and must be non-empty. It is read
from the process environment every time a connection opens; `.env` is not loaded.
For example: `$env:APP_DB_PATH = "synthetic-demo.db"`.
Schema creation is idempotent on every connection and app startup, with foreign
keys enabled and schema version 2 (including cascading triage results). Connections close after each operation;
message handling uses a single `BEGIN IMMEDIATE` transaction. Chat endpoints
are synchronous so SQLite runs in FastAPI's threadpool.

There is no session cap or automatic expiry. Storage is SQLite; retention is
none (manual deletion only). Reset preserves prior visits. The database and its
journal/WAL/shared-memory files are ignored by Git. Keep backups and paths under
your control; no backup or migration system is implemented.

**Synthetic data only. Authentication, encryption at rest, consent, retention
rules, and audit are NOT implemented and are required before real patient data.**
Uvicorn access logging is disabled because patient ids appear in endpoint paths.
The application does not log ids, request contents, or collected data.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover tests
```

Tests use synthetic data and temporary database files only; they never use the
default database file. Temporary error-test routes are isolated from the
production API. The installed Starlette version emits an httpx deprecation
warning; the requested dependency is retained.

With the server running, open /demo and complete the walkthrough above. Also:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
(Invoke-WebRequest http://127.0.0.1:8000/docs).StatusCode
(Invoke-WebRequest http://127.0.0.1:8000/demo).StatusCode
```
