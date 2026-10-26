# Healthcare Agent

Synthetic-data FastAPI demo with scripted Persian intake, vocabulary matching,
optional AI specialty triage, patient/doctor login and broadcast visit requests.
This is demo-grade authentication. There is no direct chat, prescription,
appointment booking or admin role.

## Setup and the Slice 4 breaking update

Requires Python 3.14 or later. From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

For databases from the old anonymous demo only, stop the server and delete the old disposable
synthetic database once, or select a fresh APP_DB_PATH. Old anonymous visits
have no account ownership and are not migrated into accounts. Keep any data
you need before resetting. The application never deletes the database for you.
Existing Slice 4 (schema-v3) and expanded-intake (schema-v4) databases upgrade automatically to schema v5;
keep those databases when updating the intake questions.

```powershell
# Run once only for the old disposable demo database, with the server stopped:
if (Test-Path -LiteralPath .\healthcare_agent.db) {
    Remove-Item -LiteralPath .\healthcare_agent.db
}
$env:APP_DOCTOR_AUTO_VERIFY = "true" # For newly self-registered demo doctors.
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir src
```

Open [login](http://127.0.0.1:8000/login), [patient demo](http://127.0.0.1:8000/demo),
[doctor dashboard](http://127.0.0.1:8000/doctor), or [API docs](http://127.0.0.1:8000/docs).

## Accounts and the demo workflow

Use invented usernames, display names, passwords and intake answers only.
Do not use real names, personal information or a password used elsewhere.
Both patients and doctors self-register. Usernames are lowercased ASCII,
3-32 characters from letters, digits, underscore, dot and hyphen. Passwords
are 8-128 characters. Doctor registration also needs a fictional display
name, a specialty and two or three short expertise phrases.

Doctor accounts start unverified unless APP_DOCTOR_AUTO_VERIFY=true at
registration. Unverified doctors can log in but see only a waiting banner
and cannot access doctor data endpoints or appear in patient doctor lists.
There is no admin approval flow yet; toggling auto-verify does not approve
already-registered doctors.

To exercise matching, register two doctors of general practice in separate
private browser sessions and leave their dashboards open. Register a patient
in another browser session, complete an intake, let triage finish, and press
the broadcast visit-request button. Both online doctors see the preview.
The first doctor to accept wins; the other queue clears on its next poll,
and the patient sees the accepting doctor's card. No communication channel
is opened in this slice.

The doctor dashboard polls every ten seconds while visible. Polling updates
its presence heartbeat. Online means verified, available, and seen in the
last 45 seconds. Switching availability off hides pending requests and blocks
acceptance while leaving the doctor's already-accepted visits visible.
Queue entries contain only age, symptoms, duration and severity previews.
The accepting doctor alone gets full structured intake, prior visits and the
doctor-only AI box with its generated/unverified/clinician-review notice.

Patient intake asks age, height (centimeters), weight (kilograms), main complaint,
symptoms, duration, severity, disease history, current medicines, past medication
use, food allergies, drug/other allergies, optional context for the doctor and
confirmation, in that order.
Current medicines are labeled «داروهایی که مصرف می‌کنید» and remain distinct
from «سابقه مصرف دارو». Heights/weights accept positive finite decimal numbers,
including Persian/Arabic-Indic digits and the Persian decimal separator (٫).
Persian dropdowns offer heights 30–250 cm and weights 1–300 kg in whole-unit
steps, in both intake and final-review edits. The custom-answer option keeps
exact decimals and other positive finite values available; the lists do not
change validation bounds.
These checks validate input format; no clinical plausibility or BMI calculation
is performed. Age is 0-120; severity 1-10. New text questions require non-empty
answers; histories/allergies accept «هیچ»/«ندارد». Invalid answers re-ask the step.
Returning patients can confirm their last complete non-emergency profile,
including height, weight, histories and allergies, then answer a new complaint
and symptoms. Profiles missing new fields start a full intake instead.
Negative final confirmation clears the intake; completed states do not change.

The final optional multiline box accepts up to 2000 characters and can be
skipped. Its additional_context value is available in the patient's own
review/history and only the accepting doctor's current/prior visit details.
It is never sent to the model: the provider context uses an explicit allowlist
for both current and previous visits, without notes or transcripts. A new visit
asks for a fresh note; returning-profile confirmation does not copy old notes.

Final confirmation uses a Persian inline card in the chat, grouped into personal
details, complaint/symptoms, history/medicines, allergies and doctor-only context.
Long answers expand on demand; earlier chat remains available in a disclosure.
«ویرایش اطلاعات» reveals field-specific controls. Save validates one correction
and returns to review without changing other answers; cancel discards the draft.
«بله، تأیید می‌کنم» turns the card into a compact confirmed summary and continues
triage. No modal is used. Edits are disabled after completion.

The Persian dropdowns load starter symptom/medicine names. Both symptom and
current-medicine answers support an editable multi-item list with custom entries, removal, deduplication
and an exclusive none choice. Vocabulary matches appear as plain chips.
A fixed Persian/English red-flag list can stop complaint or symptoms collection and show
the fixed emergency notice without saving the triggering text. This starter
list is not clinically reviewed and is not a clinical assessment.

Reset starts another visit for the same logged-in patient. History uses
/v1/me/history. There is no localStorage patient handle. Logout revokes the
current cookie session; delete-account removes the patient, user, all auth
sessions, intakes, messages, triage results and requests and clears the cookie.

## Triage and visit requests

After a non-emergency intake, the demo calls the triage endpoint automatically.
It shows specialty, urgency, optional reason, a fixed suggestion-not-diagnosis
notice and up to ten verified doctors, ordered online first, score descending
(NULL last), then name. New doctors have no score; the page shows «بدون امتیاز».
Scores are synthetic seed values; ratings and reviews are not implemented.

Without a provider or after invalid output/transport failure, triage stores a
general-practice fallback with unknown urgency. A later request retries a
stored fallback when the provider is configured. Valid output updates only a
fallback row; stored LLM rows are never overwritten or re-called. Failed retries
preserve the stored result with HTTP 200. Each user retry can cost one provider
call; no cooldown or general rate limiting is implemented. Context connections
close before provider I/O. Concurrent first calls can duplicate provider work,
but INSERT OR IGNORE keeps one result.

A request broadcasts to the triage specialty; patients cannot choose a doctor
id. Creation requires an owned, completed non-emergency intake, a stored triage
result whose urgency is not emergency, an online verified doctor, and no pending
or accepted request for that session. Each conflict has a safe distinct error
code. The triage button is disabled with an explanation if no listed doctor is
online. Use the existing triage refresh/retry control to refresh doctor presence.

Request statuses are pending, accepted, cancelled and expired. Patients may
cancel pending requests only. Pending requests expire after the configured TTL.
Every visit-request operation sweeps expired pending rows first. Cancelled or
expired requests allow another request. The patient panel polls every ten
seconds while a request is pending and the tab is visible. An expired request
can be retried for the current page's remembered intake; after reloading, the
page offers a fresh intake because the request-list API does not expose
session ids. Accepted requests show the accepting doctor's card.

GET /v1/doctor/requests intentionally updates last_seen_at; visit-request GET
lists can also persist derived expiry. These are the documented GET side effects.
No GET accepts/cancels a request, changes availability, logs in or logs out.

## API

Public:
- GET /health, /docs, /demo, /login, /doctor.
- GET /v1/dictionaries/{kind}?q=&limit= (symptoms or medicines, q <=100, limit 1-100).
- GET /v1/specialties -> [{code, name_fa}].
- POST /v1/auth/register -> 201; POST /v1/auth/login -> 200.
  Both return {user: {id, role, username, display_name, doctor: null |
  {verified, available, specialty: {code, name_fa}}}}.

Any logged-in role:
- POST /v1/auth/logout -> 204; GET /v1/auth/me. Both require a valid cookie.

Patient role:
- POST /v1/chat/sessions has no body and returns 201.
- POST /v1/chat/sessions/{session_id}/messages accepts {message: str}, length 1-2000.
  Optional edit_field names one collected field and is allowed only at unfinished
  final review. Invalid field/answer is 422; wrong stage/completed is 409. A valid
  correction returns to confirm and updates vocabulary matches. Blank/«رد کردن»/skip
  skips the optional note; the HTTP message itself must still have at least one character.
- POST /v1/chat/sessions/{session_id}/triage -> 200.
- GET /v1/me/history?limit=10 (1-50); DELETE /v1/me -> 204.
- POST /v1/visit-requests {session_id} -> 201; GET /v1/visit-requests -> own newest-first items.
- POST /v1/visit-requests/{id}/cancel -> updated item.

Verified doctor role:
- PUT /v1/doctor/availability {available: bool}.
- GET /v1/doctor/requests?status=pending|accepted; omitted status returns both.
- POST /v1/doctor/requests/{id}/accept -> updated item; atomic first acceptance wins.

Chat responses contain {session_id, returning, reply, step, done, emergency,
collected, matched}; patient_id has been removed. The old patient-id creation
body and /v1/patients/{patient_id}/... routes have been removed. Another
patient's session or request returns 404. No cookie is 401; wrong role or
unverified doctor is 403. Unknown/wrong-password logins share the same 401.
Other errors include 409 conflicts, 422 validation and 429 login throttle,
all in {error: {code, message}}. Handlers do not echo inputs or credentials.
All /v1 responses have Cache-Control: no-store.

## Configuration

Settings use os.environ; .env files are not loaded. See .env.example.
- APP_LOG_LEVEL defaults INFO; INFO/WARNING/ERROR/CRITICAL, case insensitive.
- APP_DB_PATH defaults healthcare_agent.db; must be non-empty.
- APP_COOKIE_SECURE: true/false, default false. Use true with HTTPS.
- APP_SESSION_TTL_HOURS: integer 1-168, default 12.
- APP_DEMO_DOCTOR_PASSWORD: optional 8-128 characters; excluded from repr.
- APP_DOCTOR_AUTO_VERIFY: true/false, default false; applies at registration.
- APP_REQUEST_TTL_MINUTES: integer 1-1440, default 30.

Invalid new settings raise ValueError naming only the variable. Example:

```powershell
$env:APP_COOKIE_SECURE = "false" # Local HTTP demo only.
$env:APP_SESSION_TTL_HOURS = "12"
$env:APP_REQUEST_TTL_MINUTES = "30"
$env:APP_DOCTOR_AUTO_VERIFY = "true"
$env:APP_DEMO_DOCTOR_PASSWORD = "synthetic-demo-password"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir src
```

doctors.json is seed data only: nine specialties and twelve fictional doctors.
Startup validates/upserts them verified, preserving linked users. Optional seed
accounts use usernames equal to JSON ids, e.g. demo_doctor_1 and demo_doctor_2.
Setting the demo password creates/refreshes those account hashes. Without it,
no seed accounts are created and seed account login/session use is disabled;
existing account/link rows are preserved. Seed presence resets offline at startup
until dashboards poll. Self-registered doctors are stored in SQLite, not JSON.

Optional provider settings:
- APP_LLM_BASE_URL: HTTP/HTTPS URL including any /v1 prefix, without credentials,
  query or fragment.
- APP_LLM_MODEL: model id; URL and model together enable calls.
- APP_LLM_API_KEY: optional bearer key, excluded from repr.
- APP_LLM_TIMEOUT_SECONDS: finite float 1-120, default 30.

```powershell
$env:APP_LLM_BASE_URL = "http://127.0.0.1:8080/v1"
$env:APP_LLM_MODEL = "your-model-id"
$env:APP_LLM_API_KEY = ""
$env:APP_LLM_TIMEOUT_SECONDS = "30"
```

The provider receives current structured intake plus up to three previous
completed non-emergency visits, dates, matched names and prior specialty.
Text is capped at 500 characters; identifiers, transcripts and additional_context
are excluded. The accepting doctor's note projection retains the full note.
Doctor-only AI summary/considerations are never in patient triage responses.

## Storage, vocabulary and demo limits

SQLite schema version 5 keeps the version-3 accounts/doctor/request tables,
the six expanded-intake columns and a nullable additional_context column through
atomic, version-gated additive migrations.
Existing accounts, visits and messages are preserved; previously unanswered
fields remain null. This upgrade does not require deleting a version-3 or version-4 database.
Connections enable foreign keys and secure_delete; normal version-5 connections
skip schema writes. Connections close explicitly; message and acceptance
transactions are short. Explicit SQLite migrations cover these additions; use dedicated
migration tooling when migrations grow. SQLite files/journals are ignored by Git.

Passwords use salted scrypt (n=16384, r=8, p=1), constant-time digest comparison
and dummy verification for unknown users. Tokens use secrets.token_urlsafe(32);
only SHA-256 hashes are stored. Cookies use HttpOnly, SameSite=Lax, Path=/,
TTL Max-Age and optional Secure. SameSite=Lax is this demo's CSRF defense.
Login failures throttle per lowercase username: five failures in fifteen minutes,
429 with Retry-After, success clears failures. This in-memory throttle is bounded
to 10000 keys and applies per process. Presence uses SQLite and polling.

**Synthetic data only.** Before real data, require a data-processing agreement,
lawful basis and data-location decision for the provider, plus appropriate
authentication hardening, encryption at rest, consent, retention and audit.
AI considerations are generated, unverified and doctor-only.

NOT implemented: admin approval of doctors, doctor credential checks, doctor
account deletion, ratings/reviews, password reset, email verification, MFA,
audit log, general rate limiting, HTTPS enforcement, direct chat, prescriptions
or appointment scheduling. Retention is manual deletion only. Expired auth
sessions are rejected; no scheduled token cleanup, backup or general migration framework
is provided. Never commit real secrets. Usernames, passwords, tokens, cookies,
request bodies and headers are not logged; Uvicorn access logs stay disabled.

Symptoms/medicines remain validated JSON starter catalogs, not clinically
reviewed. Codes are unique lowercase slugs; names/aliases must be non-empty.
Aliases are spelling/wording variants, with no brands, doses or clinical
grouping. Edit JSON locally and restart. Matching normalizes Arabic/Persian
letters, half-spaces, digits, punctuation and whitespace; it matches whole
phrases and preserves first-appearance order. Catalog search uses substrings.

## Structure and verification

- src/app/main.py: lifespan, routers, logging and no-store middleware.
- src/app/core/: settings, SQLite, security, provider client and errors.
- src/app/agent/: intake, sessions, vocabulary, bounded context and triage.
- src/app/services/accounts.py, doctors.py, visits.py: accounts, presence,
  seeding, broadcast and acceptance.
- src/app/api/: auth, dependencies, chat, owned patient routes, catalogs,
  doctor/request routes and static pages.
- src/app/schemas/: explicit request/response models.
- src/app/data/: starter vocabulary and seed doctors.
- src/app/static/: self-contained index.html, login.html and doctor.html.
- tests/: unittest checks, TestClient registration/login helper and temporary DBs.
- docs/plan.md and docs/changelog.md: approved contracts and change history.

```powershell
.\.venv\Scripts\python.exe -m unittest discover tests
```

Tests use synthetic data and temporary databases; provider requests are mocked.
The installed Starlette/httpx deprecation warning remains. For browser verification,
use separate private contexts so the three accounts have separate cookie jars.
