# Healthcare Agent: Implementation Plan and Specification

Status: package skeleton specification. The project structure is approved; agent behavior
still needs to be defined. Open decisions below are not implementation requirements.

## 1. Purpose

Build a FastAPI backend for a healthcare agent. Implement one agreed workflow
at a time, with an explicit API contract and a runnable check for its behavior.

## 2. Current baseline

- Python 3.14 or later; dependencies are FastAPI and Uvicorn.
- `src/app/main.py` creates the FastAPI application, includes the health router, and configures error handlers and logging.
- `GET /health` returns HTTP 200 with JSON `{"status": "ok"}`.
- The health endpoint checks application responsiveness only.
- FastAPI exposes interactive API documentation at `/docs`.
- No agent, model provider, database, authentication, or external service is implemented.
- `src/app/config.py` defines frozen settings read from `os.environ`. `APP_LOG_LEVEL` defaults to `INFO`; INFO, WARNING, ERROR, and CRITICAL are accepted (case insensitive). Invalid values fail startup. The application does not load `.env` files.

## 3. Project boundaries

- Put application code in `src/`, runnable checks in `tests/`, and specifications
  and project documentation in `docs/`.
- Do not create additional folders without the user's permission.
- The user approved `src/app/`, `src/app/api/`, and `src/app/schemas/` for this phase.
- `models/`, `services/`, and `agent/` are proposed only for when needed; creating them requires permission.
- Reuse existing code, standard library features, and installed dependencies first.
- Add no speculative abstractions, integrations, or infrastructure.
- Keep this plan consistent with implemented behavior; label proposed behavior clearly.

## 4. Decisions needed before agent implementation

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
- [ ] Define the first workflow and resolve its relevant open decisions.
- [ ] Write and approve its feature specification and acceptance examples.
- [ ] Implement the smallest complete workflow in `src/`.
- [ ] Add and run its runnable check in `tests/`.
- [ ] Update setup and usage documentation for the implemented behavior.

## 8. Definition of done for a feature

The agreed acceptance examples work, the relevant runnable check passes, errors
follow the documented contract, and configuration and usage instructions are
current. Report any unverified behavior or remaining limitations explicitly.

## 9. Package structure and verification

- `src/app/__init__.py`, `src/app/api/__init__.py`, and `src/app/schemas/__init__.py`: package markers.
- `src/app/main.py`: application, logging configuration, and exception handlers.
- `src/app/config.py`: frozen environment settings.
- `src/app/api/health.py`: the only application endpoint, `GET /health`.
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
