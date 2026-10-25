# Healthcare Agent

FastAPI project skeleton. Agent functionality and external integrations are not implemented.

## Setup

Requires Python 3.14 or later. Run from the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir src
```

Open interactive API documentation at <http://127.0.0.1:8000/docs>.
The health endpoint is <http://127.0.0.1:8000/health>.

## Structure

- `src/app/main.py`: application, exception handlers, and logging setup.
- `src/app/config.py`: frozen settings read from environment variables.
- `src/app/api/health.py`: health router.
- `src/app/schemas/common.py`: health and error response models.
- `tests/test_health.py`: health and settings checks.
- `tests/test_errors.py`: HTTP and validation error checks.
- `docs/plan.md`: specification, project boundaries, and implementation checklist.
- `docs/changelog.md`: notable project changes.

## Configuration

Defaults work without environment variables. `APP_LOG_LEVEL` defaults to `INFO`;
accepted values are `INFO`, `WARNING`, `ERROR`, and `CRITICAL`
(case insensitive). Invalid values fail startup. For example, before starting:

```powershell
$env:APP_LOG_LEVEL = "WARNING"
```

Settings are read at application import. The application does not load `.env`
files; `.env.example` documents the supported variable. Keep credentials out of
source control. Application logging does not include request bodies or headers.

## Tests

After installing the dev dependencies, run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover tests
```

Validation and HTTP exception tests define temporary routes on isolated test
applications. These routes are not part of the production API.

## API behavior

`GET /health` returns HTTP 200 with `{"status": "ok"}`. It confirms application
responsiveness only; it does not check external services.

HTTP errors return `{"error": {"code": "http_404", "message": "Not Found"}}`
for a missing path, using the corresponding status code and standard status
message for other HTTP errors. Validation failures return HTTP 422 with
`{"error": {"code": "validation_error", "message": "Request validation failed"}}`.
Neither handler echoes input or exception details.

With the server running, verify health and documentation in another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
(Invoke-WebRequest http://127.0.0.1:8000/docs).StatusCode
```