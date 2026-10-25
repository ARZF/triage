# Healthcare Agent

Minimal FastAPI starter. Agent functionality and external integrations are not implemented yet.

## Setup

Requires Python 3.11 or later. Run from the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m uvicorn main:app --app-dir src --reload
```

Open the interactive API documentation at <http://127.0.0.1:8000/docs>.
The health endpoint is <http://127.0.0.1:8000/health>.

## Structure

- `src/`: application code; `main.py` creates the FastAPI app.
- `tests/`: automated tests as functionality is added.
- `docs/`: project documentation.

## Configuration

`.env.example` reserves space for future integration settings. The starter does
not require configuration or load `.env` files. When integrations are added,
document their settings here and implement configuration loading as needed.
Keep real credentials out of source control.

## Quick check

With the server running, execute this in another PowerShell terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected response: `status` is `ok`. This endpoint confirms the application is
responding; it does not check external services.
