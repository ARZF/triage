# Healthcare Agent

Triage is a Persian, right-to-left healthcare workflow application built with
FastAPI, SQLite and dependency-free browser interfaces. It connects structured
patient intake, specialty suggestions, visit requests and doctor–patient chat,
with role-specific dashboards, account profiles and an independent doctor AI chat.
Administrators review doctor registrations without access to patient records.

**Portfolio project for fictional data.** Seed clinicians and public examples are
explicitly fictional. The application is not clinically validated or ready for
real patient information. Prescription and appointment booking are not implemented.

## Quick start

Requires Python 3.14 or later. From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
```

Set optional administrator/provider settings in the ignored `.env`; never commit
credentials. With `uv` available, load it into the existing virtual environment:

```powershell
uv run --no-project --env-file .env .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir src
```

Alternatively, set environment variables in PowerShell and run:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir src
```

The application reads the process environment and does not load `.env` itself.
Open [login](http://127.0.0.1:8000/login),
[patient workspace](http://127.0.0.1:8000/demo),
[doctor dashboard](http://127.0.0.1:8000/doctor),
[admin panel](http://127.0.0.1:8000/admin) or [API docs](http://127.0.0.1:8000/docs).
The patient URL `/demo` is retained for compatibility; it is not a separate mode.

Existing schema-v3 through v7 databases upgrade automatically to schema v8.
Keep existing databases; do not delete them as part of normal setup. The old
anonymous pre-account format is not migrated into owned accounts; see the
historical implementation notes in docs/plan.md before upgrading one.

## Accounts and workflow

Use invented usernames, display names, passwords and intake answers only.
Do not use real names, personal information or a password used elsewhere.
Both patients and doctors self-register. Usernames are lowercased ASCII,
3-32 characters from letters, digits, underscore, dot and hyphen. Passwords
are 8-128 characters. Doctor registration also needs a fictional display
name, a specialty, two or three short expertise phrases and a unique synthetic
license_number: 4–20 ASCII letters/digits/hyphens, stripped. Missing/invalid
licenses return 422; duplicates return 409 license_unavailable. These sample
numbers are fictional and unverified; this is not real license verification.
The signup and admin pages label this field «شماره نظام پزشکی»; the API/storage
name remains license_number, with the same synthetic-data validation.

Doctor accounts start unverified unless APP_DOCTOR_AUTO_VERIFY=true at
registration. APP_DOCTOR_AUTO_VERIFY=true is a development shortcut that skips
admin review for new registrations; it does not approve existing doctors.
Pending, rejected and suspended doctors may log in and see their own status
and review note, and edit their own profile/password, but have no queue/patient UI,
doctor data access or patient directory listing. Their page checks status every
15 seconds while visible. Suspended doctors can change passwords but cannot edit profiles.

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
shows a pending count, status navigation, synthetic doctor metadata and review audit;
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
and the patient sees the accepting doctor's card in the same conversation.
Acceptance opens the doctor's patient thread; exchange synthetic messages there.

The doctor dashboard reads requests every ten seconds while visible, without
writing rows. A separate heartbeat POST runs every 20 seconds even in another
tab, immediately after initial identity/verification load and when availability
turns on. It refreshes presence and sweeps expired pending requests in one transaction.
Online means verified, available, and seen in the last 90 seconds. The margin
allows browser timer throttling; a fully suspended browser cannot promise presence.
Switching availability off hides pending requests and blocks
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
Returning patients can confirm their saved complete health profile,
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

«گفت‌وگوی جدید» starts another intake for the same logged-in patient; an unfinished
intake remains in the sidebar after confirmation. Page load resumes the latest
conversation rather than creating a new session. The history API remains available,
but the UI uses the conversation list/detail endpoints. There is no localStorage
patient handle. Logout revokes the
current cookie session; delete-account removes the patient, user, all auth
sessions, intakes, messages, triage results and requests and clears the cookie.

## Triage and visit requests

After a non-emergency intake, the patient interface calls the triage endpoint automatically.
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
Create, cancel, accept and heartbeat operations sweep expired pending rows.
The patient list projects expired status without changing stored rows. Cancelled or
expired requests allow another request for the same intake, including after reload.
The patient conversation list polls every ten seconds while anything is pending
and the tab is visible. Accepted requests show the accepting doctor's card.

GET /v1/doctor/requests excludes overdue pending rows without updating them.
Doctor/patient request lists, conversation details and visit-message reads are read-only.
No GET accepts/cancels a request, changes availability, logs in or logs out.

## Accepted-visit text chat

Only the owning patient and the verified doctor who accepted the request can
read or post. Other accounts and non-accepted requests receive 404. The chat
does not call an LLM or add conversation text to provider context.

Each accepted conversation continues in one Persian RTL thread with distinct message bubbles,
a multiline input and a 2000-character counter. Enter sends; Shift+Enter adds a
newline. Messages are stripped and must contain 1–2000 characters afterwards.
There is a 500-message limit per visit. Empty, over-limit and pending sends are
disabled. The emergency-services banner stays above the composer.

Only the open conversation polls every three seconds while the tab is visible,
using the last message id and fetching further pages when needed. Navigation and
hidden tabs pause polling; reopening or returning fetches immediately. Consecutive read failures
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

## Shared dashboards and conversation navigation

The patient, doctor and admin pages share a top bar and toggleable RTL sidebar;
login remains self-contained. At 900px and above the sidebar starts open and
remembers its collapsed state when storage is available. Below 900px it starts
closed on each load, uses a backdrop, traps keyboard focus, closes with Escape
or a link, returns focus to the toggle and locks background scrolling. Motion
respects the reduced-motion preference. Hash routes support browser back/forward.

Patient routes are #/new, #/c/<session_id> and #/profile. The sidebar lists up to 50 recent
conversations with date, short complaint and status, plus «پروفایل من».
Confirmed account deletion is in the profile's danger section. The thread order is collected-data disclosure, intake/review, one
triage card, request status, accepting doctor, direct messages, then ended notice.
One bottom composer follows the current stage; pending/triage and ended/full
states prevent sending. Opening a saved conversation displays stored triage,
including fallback, without a provider call; «تلاش دوباره» explicitly refreshes it.

Doctor routes are #/queue, #/patient/<request_id>, #/profile and #/assistant. The queue badge and accepted
visits (active first, ended last) live in the sidebar with availability. The
patient thread starts with «گزارش سامانهٔ پذیرش», structured intake, previous
visits and the doctor-only AI warning. Admin routes are #/pending, #/approved,
#/rejected, #/suspended and #/audit, retaining review notes and paging.

Unread counts, push, per-conversation deletion/search, unfinished-session cleanup
or caps are not implemented.

## Profiles and password change

Open «پروفایل من» as a patient to edit age, height, weight, histories, current
medicines and food/drug allergies. Fields can be saved gradually; complete
profiles prefill only new assessments. Height/weight reuse the intake's positive
finite decimal parser, including Persian digits/٫. Profile text is vocabulary/data
only: no red-flag screening is added here. Existing conversations, history,
doctor reports and triage inputs remain unchanged after an edit.

Schema v8 backfills each profile once from the latest completed, non-emergency
session with every profile field present. A completed non-emergency intake
updates the profile atomically only if the profile was not edited after that
intake started. Emergency stops leave profiles untouched. Account deletion also
cascades to the profile; incomplete profiles start the normal full intake.

Every doctor can open «پروفایل», including while waiting for review. Approved
doctors can freely edit their name and expertise. Changing specialty or license
actually moves them to pending review, clears presence/availability and requires
no active accepted visits; otherwise 409 active_visits leaves everything unchanged.
Pending doctors can edit without changing status. A rejected doctor's actual edit
resubmits for review; suspended profiles are locked. Duplicate licenses return
409 license_unavailable. With APP_DOCTOR_AUTO_VERIFY=true, approved identity
edits stay approved even during active visits, and rejected resubmissions become
approved. Pending edits still stay pending. Score and review state are read-only.
Admin pending cards show the resubmission marker and date.

Patient and doctor profile pages include current/new/confirmation password
inputs. A successful change keeps the current cookie, invalidates other sessions
and makes the old password unusable. Five wrong current-password attempts in
15 minutes throttle password changes separately from login; the page shows the
Retry-After delay. An incorrect current password stays on the form.
Admin passwords come from APP_ADMIN_PASSWORD, and seeded doctors' passwords
come from APP_DEMO_DOCTOR_PASSWORD; the UI cannot change them. A managed-account
409 hides the password form and explains this restriction. Admin has no profile page.

Not implemented: email/phone, email password reset, MFA, account recovery,
doctor account deletion, profile change history/audit or profile photos.

## Independent doctor–Codex assistant

Verified doctors can open «دستیار پزشک» in the dashboard. This is a separate
Persian chat with streamed replies, Send, Stop and New Chat. Enter sends;
Shift+Enter inserts a newline. It supports discussion of synthetic clinical
cases for physician review, with an explicit AI-review notice. No final
prescriptions, patient-facing answers or automated clinical actions are added.

Only this chat's typed messages and one fixed server prompt are sent to Codex.
No intake, profiles, patient/doctor visit messages, previous tasks, repository
files or this development conversation are supplied automatically. The prompt
is in src/app/agent/doctor_assistant.py, independent from specialty triage.
There is no prompt editor, browsing, tools or record retrieval.

Completed turns live in page memory across dashboard navigation. Leaving the
tab stops generation; interrupted responses are marked and excluded from future
context. Codex's normal user-message lifecycle events are ignored; only assistant
answer text is shown. Reload, logout and New Chat clear the chat. Nothing is stored in the
application database, browser storage or application transcript logs. Codex's
operational state and provider-side data handling are separate; ephemeral threads
disable session rollout persistence, not an assurance about provider retention.
Keep using synthetic data only.

Install/maintain Codex separately and make `codex` available on the server's PATH.
Use a dedicated operator login/home, never your development Codex home or a
directory inside this repository. For example, in PowerShell as the server operator:

```powershell
$taskCodexHome = Join-Path $env:LOCALAPPDATA "HealthcareAgentCodex"
New-Item -ItemType Directory -Force -Path $taskCodexHome | Out-Null
$env:CODEX_HOME = $taskCodexHome
codex login
$env:APP_CODEX_HOME = $taskCodexHome
Remove-Item Env:CODEX_HOME
# Optional: $env:APP_CODEX_MODEL = "your-accessible-model"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir src
```

The operator completes Codex login; doctors do not sign into Codex individually.
Do not copy development credentials or modify the ignored .env automatically.
APP_CODEX_HOME may instead be set in that ignored file using the existing uv
launch command. Keep its directory private to the server operator. Its optional
config.toml may contain only model, model_reasoning_effort and
cli_auth_credentials_store; do not install skills/plugins/hooks or instruction
files there. Codex may create its own bundled skills/.system directory; the
bridge permits that runtime directory while disabling skill discovery/access.
Leave APP_CODEX_HOME empty to make assistant inference unavailable
without affecting the existing dashboard or triage. APP_CODEX_MODEL is optional;
an unavailable explicit model is not silently replaced.

The bridge checks the installed protocol, uses strict capability overrides and
an empty temporary working directory, and requires ephemeral threads with no
environment, capability roots, workspace roots or instruction files. It fails
closed for unsupported/unsafe configuration. No approval request is accepted.
An operator-managed Codex runtime is an additional deployment requirement, not
a new Python dependency. Current app-server protocol reference:
[Codex App Server](https://learn.chatgpt.com/docs/app-server).

There is one fresh process per request, a 120-second deadline, one active
request per doctor and two globally per application process. Stop/disconnect
interrupts and reaps the process. These process-local limits need a shared
limiter and isolated runtime pool before scaling across workers. Failed requests
are never resent automatically. User messages are limited to 4,000 characters;
submitted history to 40 messages/40,000 characters, output to 20,000. When full,
start a new chat; no previous turns are silently discarded.

## API

Public:
- GET /health, /docs, /demo, /login, /doctor, /admin (pages enforce role redirects).
- GET /assets/shell.css and /assets/shell.js: explicit local assets, no-cache;
  other asset names and traversal return 404. No directory is mounted.
- GET /v1/dictionaries/{kind}?q=&limit= (symptoms or medicines, q <=100, limit 1-100).
- GET /v1/specialties -> [{code, name_fa}].
- POST /v1/auth/register -> 201; POST /v1/auth/login -> 200.
  Both return {user: {id, role, username, display_name, doctor: null |
  {verified, status, review_note, available, specialty: {code, name_fa}}}}.
  Roles are patient|doctor|admin; admin display_name is «مدیر سیستم» and doctor=null.

Any logged-in role:
- POST /v1/auth/logout -> 204; GET /v1/auth/me. Both require a valid cookie.
- POST /v1/me/password {current_password,new_password} -> 204 for patient and
  self-registered doctor accounts. Extras forbidden, new password 8–128 and different.
  Wrong current password: 401 invalid_current_password; throttled: 429 with
  Retry-After; admin/seed username: 409 password_managed. No cookie is replaced.

Patient role:
- GET/PATCH /v1/patient/profile -> {profile:{age,height_cm,weight_kg,
  medical_history,medications,medication_history,food_allergies,allergies},updated_at,complete}.
  Unset fields/timestamp are null. PATCH requires at least one field, forbids
  extras/nulls, age integer 0–120, positive finite measurements and stripped
  text 1–2000; medications changes recompute stored dictionary codes.
- POST /v1/chat/sessions has no body and returns 201.
- GET /v1/chat/sessions?limit=20 (1–50): newest-first conversation summaries
  {session_id, created_at, summary, step, done, emergency, status, specialty,
  request_id}. Summary is the first 80 complaint characters, else symptoms,
  else null. One joined query; no writes. Status is emergency first, then the
  latest request (accepted becomes ended when ended_at is set; overdue pending
  projects expired), else triage when done, otherwise intake. Specialty uses
  stored triage before the latest request.
- GET /v1/chat/sessions/{session_id}: {session: ChatResponse, transcript:
  [{role, content, created_at}] in order, max 200, triage: patient TriageResponse
  or null, request: latest PatientVisit or null}. Read-only, stored triage only,
  no provider calls or doctor-only fields; unknown/other-patient sessions are 404.
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
- POST /v1/doctor/assistant/messages {messages:[{role:"user"|"assistant",content:str}]}
  -> text/event-stream: delta {text}, done {}, or error {error:{code,message}}.
  Completed alternating user/assistant pairs must end in the latest user message;
  no system/developer roles or extra fields. Before streaming, ErrorResponse
  covers 401/403 access, 422 validation, 429 assistant_busy (Retry-After:5),
  503 assistant_unavailable and 504 assistant_timeout. Midstream failures use
  safe error events; only final answer text is streamed, never reasoning/tool output.
- POST /v1/doctor/heartbeat, no body -> 204; the sole presence-refresh write.
- PUT /v1/doctor/availability {available: bool}.
- GET /v1/doctor/requests?status=pending|accepted; omitted status returns both.
- POST /v1/doctor/requests/{id}/accept -> updated item; atomic first acceptance wins.

Any doctor account, including unverified:
- GET/PATCH /v1/doctor/profile -> {name_fa,specialty,expertise,license_number,
  score,status,review_note,resubmitted_at}. PATCH accepts only name_fa (2–60),
  expertise (2–3 strings, 2–40 each), specialty_code and the existing ASCII
  license pattern; at least one field, stripped text, no extras/nulls. Doctor
  status rules above apply; suspended edits return 403 profile_locked.

Accepted patient or accepting verified doctor:
- GET /v1/visit-requests/{id}/messages?after=0&limit=50 ->
  {messages: [{id, sender, content, created_at}], ended, has_more}.
  Ascending ids greater than after; after is a nonnegative SQLite integer,
  limit is 1–100. Reading remains allowed after ending.
- POST /v1/visit-requests/{id}/messages {content} -> 201 the created message.
  Extra fields are forbidden; sender is derived from authentication.
- POST /v1/visit-requests/{id}/end -> 200 {ended: true}; accepting verified
  doctor only. Patients/unverified doctors receive 403; other doctors 404.

PatientVisit and DoctorVisit items include ended: bool and nullable accepted_at/
ended_at strings; PatientVisit also includes session_id. Visit-message responses
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
  status, reviewed_at, review_note, resubmitted_at}. Pending is oldest first; others newest review first.
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
- APP_DOCTOR_AUTO_VERIFY: true/false, default false; applies at registration and profile re-review/resubmission.
- APP_REQUEST_TTL_MINUTES: integer 1-1440, default 30.
- APP_ADMIN_USERNAME / APP_ADMIN_PASSWORD: optional pair; admin setup above.

Invalid new settings raise ValueError naming only the variable. Example:

```powershell
$env:APP_COOKIE_SECURE = "false" # Local HTTP only.
$env:APP_SESSION_TTL_HOURS = "12"
$env:APP_REQUEST_TTL_MINUTES = "30"
$env:APP_DOCTOR_AUTO_VERIFY = "true"
$env:APP_DEMO_DOCTOR_PASSWORD = "synthetic-seed-password"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir src
```

doctors.json is seed data only: nine specialties and twelve fictional doctors.
Startup validates/upserts seed data, preserving linked users, their edited name,
specialty/expertise and review state. Scores remain seed-managed. Optional seed
accounts use usernames equal to JSON ids, e.g. demo_doctor_1 and demo_doctor_2.
Setting the seed-account password creates/refreshes those account hashes. Without it,
no seed accounts are created and seed account login/session use is disabled;
existing account/link rows are preserved. Seed presence resets offline at startup
until a verified account sends a heartbeat. Self-registered doctors are stored in SQLite, not JSON.

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

## Storage, vocabulary and limitations

SQLite schema version 8 keeps the accounts, expanded intake and optional context,
adds nullable visit_requests.ended_at and an indexed visit_messages table through
atomic, version-gated additive migrations. Patient deletion cascades through
visit requests to direct messages. Fresh and upgraded databases have the same
structure, including concurrent first connections. The v7 transaction rebuilds
users to allow admin, preserves foreign-key references and indexes, and adds
doctor review/license columns and admin_audit. A foreign_key_check must pass
before commit; failures roll back and allow retry. Audit contains only admin/
doctor ids, action, statuses, synthetic review note and timestamp, without foreign keys.
The additive v8 migration adds patient_profiles with cascading ownership and
one-time complete-profile backfill, plus doctors.resubmitted_at. It runs under
BEGIN IMMEDIATE with rollback/retry and a version recheck for concurrent connections.
Existing accounts, visits and messages are preserved; previously unanswered
fields remain null. This upgrade does not require deleting a version-3 through v7 database.
Connections enable foreign keys and secure_delete; normal version-8 connections
skip schema writes. Connections close explicitly; message and acceptance
transactions are short. Explicit SQLite migrations cover these additions; use dedicated
migration tooling when migrations grow. SQLite files/journals are ignored by Git.

Passwords use salted scrypt (n=16384, r=8, p=1), constant-time digest comparison
and dummy verification for unknown users. Tokens use secrets.token_urlsafe(32);
only SHA-256 hashes are stored. Cookies use HttpOnly, SameSite=Lax, Path=/,
TTL Max-Age and optional Secure. SameSite=Lax is the current CSRF defense.
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
- src/app/agent/: intake, sessions, vocabulary, bounded context, triage and the
  isolated doctor_assistant.py Codex bridge/prompt.
- src/app/services/accounts.py, doctors.py, visits.py, chats.py, admin.py: accounts,
  presence, seeding, broadcast, acceptance, direct messages, visit ending and review.
- src/app/api/: auth, dependencies, chat, owned patient routes, catalogs,
  doctor/request routes, accepted-visit chats.py, assistant.py SSE and static pages.
- src/app/schemas/: explicit request/response models.
- src/app/data/: starter vocabulary and seed doctors.
- src/app/static/: index.html, doctor.html and admin.html share shell.css/shell.js;
  login.html uses the same shared design tokens. CSS/JS/HTML are packaged with the app.
- tests/: unittest checks, TestClient registration/login helper and temporary DBs.
- docs/plan.md and docs/changelog.md: approved contracts and change history.

```powershell
.\.venv\Scripts\python.exe -m unittest discover tests
```

Tests use synthetic data and temporary databases; provider requests are mocked.
The installed Starlette/httpx deprecation warning remains. For browser verification,
use separate private contexts so the three accounts have separate cookie jars.

## Public repository checklist

- `.env`, SQLite data/journals, authentication caches, local logs, virtual
  environments and build outputs are ignored. `.env.example` contains placeholders.
- Keep `/demo`, `APP_DEMO_DOCTOR_PASSWORD`, seed IDs such as `demo_doctor_1`
  and historical specifications for compatibility. These are technical identifiers,
  not current interface branding. Test fixtures remain explicitly synthetic.
- The prior returning-profile welcome prefix remains a read-only compatibility
  marker. New copy does not rewrite existing patient history or change schema v8.
- Before any real deployment, address the documented authentication hardening,
  CSRF protections beyond SameSite, transport/at-rest protection, consent,
  retention, audit, provider agreements and clinical review. UI polish does not
  establish security, compliance or clinical readiness.
- Choose an appropriate license before granting reuse rights publicly. This
  repository currently does not include a license; no licensing terms are assumed.

The frontend is static HTML/CSS/JavaScript: there is no npm build, linter or
formatter configured. Verify JavaScript syntax and the unittest suite; the
production packaging check is a Python wheel containing the local static assets.
The shared visual specification is in docs/design.md.
