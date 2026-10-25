# Healthcare Agent Project Rules

These rules apply to the entire repository.

## Read before editing

- Before editing any file, read `README.md`, `docs/plan.md`, and `docs/changelog.md`.
- Read any additional documentation referenced for the current task, then inspect the affected code and its callers before choosing a change.
- Follow `docs/plan.md`, especially sections 3 and 6. Separate approved requirements from proposals; do not invent endpoints, schema fields, integrations, or clinical behavior.
- Ask for clarification when missing product requirements would change the implementation; use judgment for routine implementation details within approved scope.
- Keep the plan and README consistent with implemented behavior. Record notable changes under Unreleased in `docs/changelog.md`.

## Scope and implementation

- Application code belongs in `src/app/`, checks in `tests/`, and documentation in `docs/`.
- Only `src/app/`, `src/app/api/`, `src/app/schemas/`, `src/app/agent/`, `src/app/static/`, `src/app/data/`, `src/app/core/`, and `src/app/services/` are approved application folders. Obtain permission before adding any other folder.
- `services/` is approved for Slice 4 accounts, doctors and visits. `models/` remains a proposal until needed and approved.
- Choose the smallest correct solution: reuse existing code, then the standard library, native platform features, and installed dependencies before writing new code.
- Add no speculative abstractions, boilerplate, or dependencies. Fix shared root causes instead of patching individual callers.
- Mark deliberate shortcuts with a `ponytail:` comment naming their ceiling and upgrade path.
- Validate untrusted input, preserve useful error handling, and use synthetic test data. Never commit secrets or log request bodies or headers.

## Python environment and verification

- Use Python 3.14 or later and the repository's `.venv`; do not install dependencies globally.
- Use explicit PowerShell commands from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover tests
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir src
```

- If `.venv` is absent, follow the README setup instructions before running project commands.
- Leave one small runnable check for non-trivial logic; trivial one-liners need no new test.
- Run checks appropriate to the change. Report the commands, results, and anything unverified; never describe a blocked or skipped check as passing.

## Semantic commit messages

- Every commit must use Conventional Commits: `<type>(<scope>): <description>`.
- Allowed types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `build`, `ci`, `perf`, `style`.
- Choose a specific scope from the actual change, such as `api`, `schemas`, `config`, `tests`, `docs`, `packaging`, or `git`; avoid `misc`, `stuff`, or `general`.
- Use `feat` for new behavior, `fix` for corrections, `refactor` for restructuring without behavior changes, `test` for tests, `docs` for documentation, and `build` for dependencies or packaging.
- Write a concise, imperative description starting with a lowercase letter and without a final period.
- Mark breaking changes with `!` before the colon and describe the break in a `BREAKING CHANGE:` footer.
- Before committing, inspect the staged diff; derive the type and scope from those changes and split unrelated concerns when practical.
- Stage only the intended files. Preserve unrelated user changes. Do not create commits, push, or rewrite history unless requested.
- Valid examples: `feat(api): add health endpoint`, `fix(config): reject unsupported log levels`, `docs(rules): document repository workflow`, `build(packaging): add httpx dev dependency`.
- Invalid examples: `Update files`, `fix: changes`, `docs(misc): update stuff`.
