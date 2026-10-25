# Healthcare Agent

Slices 1a and 2a provide scripted intake and vocabulary matching using synthetic data only. No LLM,
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
- `POST /v1/chat/sessions`: 201 with a new session and welcome message.
- `POST /v1/chat/sessions/{session_id}/messages`: accepts `{"message": "30"}`
  (1-2000 characters) and returns 200 with the updated session.
- `GET /v1/dictionaries/{kind}?q=&limit=`: read-only symptom or medicine vocabulary.
  `kind` is `symptoms` or `medicines`; optional `q` is at most 100 characters;
  `limit` is 1-100, default 50. Invalid values return 422 in the shared error shape.
  The response is `{kind, entries: [{code, name_fa, name_en, aliases}]}`.
- `GET /demo`: packaged self-contained HTML; inline CSS/JS, no CDN or build step.
- `GET /docs`: interactive API documentation.

Both chat POST routes return `{session_id, reply, step, done, emergency, collected, matched}`.
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

Unknown/evicted sessions return 404; invalid bodies return 422. All HTTP and
validation errors use `{"error": {"code": "...", "message": "..."}}`.
HTTP errors use code `http_<status>` and the standard status message.
Validation uses `validation_error` and `Request validation failed`.
Handlers do not echo input or exception details.

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
- `src/app/main.py`: app, exception handlers, logging, and router wiring.
- `src/app/config.py`: frozen environment settings.
- `src/app/api/health.py`, `chat.py`, `demo.py`, `dictionaries.py`: HTTP routes.
- `src/app/schemas/common.py`, `chat.py`, `dictionaries.py`: request/response models.
- `src/app/agent/intake.py`: pure immutable scripted state machine.
- `src/app/agent/sessions.py`: bounded in-memory session dict.
- `src/app/agent/dictionaries.py`: validated loading, normalization, matching, and search.
- `src/app/data/symptoms.json`, `medicines.json`: starter vocabulary sources.
- `src/app/static/index.html`: responsive demo page.
- `tests/test_health.py`, `test_errors.py`: health, settings, and error checks.
- `tests/test_intake.py`, `test_chat_api.py`: intake, chat, and demo checks.
- `tests/test_dictionaries.py`: dictionary validation, caching, matching, and API checks.
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
