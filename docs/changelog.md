# Changelog

Record notable project changes here. Keep pending changes under Unreleased;
move them into a dated version section when a release is made.

## Unreleased

### Added

- Repository-wide `AGENTS.md` rules for reading docs before edits, scoped Conventional Commits, implementation boundaries, and virtual-environment verification.

- Approved `app`, `api`, and `schemas` packages, environment settings, response models, and generic error handlers.
- Standard-library unittest checks and optional `httpx` dev dependency.

- Separate `src/`, `tests/`, and `docs/` folders.
- Minimal FastAPI application with a `GET /health` endpoint.
- Project dependencies, setup instructions, Git ignore rules, and configuration placeholder file.
- Implementation specification and feature template in `docs/plan.md`.
- This changelog in `docs/changelog.md`.

### Changed

- Moved the application from `src/main.py` to `src/app/main.py` and switched to package discovery.
- Updated configuration examples, run/test instructions, and the implementation plan.

- Raised the minimum Python version from 3.11 to 3.14.
- Updated the README and implementation plan to match the Python requirement.
