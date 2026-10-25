# Healthcare Agent

Slice 1a is a scripted patient-intake chat using synthetic data only. No LLM,
database, authentication, diagnosis, or treatment advice is implemented.

## Setup

Requires Python 3.14 or later. From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir src
```

Open [the demo](http://127.0.0.1:8000/demo) or
[API documentation](http://127.0.0.1:8000/docs). Use one server process;
in-memory sessions are not shared across workers.

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

Dropdowns offer exact ages (0-120), severity scores (1-10), common durations,
no-medication/no-allergy answers, and confirmation. Choosing an answer fills the
reply box; press Send to submit it. Custom text remains available for every
step, including symptoms and details not represented by the choices.

## API

- `GET /health`: 200 with `{"status": "ok"}`; responsiveness only.
- `POST /v1/chat/sessions`: 201 with a new session and welcome message.
- `POST /v1/chat/sessions/{session_id}/messages`: accepts `{"message": "30"}`
  (1-2000 characters) and returns 200 with the updated session.
- `GET /demo`: packaged self-contained HTML; inline CSS/JS, no CDN or build step.
- `GET /docs`: interactive API documentation.

Both chat POST routes return `{session_id, reply, step, done, emergency, collected}`.
Session IDs are uuid4 hex. Collected fields `age`, `symptoms`, `duration`,
`severity`, `medications`, and `allergies` start null. Age and severity become
integers; other values become trimmed strings. Age accepts 0-120; severity 1-10.
Text must be non-empty; `no` and `none` are valid medication/allergy answers.
Persian and Arabic-Indic digits are accepted alongside ASCII digits. Confirmation accepts بله/خیر/نه and English yes/no. Normal completion keeps
`step=confirm`; a red-flag stop keeps `step=symptoms`.

Unknown/evicted sessions return 404; invalid bodies return 422. All HTTP and
validation errors use `{"error": {"code": "...", "message": "..."}}`.
HTTP errors use code `http_<status>` and the standard status message.
Validation uses `validation_error` and `Request validation failed`.
Handlers do not echo input or exception details.

## Structure

- `AGENTS.md`: docs-first workflow, project boundaries, semantic commits.
- `src/app/main.py`: app, exception handlers, logging, and router wiring.
- `src/app/config.py`: frozen environment settings.
- `src/app/api/health.py`, `chat.py`, `demo.py`: HTTP routes.
- `src/app/schemas/common.py`, `chat.py`: request/response models.
- `src/app/agent/intake.py`: pure immutable scripted state machine.
- `src/app/agent/sessions.py`: bounded in-memory session dict.
- `src/app/static/index.html`: responsive demo page.
- `tests/test_health.py`, `test_errors.py`: health, settings, and error checks.
- `tests/test_intake.py`, `test_chat_api.py`: intake, chat, and demo checks.
- `docs/plan.md`: approved specifications and implementation checklist.
- `docs/changelog.md`: notable changes.

## Configuration and session lifetime

`APP_LOG_LEVEL` defaults to `INFO`; allowed values are INFO, WARNING, ERROR,
and CRITICAL (case insensitive). Invalid values fail startup. Set it in the
process environment, for example `$env:APP_LOG_LEVEL = "WARNING"`.
Settings are read at import; `.env` files are not loaded. See `.env.example`.
Keep credentials out of source control. Message contents, collected data,
and request bodies/headers are not logged.

The store holds at most 1000 sessions and evicts the oldest created session.
Reset creates a new session without deleting the previous one. State is lost
on restart. Database persistence belongs to the future EHR slice.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover tests
```

Tests use synthetic data; temporary error-test routes are isolated from the
production API. The installed Starlette version emits an httpx deprecation
warning; the requested dependency is retained.

With the server running, open /demo and complete the walkthrough above. Also:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
(Invoke-WebRequest http://127.0.0.1:8000/docs).StatusCode
(Invoke-WebRequest http://127.0.0.1:8000/demo).StatusCode
```
