# Medicore — Backend

**English** · [Español](README.es.md)

API and business logic for Medicore, a **multi-tenant** clinic management system, organized
with **Clean Architecture**.

## Stack

- **Python ≥ 3.12**
- **FastAPI** + **Uvicorn** — REST API (`/api/v1` prefix)
- **SQLAlchemy 2.0** + **PostgreSQL** (psycopg3) — persistence
- **Alembic** — schema migrations
- **PyJWT** + **bcrypt** — authentication and password hashing
- **cryptography** — AES-256-GCM for the superadmins' MFA secrets
- **pydantic-settings** — environment-based configuration
- **pytest** + **ruff** — testing and linting

## Layers

```
src/medicore/
├── domain/          # Business core. No framework dependencies.
│   ├── enums.py
│   ├── shared/        # domain errors + identifiers (UUID + code)
│   ├── value_objects/ # Vitals, SoapNote, IcdCode, ContactInfo, BloodType, Slug…
│   ├── entities/      # Patient, Appointment, Consultation, MedicalRecord, Prescription…
│   ├── services/      # domain services (logic that doesn't belong to a single entity)
│   └── repositories/  # interfaces (ports); implementations live in infrastructure
├── application/     # use cases (interactors), DTOs, infrastructure ports
├── infrastructure/  # SQLAlchemy, JWT/bcrypt auth, code generator, multi-tenant filter
└── presentation/    # FastAPI: routers, schemas, serializers, error handling
```

The **dependency rule** points inward: `domain` imports from no other layer; `application`
only from `domain`; `infrastructure`/`presentation` from the inner layers.

By the numbers: **22 entities** and **10 value objects** in the domain, **20 repositories
(Protocols)**, **5 application ports** (Clock, CodeGenerator, PasswordHasher, TokenIssuer,
UnitOfWork), **20 use-case groups** and **26 routers / 183 endpoints** under `/api/v1/`.

## Domain conventions

- **Value Objects**: `@dataclass(frozen=True)`, validating invariants in `__post_init__`.
- **Entities / aggregates**: mutable `@dataclass`; mutation goes through methods that preserve
  invariants (e.g. the `Appointment` state machine, or the immutable signature of
  `MedicalRecord`).
- **Identity**: a UUID (`*Id`) is the real key; a separate human-readable `code` for the UI
  (`P-00142`, `A-2401`, `REC-2026-0512-CR`).
- **Multi-tenancy**: every business entity carries a `tenant_id`; tenant filtering is the
  repositories' responsibility, not the caller's.
- **Clinical immutability**: a signed `MedicalRecord` is never modified; a correction creates an
  **amendment** (a new record with `status=amended` that references the original). Only the record's author amends it, only its current version, and always with a reason; the versions form a single chain (`amends_record_id` is unique) and each version keeps its signer (`signed_by_id`, `signed_at`).
- **Record seal** (`domain/services/record_seal.py`, OZK-99): each version stores `seal` (SHA-256, `seal_version` 1) over its immutable columns and the seal of the previous version, serialized in a canonical form that version 1 freezes. Signing and amending copy the digest into the audit log (`consultation.signed`, `record.amended`). Reads, versions, printed copies and certificates verify the chain and return `integrity`: `ok`, `tampered` or `unverifiable` (an unknown seal version); the patient's history leaves it `null`. A tampered record still shows, with a warning, its printed copy carries a visible notice, the event is audited as `record.integrity_failed` (version ids only, never content), and amending it answers 409 `record.tampered`. The seal is unkeyed: whoever can write to the database can recompute it, so the triggers in this section guard against mistakes and casual SQL, not against an attacker with database access.

## Features

- **Authentication** with JWT and roles (`admin`, `doctor`, `nurse`, `receptionist`), with a
  forced password change on first sign-in (until then only the change, the profile and sign-out are allowed; anything else answers 403 `auth.password_change_required`; support sessions are exempt). The session travels in an **httpOnly cookie**
  (`mc_session` for clinics, SameSite=Lax; `mc_console` for the platform console, SameSite=Strict
  and sent only to `/api/v1/platform`; `Secure` with `__Host-` / `__Secure-` prefixes outside
  development) with a **CSRF token bound to the session** (`mc_csrf` / `mc_console_csrf` +
  `X-CSRF-Token` header on mutations; it is an HMAC of the session id, so a token from one
  scope is useless in the other); the `Authorization: Bearer` header is accepted as an
  alternative for API clients.
- **Server-side revocable sessions**: every login creates a row in `sessions` referenced by
  the JWT's `sid` claim and validated on every request. Logout really revokes, changing the
  password revokes the user's other sessions, and suspending an account or resetting its
  password ends all its sessions immediately. **Active sessions** view: each user sees and
  ends their own (Settings), an admin those of any user in their clinic, and the superadmin
  those of a whole clinic (third-party revocations audited as `session.revoked`).
- **Signed tokens**: each token type carries its own audience (`medicore:tenant`, `medicore:platform`, `medicore:mfa`) and the mandatory claims `exp`, `iat`, `sub`, `aud`, `scope` and `sid`. A token of another type answers 401 `auth.wrong_session`, and its claims are cross-checked against the session row (user, clinic, scope, impersonator). `JWT_ALGORITHM` accepts only `HS256`, `HS384` or `HS512`. Tokens issued before this version have no audience, so every user, including superadmins, signs in again once after deploying.
- **Console session limits**: the superadmin console session expires after 30 min without activity and at most 8 h after sign-in (`PLATFORM_SESSION_IDLE_MINUTES` / `PLATFORM_SESSION_MAX_MINUTES`). Monitoring's background refresh does not count as activity, and a deactivated superadmin loses access on the next request.
- **Optional MFA (TOTP) for superadmins**: enabled from the console under *Account security* (`/platform/security`). With MFA on, the console login asks for the password and then a 6-digit code from an authenticator app, or a recovery code. The challenge is single-use, valid for 5 min and kept in an httpOnly cookie limited to `/api/v1/platform/login`. A code can't be reused, and after 5 failed attempts the lockout escalates. There are 10 single-use recovery codes, shown once and stored as hashes. The TOTP secret is encrypted with AES-256-GCM. Enabling MFA, regenerating the recovery codes or disabling it requires the current password, and every change is recorded in the platform audit log.
- **Login lockout** with three counters: per IP (30 attempts in 15 min → 15 min block, IPv6 by /64); per account from one IP (5 failures → 1 min, doubling up to 15); per account in total (20 attempts in 15 min, exempt for an IP that signed in to that account in the last 30 days). Each attempt is reserved atomically before the password check. Blocked attempts get HTTP 429 + `Retry-After`; an IP block answers the same whether or not the account exists, so the lockout doesn't reveal which accounts exist. A successful sign-in clears only that account's failures from that IP. A support reactivation or password reset also lifts that account's lockout, but not the IP counter. The console's second factor keeps its own limit of 5 per superadmin. Changing the password has its own lockout: 5 failed attempts with the current password block that account (429 with `Retry-After`, with backoff); a weak new password doesn't count. The superadmin MFA actions (setup, recovery codes, disabling) are limited too.
- **Input limits**: slug ≤ 63, email ≤ 254 (lowercase, no spaces, format-checked on invite and create: `user.invalid_email`), password ≤ 256, names ≤ 255; user agent truncated to 400 and IP to 45 characters in sessions and audit. 422 responses no longer echo the submitted value (`input`).
- **Responses**: every `/api/` response carries `Cache-Control: no-store`, except those that set their own (such as CSV downloads).
- **Plan quotas**: the seat check locks the clinic's row (`FOR NO KEY UPDATE`), so two simultaneous invitations can't exceed the plan.
- **Last administrator**: no operation, from the clinic or the platform console, can leave a clinic without an active admin (409 `users.last_admin`), even with concurrent changes.
- **Granular permissions** (`application/common/permissions.py`): a catalog of **39
  permissions** (`Permission`, `StrEnum`), a default set per role (`ROLE_PERMISSIONS`) and
  **per-tenant overrides** via `RolePermissionOverride`. `effective_permissions(role, stored)`
  resolves defaults vs. override and intersects with the current catalog; the presentation
  layer puts them in `ActorContext.permissions`, so every `ensure_permission(...)` honors the
  clinic's customization. The `role_permissions` router (`GET`/`PUT`/`DELETE`) manages them. Changing a user's role clears their per-user exceptions; admins always keep the full set of their role.
- **Patients**: the list's filters (status, primary doctor) also apply to searches, and the
  search matches every word against the full name, code or phone, ignoring accents. Each item
  carries its last completed and next visit; `GET /patients/stats` gives the page's headline
  numbers (active, inactive, new in 30 days, with an upcoming visit).
- **Vaccination** (`domain/services/immunization.py`): El Salvador's national scheme (MINSAL)
  for childhood, adolescence and older adults, plus doses by indication (pregnancy, risk
  groups). The scheme is national, so it lives in code as versioned data; only the doses
  recorded are stored (`vaccination_records`). Each dose's status (given, refused,
  contraindicated, due, overdue, due soon, upcoming, not applicable) is computed from the
  patient's age, sex and records — periodic doses (yearly influenza, Td every 10 years) come
  due again a period after the last one. A dose given at the clinic requires its lot; doses
  copied from the patient's card are recorded as external. Records are never edited: a wrong
  one is voided with a reason and stays in the history. `vaccinations` router: catalog,
  patient card, record, void and a clinic-wide worklist (due/overdue, upcoming within a
  horizon, given today). Permissions `vaccinations.view` / `vaccinations.record`.
- **In-clinic applications** (`domain/entities/application.py`): an `ApplicationOrder` says
  what to apply (drug, dose, route, number of doses and interval, observation minutes —
  30 by default). Internal orders are drafted in the consultation and issued atomically when
  it is signed; external ones (walk-ins) record the outside prescriber and their JVPM number.
  Each dose is an `ApplicationRecord` (applied, refused or contraindicated; lot, expiry, site,
  blood pressure, temperature) that is never edited — a wrong one is voided with a reason and
  its dose is due again. An applied dose opens an observation window, closed as "no
  reaction" or as an adverse reaction (which notifies the ordering doctor, without clinical
  content). `domain/services/allergies.py` matches the drug against the patient's allergies
  (direct names and drug families: penicillins, cephalosporins, NSAIDs, sulfonamides,
  dipyrone); applying anyway requires an audited justification. `applications` router:
  worklist (due today, under observation, recorded today), patient history, external order,
  cancel, record, close observation and void. Permissions `applications.view` /
  `applications.administer`.
- **Minor procedures** (`domain/entities/procedure.py`): each clinic has a catalog of
  `ProcedureType`s, preloaded on first read from `domain/services/procedure_catalog.py` (14
  common procedures with technique and instruction templates) and editable by the admin:
  who may perform it (`doctor` or `doctor_or_nurse`), informed consent, usual pathology
  specimen and suggested follow-up days. A `Procedure` freezes those rules when it is
  ordered — drafted in the consultation and issued atomically when it is signed, or
  registered directly — and can be tied to a `procedure` appointment, which is completed when
  the procedure is signed. Consent signed on paper is recorded as signer, relationship and
  witness (no file). Signing requires the consent (if needed), the allergy review, the
  technique and, when a specimen was sent, its description; an anesthesia that clashes with
  the patient's allergies needs an audited justification. Once signed the note is immutable:
  corrections are amendments (performer or a doctor). The ordering doctor is notified when
  someone else performs it, without clinical content. `procedures` router: catalog, worklist
  (pending, today's procedure appointments, done in the last 30 days), patient history,
  create, progress, consent, sign, cancel and amend. Permissions `procedures.view` /
  `procedures.perform` / `procedures.catalog`. Every writer of a procedure (save, consent, sign, cancel, amend, fee) locks its row first: a second signature, or any write to a signed procedure, answers 409 `procedure.already_signed`, while a cancelled one stays at 422 `procedure.closed`. Signing also locks the appointment it completes, and creating a procedure on an appointment locks that appointment, so two registrations at once can't both succeed (the second answers 422 `procedure.appointment_taken`).
- **Scheduling**: per-doctor availability, slot resolution, appointment lifecycle
  (scheduled → confirmed → in progress → completed). Transitions (confirm, cancel, no-show, reschedule, fee adjustment) lock the appointment inside the transaction and run one after another: the loser of a race reads the new status and gets 422 `invalid_transition`. An in-progress or completed appointment can't be cancelled.
- **Consultation → record**: signing a consultation issues an immutable `MedicalRecord` plus
  the prescriptions and completes the appointment, all in one transaction. The sign locks the
  consultation row before validating and taking the record number, so concurrent signs and edits
  of the same consultation are serialized: a second sign or an edit of a signed one answers 409
  (`consultation.already_signed`), a late autosave cannot revert it to a draft, and starting the
  same appointment twice returns the same consultation.
- **Consultation access** (`application/use_cases/consultations.py`): the note, diagnoses and drafts belong to the owning doctor (`consultations.edit` is `DOCTOR_ONLY`). Another doctor gets 403 `consultation.not_own`, other roles 403 `permission.missing` and support impersonation 403 `support.clinical_forbidden`; admins can start a consultation but not read or change it. Nurses write vitals with `consultations.vitals` (delegable, nurses by default): `GET /consultations/by-appointment/{appointment_id}/vitals` answers 404 `consultation.not_started` when the appointment has no consultation yet, and `PUT /consultations/{id}/vitals` takes partial updates (a field sent as `null` is cleared; a signed consultation answers 409 `consultation.already_signed`). `POST /consultations/start/{appointment_id}` answers a minimal reference (`id`, `appointment_id`, `patient_id`, `doctor_id`, `status`, `started_at`) without the note, and `PATCH /autosave` merges vitals field by field.
- **Medical records reading** (`application/use_cases/records.py`, `records` router): the clinical content of a record (note, diagnoses, prescriptions, vaccines, exams, full copy, certificates and the clinical history) needs `records.read_clinical`, a doctor-only permission that can't be delegated (`DOCTOR_ONLY`); anyone else gets 403 `permission.missing`. `GET /records` is paginated (`{items, total, offset, limit}`, 25 by default, 100 at most) and filters on the server: `patient_id`, `type`, `date_from`/`date_to` (clinic days) and `q` (record code, patient name or code); a reversed range answers 400 `records.invalid_range`. It returns metadata only (no reason for the visit, note or vitals) and is backed by the index `ix_records_tenant_encounter`. New endpoints: `GET /patients/{id}/records` (clinical history, doctors only) and `GET /patients/{id}/vitals` (`records.view`); `GET /patients/{id}` adds `latest_vitals` and `recent_records` (up to 6, metadata only). Audit: `record.listed` (each page; never the search text), `record.viewed`, `record.history_viewed`, `patient.vitals_listed`, `prescription.listed` and `document.listed`. In printing, `GET /print/records/{id}` includes `document`; for non-doctors the prescription comes without the general instructions, and the full copy, the exam order and certificates (listing and printing) need `records.read_clinical`.
- **Record amendments** (`application/use_cases/records.py`, `records` router): `POST /records/{id}/amend` takes `{reason, chief_complaint?, note?}` and rejects unknown fields (422). Only the record's author amends it (403 `record.not_own`; support sessions get 403 `support.clinical_forbidden`), and only the current version (409 `record.superseded`, with `params.current_id`). An amendment with no changes answers 422 `record.amend_empty`; a reason outside 10 to 1000 characters answers 422 `record.amend_reason_invalid` (`params.min`, `params.max`). The reason is stored on the version (`amendment_reason`) and shown in the history and in the printed copy, but it stays out of the audit log, which records the changed sections (`changed`) and the reason's length (`reason_chars`), because administrators read it without clinical access. The check and the insert run under a row lock, and a partial unique index `uq_medical_records_amends` on `amends_record_id` backs it. Currency is derived (a version is current when nothing amends it), so signed records are never updated. `GET /records/{id}/versions` lists the chain (requires `records.read_clinical`, audited as `record.versions_viewed`). `RecordResponse` adds `amendment_reason`, `is_current` and `superseded_by_id`, and `GET /records/{id}` of an older version is still allowed. Lists (`GET /records`, `GET /patients/{id}/records`, vitals, and `recent_records` / `records_count` in `GET /patients/{id}`) show only current versions. `GET /print/records/{id}` resolves to the current version and adds `version` and `original_signed_at`. A certificate issued on a replaced record uses the current version, listing certificates by record walks the whole chain, and a printed certificate ends the consultation at the original signature time.
- **Prescriptions** (`application/use_cases/prescriptions.py`, `prescriptions` router): only the doctor who issued a prescription completes or cancels it (403 `prescription.not_own`; support sessions get 403, and administrators, who don't hold `prescriptions.manage`, get `permission.missing`). `prescriptions.manage` is `DOCTOR_ONLY`. Completing is the natural end of the treatment; cancelling stops it early and needs a reason of 10 to 500 characters, after stripping (422 `prescription.cancel_reason_invalid`, `params.min`, `params.max`). The reason is kept on the prescription (`cancel_reason`) and the audit log keeps only its length (`reason_chars`). `closed_at` and `closed_by_id` record when and by whom it was closed. `GET /prescriptions?patient_id=` returns `cancel_reason` only to actors with `records.read_clinical`; the others see the status and the date. Both transitions lock the row, so a complete and a cancel at the same time leave the second one with 422 `invalid_transition`. Nobody is notified: only the prescriber can act. Printing a record's prescription (`GET /print/records/{id}?document=prescription`) leaves out the cancelled ones; if all of them are cancelled it answers 400 `print.nothing_to_print`, and the signed record does not change. `POST /prescriptions/{id}/cancel` takes `{"reason": str}` and rejects unknown fields (422), so the backend and the frontend deploy together. Since OZK-99 a database trigger allows only the closing itself (`active` to `completed` or `cancelled`, with nothing else changed) and rejects `DELETE` and `TRUNCATE`.
- **Medical documents** (`application/use_cases/records.py`, `records` router; `MedicalDocument.register` and `link_to` in `domain/entities/medical_document.py`): `POST /documents` takes `patient_id`, `file_name`, `kind`, `mime_type`, `size_bytes` and an optional `record_id`, with length limits, and rejects unknown fields (422 `request_invalid`, so a client that still sends `storage_key` fails). The server generates the storage key as `{tenant_id}/{patient_id}/{document_id}`; it is unique in the database (`uq_medical_documents_storage_key`) and never returned: `DocumentResponse` and `GET /patients/{id}/documents` omit it. Only metadata is stored; there is no file upload yet. Support sessions can't register documents (`support.clinical_forbidden`). A `record_id` must belong to the same patient; if the record has been amended, the document links to its current version. `AttachDocument`, the use case with no endpoint, was removed.
- **In-app notifications** (`application/common/notifications.py`): use cases emit them inside
  their own transaction — they are saved together with the action or not at all — and never
  to the author themselves. Events: appointment created/rescheduled/cancelled/no-show (to the
  appointment's doctor), document uploaded (to the
  patient's assigned doctor or, if none, the doctor of their last completed appointment) and
  user created/role changed (to active admins), and support actions on a clinic's users (to active admins and the affected user; the impersonation entry, to admins only). Only `type` + `data` are stored (ids and
  labels, never clinical content or file names) and the client writes the text in its own
  language. `notifications` router: paginated list (filterable by unread and by category:
  `appointment`, `record`, `document`, `user`), unread count, mark one / all; read ones
  older than 90 days are purged when marking. During impersonation they can be read but are
  not marked as read.
- **Dashboard** (`GET /dashboard/summary`): real metrics for the day — appointments (excluding
  cancelled) and pending ones, registered patients and schedule occupancy (booked slots over
  slots within working hours) — compared with the same weekday of the previous week. A doctor
  sees only their own schedule; other roles see the whole clinic. Without permission for a
  metric, it comes back as `null`. Alongside it, `GET /appointments/upcoming` lists the next
  scheduled/confirmed appointments from now on, across days (same doctor scope).
- **Auditing (HIPAA/GDPR)** per tenant plus a global platform console; every action stores a
  readable `subject` in its metadata for a useful detail column. Consultation events: `consultation.viewed` (scope `full` or `vitals`), `consultation.note_updated`, `consultation.vitals_updated` (metadata `keys`), `consultation.template_changed` (`from`/`to`) and `consultation.draft_changed` (`section`/`op`), with names only, never clinical text. Reads, note and vitals updates by the same actor are coalesced in 10-minute windows per key (`append_coalesced`), so autosave and polling don't fill the log.
- **Platform console** (superadmin): clinic onboarding/management, global stats, consolidated
  audit and **support sessions** (impersonation with a short TTL, a required reason of 5–500 characters and a trail in the clinic's audit). Support actions on a clinic's users (password reset with a reason, edit, role change, suspension, reactivation) are recorded in that clinic's audit as "Platform support", with IP and browser but without the superadmin's identity, and are not duplicated in the global audit.

## Configuration

Copy `.env.example` to `.env` and adjust the values:

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | `development` or `production`. Production enables strict validation. | `development` |
| `DATABASE_URL` | PostgreSQL connection string (psycopg3) | `postgresql+psycopg://localhost/medicore` |
| `JWT_SECRET` | Secret used to sign tokens. **Required in production, at least 32 bytes** (`openssl rand -hex 32`). | `change-me` (dev only) |
| `JWT_ALGORITHM` | JWT algorithm: `HS256`, `HS384` or `HS512` only | `HS256` |
| `JWT_EXPIRE_MINUTES` | Token lifetime | `1440` (24 h) |
| `JWT_SUPPORT_EXPIRE_MINUTES` | Lifetime of support/impersonation sessions | `60` (1 h) |
| `COOKIE_SECURE` | `Secure` flag and `__Host-` / `__Secure-` prefixes on session cookies. Unset = on everywhere except `development`. Cannot be `false` in production. | derived from `ENVIRONMENT` |
| `PLATFORM_SESSION_IDLE_MINUTES` | Idle timeout of the platform console session (min, between 5 and the maximum) | `30` |
| `PLATFORM_SESSION_MAX_MINUTES` | Absolute lifetime of the platform console session (min) | `480` (8 h) |
| `PLATFORM_COOKIE_PATH` | Path of the console session cookie (only sent to the platform API) | `/api/v1/platform` |
| `MFA_ENCRYPTION_KEY` | Key that encrypts the superadmins' TOTP secrets (AES-256-GCM): 32 bytes in base64url. **Required in production** (the app won't start without it). In development, if empty, it's derived from `JWT_SECRET`. Losing it makes already-enabled MFA unverifiable. Generate it with `python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"` | empty |
| `MFA_ISSUER` | Name the authenticator app shows next to the code | `Medicore` |
| `CORS_ORIGINS` | Allowed origins (comma-separated); `*` only in development | `*` |
| `ENABLE_DOCS` | Expose Swagger/OpenAPI at `/api/v1/docs` | `true` (dev) / `false` (prod, unless explicitly enabled) |
| `TRUSTED_PROXIES` | IPs/CIDRs (comma-separated) of the reverse proxies whose `X-Forwarded-For` header is honored (e.g. `127.0.0.1` or `10.0.0.0/8`). Empty → the header is ignored and the socket IP is recorded. An invalid value prevents startup. | empty |
| `DEMO_PASSWORD` | Password for the demo users created by `scripts/seed_demo.py` (≥ 8 chars). **Required in production**, where the public default is rejected. | `demo1234` (dev only) |
| `DEMO_ADMIN_PASSWORD` | Password for the demo clinic admins (≥ 8 chars), kept private so the shared demo password doesn't open the administration. **Required in production** and different from `DEMO_PASSWORD` | `DEMO_PASSWORD` |

> In **production** (`ENVIRONMENT=production`) the app **refuses to start** if `JWT_SECRET` is
> still the insecure default or shorter than 32 bytes, or if `CORS_ORIGINS` is `*`, `COOKIE_SECURE` is `false` or `MFA_ENCRYPTION_KEY` is empty. API docs are also
> disabled unless `ENABLE_DOCS=true` is set explicitly. Nothing is validated in development and
> the defaults work as-is.

## Getting started

```bash
# 1) Environment and install (includes dev dependencies)
python -m venv .venv
.venv/bin/pip install -e ".[dev]"        # Windows: .venv\Scripts\pip install -e ".[dev]"

# 2) Database schema
.venv/bin/alembic upgrade head

# 3) (optional) ICD-10/ICD-11 diagnosis catalog
.venv/bin/python scripts/import_icd.py

# 4) Demo data: 3 clinics with ~8 weeks of history and 4 weeks of agenda, generated by
#    running the real use cases with a simulated clock (audit + notifications included)
.venv/bin/python scripts/seed_demo.py            # idempotent
.venv/bin/python scripts/seed_demo.py --reset    # deletes the demo tenants and recreates them

# 5) (optional) Create a platform superadmin
.venv/bin/python scripts/create_platform_admin.py

# Superadmin lost the authenticator app and the recovery codes: turns their MFA off and revokes their sessions
.venv/bin/python scripts/reset_platform_mfa.py <email>

# Scheduled task, daily in every environment: deletes expired or revoked sessions (recorded as the session_purge job)
.venv/bin/python scripts/purge_expired_sessions.py

# 6) Start the API
.venv/bin/uvicorn medicore.presentation.main:app --reload
```

- API at `http://localhost:8000/api/v1`, interactive docs at `/api/v1/docs`, liveness check at
  `/health` and readiness (database reachable, `503` otherwise) at `/health/ready`, also served
  as `/api/v1/health/ready` so an external uptime monitor can reach it through nginx.
- After running the seed, every demo user has the password from `DEMO_PASSWORD` (**`demo1234`**
  in development when unset) and the clinic admins the one from `DEMO_ADMIN_PASSWORD` (the same
  `DEMO_PASSWORD` when unset). In production both are required: the seed refuses the default and
  an admin password equal to the shared one.

The public demo has three clinics, one per plan. Existing slugs and email addresses stay the same.

| Clinic (slug) | Plan | Doctor seats | Support seats¹ | Clinical modules | Analytics |
|---|---|---|---|---|---|
| Policlínica Escalón (`clinica-demo`) | Clínica Plus | 5/5 | 4/6 | All three | Operational |
| Centro Médico Familiar del Norte (`centro-norte`) | Clínica | 3/3 | 3/3 | Vaccination | Clinic |
| Consultorio Médico Dra. Sofía Alvarenga (`doc-demo`) | Profesional independiente | 1/1 | 1/1 | None | Basic |

¹ The first admin does not use a support seat. Escalón includes an invited receptionist.
Sofía sees adults and children; Yesenia Ramos schedules appointments. Sign in with
`sofia.alvarenga@doc-demo.test` or `yesenia.ramos@doc-demo.test`; its admin is `admin@doc-demo.test`.
Passwords still come from `DEMO_PASSWORD` and `DEMO_ADMIN_PASSWORD`.

The nightly reset recreates only these three slugs; it leaves real clinics such as `clinica-loida` alone.
Before deploying, confirm that `doc-demo` is unused in production (checked absent on 2026-11-15).
Test the seed and `--reset` only against a disposable database, never the local working database.

## Error format

Every error response has the same shape:

```json
{"detail": "user with email x@y.test already exists", "code": "user.email_taken", "params": {"email": "x@y.test"}}
```

- `code` is stable and is what the frontend translates (`err.<code>` in
  `frontend/src/lib/i18n.ts`, with `{param}` interpolated from `params`). `detail` is English
  text for API clients and logs; it is not shown to the user.
- Errors carry a default code from their class (`not_found`, `permission_denied`,
  `invalid_transition`…) and a specific one where they are raised (`code="slot.not_bookable"`).
  `HTTPException`s without their own code come out as `http.<status>`; FastAPI validation (422)
  as `request_invalid` (with `detail` in its original list shape and the fields in
  `params.fields`); an unexpected failure (500) as `internal`.
- Enum fields (`role`, `sex`, `kind`, `status`…) are declared with the enum in the schemas: an
  unknown value is a 422 `request_invalid` naming the field, never a 500.
- `tests/presentation/test_error_codes_api.py` fails if the backend emits a code without a
  Spanish **and** an English translation: adding a new code means adding both texts.
- 401 is only for "who are you?" failures (credentials, session): the client drops the session
  on a 401. A wrong current password when changing it is a 400 (`password.current_incorrect`).
- Validation errors (422) no longer include the submitted value (`input`) in their details.
- Signing a consultation twice, or editing one that is already signed (autosave, diagnoses, drafts),
  answers 409 `consultation.already_signed`. `consultation.incomplete` stays a 422.
- Reading clinical content without `records.read_clinical` answers 403 `permission.missing`; a records list with `date_from` after `date_to` answers 400 `records.invalid_range`.
- Consultation access answers 403 `consultation.not_own` (another doctor's consultation), `permission.missing` (other roles) or `support.clinical_forbidden` (support impersonation); vitals of an appointment with no consultation answer 404 `consultation.not_started`.
- Record amendments answer 403 `record.not_own` (not the author) or `support.clinical_forbidden`, 409 `record.superseded` (`params.current_id`), 422 `record.amend_reason_invalid` (`params.min`, `params.max`) and 422 `record.amend_empty`.
- Closing a prescription answers 403 `prescription.not_own` (not the prescriber), 422 `prescription.cancel_reason_invalid` (`params.min`, `params.max`) when the reason is out of range, and 422 `invalid_transition` when it is already closed.
- Amending a record whose seal doesn't match answers 409 `record.tampered`. `record.unsealed` (amending a record that has no seal) and `record.seal_invalid` (a malformed seal) guard invariants that normal use doesn't reach.
- Uploading a document answers 403 `support.clinical_forbidden` (support sessions) or `permission.missing` (roles without `records.upload`), 422 `document.record_mismatch` (the record belongs to another patient), 404 `not_found` (missing patient, or missing record or one from another clinic), 400 `document.unsupported_type`, `document.too_large` or `document.invalid_name`, and 422 `request_invalid` for unknown fields such as `storage_key`.

## Tests and linting

A suite of **1789 tests** (385 domain · 766 application · 401 presentation · 233 infrastructure · 4 scripts),
almost entirely database-independent thanks to in-memory adapters that honor the same
multi-tenant contract as the SQLAlchemy repos.

The integration tests against real PostgreSQL (`tests/infrastructure/test_audit_repository_sql.py`,
`test_diagnosis_catalog_sql.py` — ranking and trigram search for the diagnosis autocomplete —
`test_login_throttle_sql.py` — atomic UPSERT of the login lockout —
`test_consultation_sign_sql.py` — concurrent signs and edits of one consultation —
`test_procedure_sign_sql.py` — concurrent signatures and late saves of one procedure —
`test_appointment_locks_sql.py` — appointment transitions racing consultation signatures and starts —
`test_notification_repository_sql.py` — JSONB and bulk UPDATE/DELETE of the inbox —
`test_record_summaries_sql.py` — the records list (summaries, filters and paging) — `test_record_amend_sql.py` — the amendment chain (row lock, unique index, reason CHECK) — `test_patient_search_sql.py` — accent-insensitive search, phone digits, last visits — `test_prescription_sql.py` — the closing fields, the cancel-reason CHECK and the row lock, and `test_document_repository_sql.py` — the document round trip and the unique storage key — and `test_record_integrity_sql.py` — the seal round trip, the append-only triggers (`UPDATE`, `DELETE`, `TRUNCATE`, also under `session_replication_role = replica`), the RESTRICT foreign keys and the detection of a tampered record) use
`TEST_DATABASE_URL` (or the configured `DATABASE_URL`), run inside a transaction that is always
rolled back — they leave no trace in the development database — and are **skipped
automatically** when PostgreSQL isn't reachable.

```bash
.venv/bin/pytest
.venv/bin/ruff check src tests
```

The demo seed integration test commits and exercises the nightly reset. It is skipped unless
`DEMO_TEST_DATABASE_URL` explicitly points to an **empty, migrated disposable database**;
it never falls back to the working database. After creating that disposable database, run:

```bash
DATABASE_URL="$DEMO_TEST_DATABASE_URL" .venv/bin/alembic upgrade head
.venv/bin/pytest tests/scripts -q
```

## Lock order

Writers of clinical documents and appointments lock their rows inside the transaction, in a fixed order, so two transactions never wait on each other (OZK-106). The canonical statement is the docstring of `AppointmentRepository.get_for_update`.

1. **Clinical document (N1)**: a consultation or a procedure. A transaction never locks both.
2. **Appointment (N2)**.
3. **Counter (N3)**: record code, appointment code and the rest. Always last, so nothing is locked while holding one.

Plain reads take no lock. Cancelling an appointment doesn't look at its consultation: a consultation exists only for appointments in progress or completed, and those can't be cancelled.

| Use case | Locks, in order |
|---|---|
| `SignConsultation` | consultation → appointment (before taking the record code) → record counter |
| Consultation editors, `UpdateConsultationVitals` | consultation |
| `StartConsultation` | appointment |
| `SignProcedure` | procedure → appointment |
| `SaveProcedureProgress`, `RecordProcedureConsent`, `CancelProcedure`, `AmendProcedure`, `SetProcedureFee` | procedure |
| `CreateProcedure` with an appointment | appointment |
| `ConfirmAppointment`, `CancelAppointment`, `MarkNoShow`, `RescheduleAppointment`, `AdjustAppointmentFee` | appointment |
| `CreateAppointment`, `CreatePatient`, certificates | their counter |

## Deployment

Production-ready Docker image (`Dockerfile` in this folder; non-root user, starts uvicorn on
port 8000). Its entrypoint applies pending migrations (`alembic upgrade head`) before starting
the app; set `SKIP_MIGRATIONS=1` to skip that. It also ships `scripts/` and the ICD CSVs in
`data/`, so the catalog import and the demo seed can run inside the container. For the full
stack (PostgreSQL + backend + nginx) see the root `docker-compose.yml`.

```bash
# Build
docker build -t medicore-backend .

# Migrations only (the entrypoint already runs them on start)
docker run --rm --env-file .env medicore-backend alembic upgrade head

# Start the API
docker run -d -p 8000:8000 --env-file .env medicore-backend
```

Production checklist (via environment variables, see the **Configuration** table):

- `ENVIRONMENT=production`
- A strong `JWT_SECRET` of at least 32 bytes (`openssl rand -hex 32`) — the app won't start if it's insecure or shorter.
- `MFA_ENCRYPTION_KEY` set (32 bytes, base64url) — the app won't start without it in production.
- `DATABASE_URL` pointing to the real database.
- `CORS_ORIGINS` with the frontend's origins (not `*`).
- `TRUSTED_PROXIES` with the reverse proxy's IP (e.g. `127.0.0.1` if nginx runs on the same
  host) so the audit trail records the real client IP.
- Optional: `ENABLE_DOCS=false` to hide Swagger/OpenAPI.
- A daily scheduled task running `python scripts/purge_expired_sessions.py` (see **Getting started**).

> **Upgrade note:** after applying migration `d0e1f2a3b4c6` (console session limits), clinic users and superadmins must sign in again once.

> **Before deploying this version:** set `MFA_ENCRYPTION_KEY` (32 bytes, base64url). Migration `e1f2a3b4c5d7` adds the MFA columns to `platform_admins` and the `platform_admin_recovery_codes` table.

> **Before deploying this version:** every user, including superadmins, signs in again once (tokens issued earlier have no audience).
>
> **Migration `f2a3b4c5d6e8`:** adds `last_success_at` to `login_attempts` (login lockout). It needs no new environment variables.
>
> **Migration `a3b4c5d6e7f9`:** adds a unique partial index so a consultation has at most one original medical record. **Before deploying, run the detection query in [Duplicate records from double signing](#duplicate-records-from-double-signing)**: the migration refuses to run while duplicates exist (it lists only their ids) and never resolves them itself. Creating the index blocks writes to `medical_records` for an instant. The Docker entrypoint runs `alembic upgrade head`, so the migration applies on deploy.
>
> **Migration `c4d5e6f7a8b0`:** adds the index `ix_records_tenant_encounter` on `medical_records(tenant_id, encounter_at)` for the records list, and grants `records.read_clinical` to the doctor role of clinics that had customized it. Creating the index blocks writes to `medical_records` for an instant. Its downgrade removes the permission from the doctor's customizations and drops the index.

> **Migration `e6f7a8b9c0d2`** (record amendments): adds `amendment_reason` (required on every amendment, enforced by a CHECK), fills the existing amendments with the placeholder reason "Enmienda previa a la exigencia de motivo", reassigns `author_id` of amendments made by another doctor to the original author of the chain (who signed each version stays in `signed_by_id` and in the audit log), and creates the unique index `uq_medical_records_amends`. **Before deploying, run the queries in [Branched amendment chains](#branched-amendment-chains)**: the migration refuses to run while any record has more than one amendment, and lists only their ids. Its downgrade drops the column, the CHECK and the index, but does not restore the reassigned authors. **Deploy the backend and the frontend together**: the previous frontend doesn't send the reason.
>
> **Migration `d5e6f7a8b9c1`** (consultation authorship): gives `consultations.edit` back to the doctor roles that customized it and drops doctors' revocations of it; in nurse and receptionist roles and users, `consultations.edit` becomes `consultations.vitals` (if a grant and a revocation of the same permission would both remain, the revocation wins; admins are untouched). **Before deploying, back up `role_permission_overrides` and the `users` table (column `permission_adjustments`).** Its downgrade turns `vitals` back into `edit`, but it does not restore the doctors' revocations.
>
> **Migration `f7a8b9c0d1e3`** (prescription closure): adds `closed_at`, `closed_by_id` and `cancel_reason`, with a CHECK that every cancelled prescription has a reason; the cancelled ones that predate it get the placeholder "Cancelación previa a la exigencia de motivo". `prescriptions.manage` becomes doctor-only: nurse and receptionist overrides and user adjustments lose it, and doctors get it back. **Before deploying, run the queries in [Prescriptions closed by someone else](#prescriptions-closed-by-someone-else)**, and deploy the backend and the frontend together: the cancel endpoint now requires a body with `reason`. Its downgrade drops the columns and the CHECK, but does not restore the permissions.

> **Migration `f8a9b0c1d2e4`** (document storage keys): unlinks (`record_id = NULL`) the documents whose record belongs to another patient or doesn't exist (the file stays with its patient), rewrites every `storage_key` to `{tenant_id}/{patient_id}/{id}` (no file is stored yet, so nothing moves) and creates the unique index `uq_medical_documents_storage_key`. **Before deploying, run the queries in [Document storage keys](#document-storage-keys)**, and deploy the backend and the frontend together: `POST /documents` no longer accepts `storage_key`. Its downgrade only drops the index; the unlinked records and the previous keys are not recovered.

> **Migration `a9b0c1d2e3f5`** (signed records protection, OZK-99): seals every version (`seal`, `seal_version` 1), so the seal certifies the content as it stood on the migration date, not when it was signed. It makes `medical_records` append-only (triggers that reject `UPDATE`, `DELETE` and `TRUNCATE`), lets prescriptions only be closed, changes the foreign keys of `medical_records`, `prescriptions` and `medical_documents` to RESTRICT and creates the indexes that back them. It unlinks (`record_id = NULL`) the prescriptions and documents whose record doesn't exist. It refuses to run, listing only ids, while any other dangling reference exists. **Before deploying, run the queries in [Signed records protection and dangling references before OZK-99](#signed-records-protection-and-dangling-references-before-ozk-99)**, and deploy the backend and the frontend together. Going back needs `alembic downgrade f8a9b0c1d2e4` as well as the previous code: the code alone leaves the triggers and the seal columns in the database.

> **Before deploying this version** (OZK-106, no migration): a signed procedure answers 409 `procedure.already_signed` instead of 422, so deploy the backend and the frontend together. Run the queries in [Inconsistent appointments and procedures before OZK-106](#inconsistent-appointments-and-procedures-before-ozk-106) first: they only report, and nothing is changed automatically.

> For multiple workers just set `WEB_CONCURRENCY=N` (uvicorn reads it; `docker-compose.yml` uses 2). Each
> worker holds its own pool of up to 15 connections: keep `N × 15` below Postgres' `max_connections`.
> The app is served behind a reverse proxy that terminates TLS and forwards `X-Forwarded-For`.
> The header is **only honored** if the connection comes from a proxy listed in
> `TRUSTED_PROXIES` (walking the chain right to left and discarding trusted hops); otherwise
> the socket IP is recorded. The image starts uvicorn with `--no-proxy-headers` so the app is
> the only one interpreting the header — keep it that way if you override the `CMD`.

## Duplicate records from double signing

Before migration `a3b4c5d6e7f9`, a consultation signed twice at the same time (double click, retry, two tabs) could end up with two original medical records. Signing now locks the consultation, and the migration adds a unique partial index on `medical_records(consultation_id)` for original records (amendments repeat `consultation_id` and are excluded), so the database refuses a second original. The migration never deduplicates: each duplicate is a clinical document, and deciding which one stands is a clinical decision. It therefore refuses to run while duplicates exist and lists only their ids.

Run this query against the production database before deploying:

```sql
SELECT r.tenant_id, r.consultation_id, r.id AS record_id, r.code, r.signed_at,
       (SELECT count(*) FROM prescriptions p WHERE p.record_id = r.id) AS prescriptions,
       (SELECT count(*) FROM application_orders a WHERE a.consultation_id = r.consultation_id) AS application_orders,
       (SELECT count(*) FROM procedures pr WHERE pr.consultation_id = r.consultation_id) AS procedures
FROM medical_records r
WHERE r.amends_record_id IS NULL AND r.consultation_id IN (
  SELECT consultation_id FROM medical_records
  WHERE consultation_id IS NOT NULL AND amends_record_id IS NULL
  GROUP BY consultation_id HAVING count(*) > 1)
ORDER BY r.consultation_id, r.signed_at;
```

- **No rows**: there are no duplicates, and the migration applies on deploy.
- **Rows**: resolve each consultation by hand before deploying. Void the duplicate prescriptions, application orders and procedures, and the surplus record, keeping the one that stands. Each row shows how many prescriptions the record has, and how many application orders and procedures the consultation has. The migration does not run until no duplicates remain.

## Branched amendment chains

A record can be amended at most once, so its versions form a line. Before this version a record could be amended more than once, and an amendment could be signed by a different doctor than the original author. Migration `e6f7a8b9c0d2` enforces the line with a unique index on `amends_record_id`. It never re-links anything by itself: where a record has more than one amendment, the choice of which version the next one follows is a clinical decision. The migration therefore refuses to run while such branches exist and lists only their ids.

Run these queries against the production database before deploying:

```sql
-- 1. Branches (if there are rows, the migration fails)
SELECT tenant_id, amends_record_id, array_agg(id ORDER BY signed_at) ids, array_agg(signed_by_id ORDER BY signed_at) signers
FROM medical_records WHERE amends_record_id IS NOT NULL GROUP BY 1,2 HAVING count(*) > 1;
-- 2. Amendments made by another doctor (the migration reassigns them to the original author)
WITH RECURSIVE chain AS (SELECT id, id root_id, author_id root_author FROM medical_records WHERE amends_record_id IS NULL
  UNION ALL SELECT m.id, c.root_id, c.root_author FROM medical_records m JOIN chain c ON m.amends_record_id = c.id)
SELECT r.tenant_id, r.id, chain.root_id, chain.root_author, r.author_id, r.signed_by_id, r.signed_at
FROM medical_records r JOIN chain USING (id) WHERE r.amends_record_id IS NOT NULL AND r.author_id <> chain.root_author;
-- 3. Certificates issued by someone other than the original author (they stay valid; decide whether to void them)
WITH RECURSIVE chain AS (SELECT id, author_id root_author FROM medical_records WHERE amends_record_id IS NULL
  UNION ALL SELECT m.id, c.root_author FROM medical_records m JOIN chain c ON m.amends_record_id = c.id)
SELECT c.tenant_id, c.id, c.code, c.doctor_id, chain.root_author, c.voided_at
FROM medical_certificates c JOIN chain ON chain.id = c.record_id WHERE c.doctor_id <> chain.root_author;
```

- **Rows from query 1**: the migration will refuse to run. Resolve each branch by hand, with clinical review: re-point each later amendment at the tip of the previous one, ordered by `signed_at`, with an `UPDATE` of `amends_record_id`. Do it in a transaction and check the result, then run the query again until it returns no rows.
- **Rows from query 2**: nothing to do before deploying. The migration reassigns their `author_id`, and the signer of each version stays in `signed_by_id` and in the audit log.
- **Rows from query 3**: those certificates remain valid and the migration does not touch them. Decide with the clinic whether to void them.

## Prescriptions closed by someone else

Until this version any doctor of the clinic could complete or cancel any prescription, and cancelling needed no reason. Migration `f7a8b9c0d1e3` lets only the prescriber close one, and it moves `prescriptions.manage` to doctors. It never reassigns or reopens anything: the closures that others made stay as they are. Run these queries against the production database before deploying:

```sql
-- 1. Cancelled prescriptions that will receive the placeholder reason
SELECT tenant_id, count(*) FROM prescriptions WHERE status='cancelled' GROUP BY 1;
-- 2. Role customizations affected
SELECT tenant_id, role FROM role_permission_overrides WHERE role IN ('nurse','receptionist') AND permissions ? 'prescriptions.manage';
SELECT tenant_id, role FROM role_permission_overrides WHERE role='doctor' AND NOT permissions ? 'prescriptions.manage';
-- 3. User adjustments affected
SELECT tenant_id, id, role FROM users WHERE (role IN ('nurse','receptionist') AND (permission_adjustments->'granted' ? 'prescriptions.manage' OR permission_adjustments->'revoked' ? 'prescriptions.manage')) OR (role='doctor' AND permission_adjustments->'revoked' ? 'prescriptions.manage');
-- 4. Prescriptions closed by someone other than their prescriber (clinical review)
SELECT p.tenant_id, p.id, a.action, a.actor_id, a."timestamp" FROM prescriptions p JOIN audit_logs a ON a.tenant_id=p.tenant_id AND a.entity_type='Prescription' AND a.entity_id=p.id::text AND a.action IN ('prescription.completed','prescription.cancelled') WHERE a.actor_id <> p.prescriber_id;
-- 5. Active prescriptions that nobody can close (prescriber inactive or deleted)
SELECT p.tenant_id, count(*) FROM prescriptions p LEFT JOIN users u ON u.id=p.prescriber_id WHERE p.status='active' AND (u.id IS NULL OR u.status <> 'active') GROUP BY 1;
```

- **Query 1**: those cancellations keep the placeholder reason "Cancelación previa a la exigencia de motivo" until someone writes a real one; nothing else to do before deploying.
- **Query 2 and 3**: the migration changes these rows. Nurse and receptionist customizations lose `prescriptions.manage`, with no substitute, and doctors get it back (or lose their revocation of it). Admin rows are not touched.
- **Query 4**: the migration fills `closed_by_id` with the first closure in the audit log. Review these cases with the clinic; the migration does not reopen them.
- **Query 5**: after deploying, nobody can complete or cancel these prescriptions, and an administrator can't either. They stay active until the clinic decides how to close them (see the backlog).

## Document storage keys

Until this version the client chose each document's `storage_key`, and nothing prevented two documents from sharing one. Migration `f8a9b0c1d2e4` makes the server choose it, adds the unique index, and unlinks the documents that point to a record of another patient. No file is stored yet, so rewriting the keys moves nothing. Run these queries against the production database before deploying:

```sql
-- Documents linked to another patient's record or to a missing one (the migration unlinks them)
SELECT d.tenant_id, d.id, d.patient_id, d.record_id, r.patient_id AS record_patient_id
FROM medical_documents d LEFT JOIN medical_records r ON r.id = d.record_id AND r.tenant_id = d.tenant_id
WHERE d.record_id IS NOT NULL AND (r.id IS NULL OR r.patient_id <> d.patient_id);
-- Keys that will be rewritten
SELECT count(*) FROM medical_documents WHERE storage_key <> tenant_id::text||'/'||patient_id::text||'/'||id::text;
```

- **Rows from query 1**: nothing to do before deploying. The migration unlinks them, each document stays in its patient's file, and the record they pointed to is not touched.
- **Query 2**: a count only. The migration rewrites those keys and nothing else.

## Inconsistent appointments and procedures before OZK-106

Before this version an appointment could be cancelled, marked as no-show or rescheduled while its consultation was being signed or started, a late save could reopen a signed procedure, and two registrations could create two procedures on one appointment. OZK-106 closes those races without a migration, so there is nothing to fix for the deploy itself. The queries below only detect the cases that already exist. Run them against the production database before deploying and review each row with the clinic; none of them changes anything.

```sql
-- 1. Cancelled or no-show appointments with a consultation (and its record, if signed)
SELECT a.tenant_id, a.id, a.code, a.status, c.id AS consultation_id, c.status AS consultation_status,
       r.id AS record_id, r.code AS record_code
FROM appointments a JOIN consultations c ON c.appointment_id = a.id
LEFT JOIN medical_records r ON r.consultation_id = c.id AND r.amends_record_id IS NULL
WHERE a.status IN ('cancelled','no_show');
-- 2. Signed consultations whose appointment is not completed
SELECT c.tenant_id, c.id, a.code, a.status FROM consultations c JOIN appointments a ON a.id = c.appointment_id
WHERE c.status = 'signed' AND a.status <> 'completed';
-- 3. Appointments audited as cancelled whose status is not
SELECT a.tenant_id, a.id, a.code, a.status, l."timestamp" FROM audit_logs l JOIN appointments a ON a.id::text = l.entity_id
WHERE l.entity_type = 'Appointment' AND l.action = 'appointment.cancelled' AND a.status <> 'cancelled';
-- 4. Procedures signed more than once
SELECT tenant_id, entity_id AS procedure_id, count(*), array_agg(actor_id ORDER BY "timestamp") AS signers
FROM audit_logs WHERE action = 'procedure.signed' GROUP BY 1,2 HAVING count(*) > 1;
-- 5. Signed procedures that are no longer completed
SELECT p.tenant_id, p.id, p.status FROM procedures p
WHERE p.status <> 'completed' AND EXISTS (SELECT 1 FROM audit_logs l
  WHERE l.entity_type = 'Procedure' AND l.entity_id = p.id::text AND l.action = 'procedure.signed');
-- 6. Appointments with more than one live procedure
SELECT tenant_id, appointment_id, count(*), array_agg(id) AS procedure_ids FROM procedures
WHERE appointment_id IS NOT NULL AND status <> 'cancelled' GROUP BY 1,2 HAVING count(*) > 1;
-- 7. Signed procedures whose appointment is not completed (includes legitimate cases)
SELECT p.tenant_id, p.id, a.code, a.status FROM procedures p JOIN appointments a ON a.id = p.appointment_id
WHERE p.status = 'completed' AND a.status <> 'completed';
```

- **Query 1**: cancelled or no-show appointments that have a consultation (and a record, if it was signed). A cancellation raced a signature or a start: decide which status is right.
- **Query 2**: signed consultations whose appointment is not completed: the same race from the other side.
- **Query 3**: appointments whose audit log says cancelled but whose status is not: they changed after the cancellation.
- **Query 4**: procedures with more than one `procedure.signed` in the audit log: two signatures raced, so the performer and the notifications may be duplicated. Decide with the clinic which signature stands.
- **Query 5**: signed procedures that are no longer completed, reopened or cancelled after the signature.
- **Query 6**: appointments with more than one live procedure: a duplicate procedure, and its fee, from two registrations at once. Decide which one stands and void the other.
- **Query 7**: signed procedures whose appointment is not completed. It includes legitimate cases: a procedure signed on a cancelled or no-show appointment stays as it is, by design (see the [backlog](../docs/BACKLOG.md)). Review only the rows that are not that case.

## Signed records protection and dangling references before OZK-99

Until this version nothing in the database prevented an `UPDATE` or a `DELETE` on `medical_records`: the application never sends them, but a bad query could. Its foreign keys to patients, users, consultations, appointments and clinics were missing or cascaded, so deleting a patient or a clinic could take signed records with it. Migration `a9b0c1d2e3f5` closes both gaps, and it needs the production database clean first. Run these queries against it before deploying. They only report; nothing changes.

```sql
-- 1. Records with a broken or foreign-clinic reference
SELECT r.tenant_id, r.id, r.code,
  p.id IS NULL no_patient, p.tenant_id IS DISTINCT FROM r.tenant_id patient_tenant,
  a.id IS NULL no_author, s.id IS NULL no_signer,
  (r.consultation_id IS NOT NULL AND c.id IS NULL) no_consultation,
  (r.appointment_id IS NOT NULL AND ap.id IS NULL) no_appointment
FROM medical_records r
LEFT JOIN patients p ON p.id=r.patient_id LEFT JOIN users a ON a.id=r.author_id
LEFT JOIN users s ON s.id=r.signed_by_id LEFT JOIN consultations c ON c.id=r.consultation_id
LEFT JOIN appointments ap ON ap.id=r.appointment_id
WHERE p.id IS NULL OR a.id IS NULL OR s.id IS NULL
   OR (r.consultation_id IS NOT NULL AND c.id IS NULL) OR (r.appointment_id IS NOT NULL AND ap.id IS NULL)
   OR p.tenant_id<>r.tenant_id OR a.tenant_id<>r.tenant_id OR s.tenant_id<>r.tenant_id
   OR c.tenant_id<>r.tenant_id OR ap.tenant_id<>r.tenant_id;
-- 2. Prescriptions with a broken reference
SELECT x.tenant_id, x.id, p.id IS NULL no_patient, pr.id IS NULL no_prescriber,
  (x.closed_by_id IS NOT NULL AND cl.id IS NULL) no_closer, (x.record_id IS NOT NULL AND r.id IS NULL) no_record
FROM prescriptions x LEFT JOIN patients p ON p.id=x.patient_id LEFT JOIN users pr ON pr.id=x.prescriber_id
LEFT JOIN users cl ON cl.id=x.closed_by_id LEFT JOIN medical_records r ON r.id=x.record_id
WHERE p.id IS NULL OR pr.id IS NULL OR (x.closed_by_id IS NOT NULL AND cl.id IS NULL) OR (x.record_id IS NOT NULL AND r.id IS NULL);
-- 3. Documents with a broken reference
SELECT d.tenant_id, d.id, p.id IS NULL no_patient, u.id IS NULL no_uploader, (d.record_id IS NOT NULL AND r.id IS NULL) no_record
FROM medical_documents d LEFT JOIN patients p ON p.id=d.patient_id LEFT JOIN users u ON u.id=d.uploaded_by_id
LEFT JOIN medical_records r ON r.id=d.record_id
WHERE p.id IS NULL OR u.id IS NULL OR (d.record_id IS NOT NULL AND r.id IS NULL);
-- 4. (informative) records whose consultation belongs to another patient
SELECT r.id, r.patient_id, c.patient_id FROM medical_records r JOIN consultations c ON c.id=r.consultation_id WHERE c.patient_id<>r.patient_id;
```

- **Query 1 (records)**: a row is a record whose patient, author, signer, consultation or appointment is missing, or belongs to another clinic. The migration refuses to run and lists the ids. Never delete or edit the record. If only the parent is missing, recreate it as an inactive marker with the same `id` and clinic, without clinical data; the migration does the same when it meets that case. If the parent exists in another clinic, stop and investigate before deploying.
- **Queries 2 and 3 (prescriptions and documents)**: a row where `no_record` is the only `true` column is fine. The migration sets `record_id` to `NULL`, and the prescription or document stays with its patient. Any other `true` column makes the migration stop, as in query 1.
- **Query 4**: informative, and it doesn't block the migration. Review those records with the clinic, since the consultation and the record disagree about the patient.

### Demo reset

`python scripts/seed_demo.py --reset` deletes only the demo clinics, selected by slug, through `purge_tenants` (`infrastructure/database/tenant_purge.py`). `clinica-loida` is never in that list. Inside its own transaction, the purge disables the row triggers of `medical_records` and `prescriptions`, deletes the data of those clinics in dependency order, enables both triggers again with `ENABLE ALWAYS` and checks that they are enabled before the commit. A rollback undoes everything, the triggers included. While the purge runs, writes to those two tables wait for it in every clinic: run the reset outside opening hours.

There is no back door for the purge, on purpose. A session setting (`SET`, which any role can run), a `SECURITY DEFINER` function (a permanent object the application could also call) and `session_replication_role = replica` were discarded: the last one also turns off the foreign keys and cascades, and triggers marked `ENABLE ALWAYS` fire under it anyway. The transactional purge is the only path, and it is code that can be read.

### Writing future migrations that touch medical_records

- A migration that changes data in `medical_records` disables the trigger explicitly (`ALTER TABLE medical_records DISABLE TRIGGER trg_medical_records_append_only`), with a comment that says why, and enables it again with `ENABLE ALWAYS TRIGGER` before it ends. Never leave it disabled.
- Changing what the seal covers means a new `seal_version` with its own canonical form and backfill. Version 1 stays frozen, so existing seals keep verifying.
- The backfill of `a9b0c1d2e3f5` is the only migration that imports domain code (`record_seal`), and a golden-vector test pins its output. Don't copy that pattern: a later change to the domain would rewrite what an old migration sealed.
- A data-only restore needs `--disable-triggers` (for example `pg_restore --data-only --disable-triggers`), or the triggers reject the rows.

### Verifying after deploying

```sql
SELECT tgname, tgenabled FROM pg_trigger WHERE tgrelid IN ('medical_records'::regclass,'prescriptions'::regclass) AND NOT tgisinternal;
```

Every row must show `A` (always). `D` (disabled) or `O` (origin only) means the protection is off. Then check that the database refuses to change a signed record, inside a transaction that is rolled back (on a database that has records):

```sql
BEGIN;
UPDATE medical_records SET amendment_reason = amendment_reason WHERE id = (SELECT id FROM medical_records LIMIT 1); -- must fail: append-only
ROLLBACK;
```

There is no nightly job that recomputes the seals yet; it is in the [backlog](../docs/BACKLOG.md).
