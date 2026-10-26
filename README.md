# Healthcare Agent

Synthetic-data FastAPI demo with scripted Persian intake, vocabulary matching,
optional AI specialty triage, patient/doctor login and broadcast visit requests.
Accepted patients and doctors can exchange direct text messages. Authentication
is demo-grade. Administrators review doctor registrations without patient-data
access; there is no prescription or appointment booking.

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
Existing schema-v3, v4, v5 and v6 databases upgrade automatically to schema v7;
keep those databases when updating the intake or adding visit chat.

```powershell
# Run once only for the old disposable demo database, with the server stopped:
if (Test-Path -LiteralPath .\healthcare_agent.db) {
    Remove-Item -LiteralPath .\healthcare_agent.db
}
$env:APP_ADMIN_USERNAME = "admin_demo"
$env:APP_ADMIN_PASSWORD = "synthetic-admin-password" # Demo only, 12–128 characters.
Remove-Item Env:APP_DOCTOR_AUTO_VERIFY -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir src
```

Open [login](http://127.0.0.1:8000/login), [patient demo](http://127.0.0.1:8000/demo),
[doctor dashboard](http://127.0.0.1:8000/doctor), [admin panel](http://127.0.0.1:8000/admin),
or [API docs](http://127.0.0.1:8000/docs).

## Accounts and the demo workflow

Use invented usernames, display names, passwords and intake answers only.
Do not use real names, personal information or a password used elsewhere.
Both patients and doctors self-register. Usernames are lowercased ASCII,
3-32 characters from letters, digits, underscore, dot and hyphen. Passwords
are 8-128 characters. Doctor registration also needs a fictional display
name, a specialty, two or three short expertise phrases and a unique synthetic
license_number: 4–20 ASCII letters/digits/hyphens, stripped. Missing/invalid
licenses return 422; duplicates return 409 license_unavailable. These demo
numbers are fake and unverified; this is not real license verification.
The signup and admin pages label this field «شماره نظام پزشکی»; the API/storage
name remains license_number, with the same synthetic-demo validation.

Doctor accounts start unverified unless APP_DOCTOR_AUTO_VERIFY=true at
registration. APP_DOCTOR_AUTO_VERIFY=true is a local-demo shortcut that skips
admin review for new registrations; it does not approve existing doctors.
Pending, rejected and suspended doctors may log in and see their own status
and review note, but have no queue/patient UI, doctor data access or patient
directory listing. Their page checks status every five seconds while visible.

The configured admin username, literal admin and all seed-doctor ids are reserved
and cannot self-register. Admin accounts cannot self-register or access any
patient/doctor data endpoint, including visit chat (403).

## Admin setup and review

Set both APP_ADMIN_USERNAME and APP_ADMIN_PASSWORD, or neither. The username
must match lowercase ASCII [a-z0-9_.-], length 3–32; password length is 12–128.
Settings never load .env files or include these values in repr. Startup creates
the configured admin or refreshes its password hash. A username already owned
by a patient/doctor fails startup; usernames cannot be reused across roles.
With neither variable set, no admin is created and startup logs admin_disabled;
previous admin accounts cannot authenticate while unconfigured.

For local `.env` configuration, put APP_ADMIN_USERNAME and APP_ADMIN_PASSWORD
in the ignored repository-root `.env` file. Edit the values there; do not commit
the file. With `uv` installed, load it into the server's process environment:

```powershell
uv run --no-project --env-file .env .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir src
```

This uses the existing virtual environment without installing or syncing
dependencies. Settings still read only os.environ. Restart with this command
after changing `.env`; startup refreshes the configured admin password hash.

Log in as admin in a separate private browser session and open /admin. The panel
shows a pending count, status tabs, synthetic doctor metadata and review audit;
it never exposes usernames, password data, patient records, triage or chat.
Visible admin pages refresh every 15 seconds. Approve pending registrations;
Reject requires a 3–300-character stripped reason. Approved doctors may be
suspended with a reason. Rejected/suspended doctors can be approved again.
Invalid transitions return 409 invalid_transition and refresh the panel.

Suspension atomically clears verification/availability/presence, ends that
doctor's accepted unended visits and writes an audit entry. Patients retain
readable history with ended=true and locked chat inputs. Other doctors' visits
stay open. Reinstatement clears the review note but leaves ended visits ended
and availability off until the doctor opts in. Seed-data refresh preserves
admin review decisions. Review notes must contain synthetic information only.

To exercise matching, register two doctors of general practice in separate
private browser sessions, approve them in /admin, and leave their dashboards open. Register a patient
in another browser session, complete an intake, let triage finish, and press
the broadcast visit-request button. Both online doctors see the preview.
The first doctor to accept wins; the other queue clears on its next poll,
and the patient sees the accepting doctor's card. Open the chat panel on both
accepted-visit cards to exchange synthetic messages.

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
Create, cancel, accept and doctor-list operations sweep expired pending rows.
The patient list projects expired status without changing stored rows. Cancelled or
expired requests allow another request. The patient panel polls every ten
seconds while a request is pending and the tab is visible. An expired request
can be retried for the current page's remembered intake; after reloading, the
page offers a fresh intake because the request-list API does not expose
session ids. Accepted requests show the accepting doctor's card.

GET /v1/doctor/requests intentionally updates last_seen_at and sweeps expiry.
Patient request lists and visit-message reads are read-only.
No GET accepts/cancels a request, changes availability, logs in or logs out.

## Accepted-visit text chat

Only the owning patient and the verified doctor who accepted the request can
read or post. Other accounts and non-accepted requests receive 404. The chat
does not call an LLM or add conversation text to provider context.

Each accepted card has a Persian RTL chat panel with distinct message bubbles,
a multiline input and a 2000-character counter. Enter sends; Shift+Enter adds a
newline. Messages are stripped and must contain 1–2000 characters afterwards.
There is a 500-message limit per visit. Empty, over-limit and pending sends are
disabled. The emergency-services banner stays above the message history.

Open panels poll every three seconds while the tab is visible, using the last
message id and fetching further pages when needed. Closed/hidden panels pause;
reopening or returning to the tab fetches immediately. Consecutive read failures
back off to ten seconds; success restores three seconds. Reads retry automatically.
An uncertain send preserves its draft and asks the user to check history before
resending; automatic POST retries require future idempotency support. Refreshes
preserve the draft and scroll position. New messages scroll down only when near
the bottom or when the message is the user's own.

The accepting doctor selects «پایان ویزیت» and confirms inline. Both inputs lock
and show a read-only note; history remains accessible. Ending is idempotent,
and status remains accepted with ended=true. Ending does not reopen the intake
for another request. Posting after ending returns 409 visit_ended; reaching the
message ceiling returns 409 chat_full.

## API

Public:
- GET /health, /docs, /demo, /login, /doctor, /admin (pages enforce role redirects).
- GET /v1/dictionaries/{kind}?q=&limit= (symptoms or medicines, q <=100, limit 1-100).
- GET /v1/specialties -> [{code, name_fa}].
- POST /v1/auth/register -> 201; POST /v1/auth/login -> 200.
  Both return {user: {id, role, username, display_name, doctor: null |
  {verified, status, review_note, available, specialty: {code, name_fa}}}}.
  Roles are patient|doctor|admin; admin display_name is «مدیر سیستم» and doctor=null.

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

Accepted patient or accepting verified doctor:
- GET /v1/visit-requests/{id}/messages?after=0&limit=50 ->
  {messages: [{id, sender, content, created_at}], ended, has_more}.
  Ascending ids greater than after; after is a nonnegative SQLite integer,
  limit is 1–100. Reading remains allowed after ending.
- POST /v1/visit-requests/{id}/messages {content} -> 201 the created message.
  Extra fields are forbidden; sender is derived from authentication.
- POST /v1/visit-requests/{id}/end -> 200 {ended: true}; accepting verified
  doctor only. Patients/unverified doctors receive 403; other doctors 404.

PatientVisit and DoctorVisit items include ended: bool. Visit-message responses
contain no other-party username, patient/doctor id or intake session id.

Chat responses contain {session_id, returning, reply, step, done, emergency,
collected, matched}; patient_id has been removed. The old patient-id creation
body and /v1/patients/{patient_id}/... routes have been removed. Another
patient's session or request returns 404. No cookie is 401; wrong role or
unverified doctor is 403. Unknown/wrong-password logins share the same 401.
Other errors include 409 conflicts, 422 validation and 429 login throttle,
all in {error: {code, message}}. Handlers do not echo inputs or credentials.
All /v1 responses have Cache-Control: no-store.

Admin role only:
- GET /v1/admin/doctors?status=pending&limit=50&offset=0 -> {items, total}.
  Status: pending|approved|rejected|suspended; limit 1–100, offset >=0.
  Items: {id, name_fa, specialty, expertise, license_number, registered_at,
  status, reviewed_at, review_note}. Pending is oldest first; others newest review first.
- POST /v1/admin/doctors/{id}/approve -> updated item; pending/rejected/suspended only.
- POST /v1/admin/doctors/{id}/reject {note} -> updated item; pending only.
- POST /v1/admin/doctors/{id}/suspend {note} -> updated item; approved only.
- GET /v1/admin/audit?limit=50 -> {items: [{id, action, doctor_id,
  doctor_name_fa, from_status, to_status, note, created_at}]}, newest first, limit 1–100.
  Doctor names are null if the doctor is missing. All admin APIs require auth
  (401) and role admin (403 otherwise), and retain ErrorResponse/no-store.

## Configuration

Settings use os.environ; the application does not load .env files itself.
The optional uv command above loads .env before launch. See .env.example.
- APP_LOG_LEVEL defaults INFO; INFO/WARNING/ERROR/CRITICAL, case insensitive.
- APP_DB_PATH defaults healthcare_agent.db; must be non-empty.
- APP_COOKIE_SECURE: true/false, default false. Use true with HTTPS.
- APP_SESSION_TTL_HOURS: integer 1-168, default 12.
- APP_DEMO_DOCTOR_PASSWORD: optional 8-128 characters; excluded from repr.
- APP_DOCTOR_AUTO_VERIFY: true/false, default false; applies at registration.
- APP_REQUEST_TTL_MINUTES: integer 1-1440, default 30.
- APP_ADMIN_USERNAME / APP_ADMIN_PASSWORD: optional pair; admin setup above.

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

SQLite schema version 7 keeps the accounts, expanded intake and optional context,
adds nullable visit_requests.ended_at and an indexed visit_messages table through
atomic, version-gated additive migrations. Patient deletion cascades through
visit requests to direct messages. Fresh and upgraded databases have the same
structure, including concurrent first connections. The v7 transaction rebuilds
users to allow admin, preserves foreign-key references and indexes, and adds
doctor review/license columns and admin_audit. A foreign_key_check must pass
before commit; failures roll back and allow retry. Audit contains only admin/
doctor ids, action, statuses, synthetic review note and timestamp, without foreign keys.
Existing accounts, visits and messages are preserved; previously unanswered
fields remain null. This upgrade does not require deleting a version-3 through v6 database.
Connections enable foreign keys and secure_delete; normal version-7 connections
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

NOT implemented: real doctor credential checks, doctor
account deletion, ratings/reviews, password reset, email verification, MFA,
patient-data audit log, general rate limiting, HTTPS enforcement, prescriptions
or appointment scheduling. Retention is manual deletion only. Expired auth
sessions are rejected; no scheduled token cleanup, backup or general migration framework
is provided. Never commit real secrets. Usernames, passwords, tokens, cookies,
request bodies and headers are not logged; Uvicorn access logs stay disabled.

Chat features NOT implemented: WebSocket/push, attachments, typing and read
receipts, unread counts, moderation or reporting, message editing/deletion,
retention, audit log, chat export and doctor-to-doctor transfer.

Admin features NOT implemented: real license verification, admin user management
and self-service password reset, multi-admin roles, admin MFA, per-IP rate
limiting and alerting on admin actions. The review audit is limited to the
three supported doctor transitions.

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
- src/app/services/accounts.py, doctors.py, visits.py, chats.py, admin.py: accounts,
  presence, seeding, broadcast, acceptance, direct messages, visit ending and review.
- src/app/api/: auth, dependencies, chat, owned patient routes, catalogs,
  doctor/request routes, accepted-visit chats.py and static pages.
- src/app/schemas/: explicit request/response models.
- src/app/data/: starter vocabulary and seed doctors.
- src/app/static/: self-contained index.html, login.html, doctor.html and admin.html.
- tests/: unittest checks, TestClient registration/login helper and temporary DBs.
- docs/plan.md and docs/changelog.md: approved contracts and change history.

```powershell
.\.venv\Scripts\python.exe -m unittest discover tests
```

Tests use synthetic data and temporary databases; provider requests are mocked.
The installed Starlette/httpx deprecation warning remains. For browser verification,
use separate private contexts so the three accounts have separate cookie jars.
