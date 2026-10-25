# Healthcare Agent: Implementation Plan and Specification

Status: Slice 1a approved. Scripted intake and demo are in scope; future workflow decisions remain proposals.

## 1. Purpose

Build a FastAPI backend for a healthcare agent. Implement one agreed workflow
at a time, with an explicit API contract and a runnable check for its behavior.

## 2. Current baseline

- Python 3.14 or later; dependencies are FastAPI and Uvicorn.
- `src/app/main.py` creates the FastAPI application, includes the health router, and configures error handlers and logging.
- `GET /health` returns HTTP 200 with JSON `{"status": "ok"}`.
- The health endpoint checks application responsiveness only.
- FastAPI exposes interactive API documentation at `/docs`.
- Slice 1a implements scripted intake and demo chat, without an LLM, model provider, database, authentication, diagnosis, or treatment advice.
- `src/app/config.py` defines frozen settings read from `os.environ`. `APP_LOG_LEVEL` defaults to `INFO`; INFO, WARNING, ERROR, and CRITICAL are accepted (case insensitive). Invalid values fail startup. The application does not load `.env` files.

## 3. Project boundaries

- Put application code in `src/`, runnable checks in `tests/`, and specifications
  and project documentation in `docs/`.
- Do not create additional folders without the user's permission.
- The user approved `src/app/`, `src/app/api/`, `src/app/schemas/`, `src/app/agent/`, and `src/app/static/`.
- `models/` and `services/` are proposed only for when needed; creating them requires permission.
- Reuse existing code, standard library features, and installed dependencies first.
- Add no speculative abstractions, integrations, or infrastructure.
- Keep this plan consistent with implemented behavior; label proposed behavior clearly.

## 4. Decisions for future slices beyond the approved scripted demo

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
- **Scope:** native labeled select above the existing reply box, with Persian choices and RTL layout. Ages 0-120, severity 1-10, common duration choices, no-medication/no-allergy responses, and yes/no confirmation. Symptoms remain free text; every step permits custom text.
- **API contract:** submit the selected value through the existing message endpoint; no API or state-machine changes.
- **Validation:** retain server validation. No selection is prefilled or automatically submitted; choose, review, then Send. Numeric option labels and values use Persian digits.
- **Agent behavior:** keep the same step order, red-flag stop, reset, and terminal behavior.
- **Failure behavior:** disable dropdown and input together while pending, failed, or complete. Disable the dropdown for symptoms, with a visible instruction to type the description.
- **Access and data handling:** same synthetic-only session behavior; no new collection fields.
- **Configuration:** no new folders or dependencies.
- **Acceptance examples:** select age 30, type synthetic symptoms, select a duration, severity 3, no medications, no allergies, and yes to complete; a custom choice clears the input for typing; no at confirm restarts at age.
- **Runnable check:** existing unittest suite, including a full API intake using the exact dropdown answer values.

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
- `src/app/main.py`: application, logging configuration, and exception handlers.
- `src/app/config.py`: frozen environment settings.
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
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
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
