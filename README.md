# Medicore

**English** · [Español](README.es.md)

A **multi-tenant** clinic management system built with **Clean Architecture**.

It covers the full care cycle: per-organization sign-in, a dashboard with real metrics, patient management, scheduling and appointments, the live consultation (SOAP notes) with an **ICD-10/ICD-11 diagnosis catalog**, signed and immutable medical records, medical files, per-doctor availability, insurers, user management, **granular role permissions customizable per clinic**, **in-app notifications**, **vaccination following El Salvador's national scheme**, **in-clinic medication applications**, **minor procedures**, organization settings and a **getting-started guide** for doctors and admins that ticks itself off from real data. The interface is available in **Spanish and English**, including the backend's error messages.

It also ships a **platform console (superadmin)** that sits above the multi-tenant boundary: clinic onboarding and administration, a **Business** overview (MRR, collections, expirations, adoption and seats per clinic), **Monitoring** (API and database health, server errors, failed sign-ins and lockouts, open sessions and support access), global audit, account support (password reset, unlock, suspension) and **audited impersonation** of a clinic for support.

---

## Stack

| Layer | Technology |
|---|---|
| Language | Python ≥ 3.12 |
| API | FastAPI ≥ 0.115 + Uvicorn |
| ORM | SQLAlchemy 2.0 (sync) |
| Migrations | Alembic ≥ 1.13 |
| Database | PostgreSQL (psycopg3) |
| Auth | PyJWT ≥ 2.8 + bcrypt ≥ 4 · httpOnly cookie + double-submit CSRF |
| Config validation | pydantic-settings |
| Tests / Lint | pytest ≥ 8 + ruff (in-memory adapters) |
| Frontend | React 18 + TypeScript 5 + Vite 6 |
| State / data (FE) | Zustand + TanStack Query + Axios |
| Styling (FE) | Tailwind CSS 3 + design tokens |
| Routing / i18n (FE) | React Router 6 + custom ES/EN i18n |

---

## Architecture

The backend follows strict **Clean Architecture** with four layers. The dependency rule always points inward — `domain` imports nothing external:

```
src/medicore/
├── domain/           # Business core — no framework dependencies
│   ├── enums.py
│   ├── shared/         # Domain errors (with a translatable code) + typed UUID identifiers
│   ├── value_objects/  # 10 VOs: TimeRange, DateRange, Vitals, IcdCode, Slug,
│   │                   # SoapNote, ContactInfo, BloodType, Money, UserPreferences
│   ├── entities/       # 22 aggregates: Appointment (FSM), Consultation, MedicalRecord,
│   │                   # Prescription, Patient, User, Tenant, Insurer, MedicalDocument,
│   │                   # Availability, Notification, AuditLog, AuthSession,
│   │                   # CatalogDiagnosis, RolePermissionOverride, PlatformAdmin,
│   │                   # PlatformAuditLog, VaccinationRecord, ApplicationOrder,
│   │                   # ApplicationRecord, ProcedureType, Procedure
│   ├── services/       # slot_resolver (availability), immunization (scheme), allergies,
│   │                   # procedure_catalog (default catalog)
│   └── repositories/   # Interfaces (ports): 20 repository Protocols
│
├── application/      # Use cases (interactors) + infrastructure ports
│   ├── ports/          # 5 ports: Clock, CodeGenerator, PasswordHasher,
│   │                   # TokenIssuer, UnitOfWork
│   ├── common/         # ActorContext, app errors, permission catalog, auditing,
│   │                   # login lockout, notification emission, timezone
│   └── use_cases/      # 20 groups: auth, sessions, patients, appointments,
│                       # consultations, records, prescriptions, availability, users,
│                       # organization, insurers, diagnoses, audit, role_permissions,
│                       # notifications, dashboard, vaccinations, applications,
│                       # procedures, platform
│
├── infrastructure/   # Concrete implementations
│   ├── config.py       # Settings from .env (pydantic-settings) — dev-safe defaults
│   ├── database/       # SQLAlchemy engine + session factory
│   ├── persistence/
│   │   ├── models/     # ORM models (31 tables; complex VOs as JSONB)
│   │   ├── mappers/    # ORM ↔ domain entity (keeps the domain clean)
│   │   └── repositories/  # SQLAlchemy implementations of the ports
│   └── auth/           # JwtTokenIssuer, BcryptPasswordHasher, code generator, SystemClock
│
└── presentation/
    ├── app.py           # Factory: builds FastAPI + CORS + security headers + error handlers + routers
    ├── main.py          # Entry point (uvicorn medicore.presentation.main:app)
    ├── dependencies.py  # DI: get_actor / get_platform_actor (cookie or Bearer → Context,
    │                    # revocable session, CSRF), get_uow, get_codes, get_clock
    ├── cookies.py       # httpOnly session cookies + CSRF token
    ├── client_ip.py     # Real client IP (X-Forwarded-For only from trusted proxies)
    ├── serializers.py   # domain entity → dict (without touching the domain)
    ├── errors.py        # ApiError: HTTPException with a translatable code
    ├── error_handlers.py# Errors → {"detail", "code", "params"} with their HTTP status
    ├── schemas/         # Pydantic request + response models per resource
    └── routers/         # 19 routers, 130 endpoints under /api/v1/
```

### Multi-tenancy
Every business entity carries a `tenant_id`. The filter is applied **in every repository**, not by the caller — isolation is enforced structurally. The `UnitOfWork` is tenant-scoped: `factory.for_tenant(tenant_id)`. Global operations (slug resolution, superadmin) use an unscoped `UnitOfWork` or read-only helpers.

### Platform (superadmin)
A separate session (`platform`-scoped token) that operates above the multi-tenant boundary: clinic creation/editing (including the timezone and sites), each clinic's **subscription** (plan, modules, paid period, special terms, payments), status changes (active / suspended / archived), global stats and audit, account support (password reset, unlock, user suspension) and **impersonation**. Impersonation issues a tenant token marked with `impersonated_by` and a shorter TTL, so every write made during support is audited.

### Critical business rules
- Appointments only within the doctor's availability, with no overlaps, honoring the booking rules.
- A signed `MedicalRecord` is **immutable**; corrections are **versioned amendments** (`status=amended` referencing the original).
- `SignConsultation` is **atomic**: record + prescriptions + appointment `completed` in a single transaction.
- Consultation diagnoses are limited to the catalog of the **ICD version configured per clinic** (ICD-10 / ICD-11), with autocomplete.
- **Vaccination** following El Salvador's national scheme (MINSAL), for children, adolescents and adults: each patient's card computes every dose's status (given, due, overdue, upcoming…) from their age and records; records are never edited, a wrong one is voided with a reason. A worklist shows overdue and upcoming doses across the clinic.
- **In-clinic applications** (injections, IV fluids, nebulizations…): the doctor indicates them in the consultation and they become orders for nursing when it is signed; walk-ins with an outside prescription record the prescribing doctor and their JVPM number. Each dose is recorded with lot, site and vitals, never edited (a wrong one is voided with a reason), and opens an observation window (30 min by default, configurable per order) closed as "no reaction" or as an adverse reaction, which notifies the ordering doctor. Applying a drug that clashes with the patient's allergies requires a written, audited justification.
- **Minor procedures** (sutures, biopsies, wound care, IUD insertion, ECG…): each clinic has a configurable catalog, preloaded with the most common procedures, that says who may perform each one (doctor only, or doctor or nurse), whether it needs informed consent, whether it usually takes a pathology specimen and the suggested follow-up. A procedure is ordered in the consultation (pending when it is signed) or registered directly, optionally tied to a procedure appointment. Before performing it: allergy review, anticoagulants, fasting and vitals; consent signed on paper is recorded with who signed and a witness (no file). The note (anesthesia, technique, findings, materials, complications, home instructions, specimen sent to pathology) is immutable once signed — corrections are amendments — and signing suggests a follow-up date and notifies the ordering doctor when someone else performed it.
- **Granular permissions** enforced in the application layer (not just the UI) — see the next section.
- Temporary password with a forced change on first sign-in.
- **Password policy** (`domain/services/password_policy.py`, NIST SP 800-63B style) wherever a password is set — invite, reset (clinic or console), change, clinic creation, superadmin script: at least 10 characters (at most 72 bytes, bcrypt's limit), letters plus a number or symbol, not a common password, nothing from the person's name, email or clinic, and different from the current one. No periodic expiry; brute force is covered by the login lockout. The UI shows the requirements live and generates temporary passwords that always comply.
- Auditing of access and sensitive changes (HIPAA/GDPR), per tenant and global.

---

## Permissions

Access control is **granular and customizable per clinic** (`application/common/permissions.py`):

- **Catalog of 31 permissions** (`Permission`, `StrEnum`) grouped by resource: `patients.*`, `appointments.*`, `availability.manage`, `consultations.*`, `records.*` (including `sign` and `amend`), `prescriptions.manage`, `diagnoses.view`, `insurers.*`, `users.*`, `organization.*`, `locations.manage`, `audit.view`, `permissions.manage`, `vaccinations.*`, `applications.*`, `procedures.*`.
- **4 roles** — `admin`, `doctor`, `nurse`, `receptionist` — each with a default permission set in `ROLE_PERMISSIONS`.
- **Per-tenant overrides**: each clinic can customize a role's set through a `RolePermissionOverride` row. `effective_permissions(role, stored)` resolves defaults vs. override (and intersects with the current catalog to tolerate retired permissions).
- On every request, the presentation layer puts the effective permissions in `ActorContext.permissions`, so every `ensure_permission(...)` check honors the clinic's customization.
- **Per-user exceptions** (plans with the `user_permissions` feature, Clínica and up): one person can get a few extra permissions or lose a few of their role's, stored as the difference from the role (`PermissionAdjustments` on `User`), so later changes to the role still reach them. Edited from **Users → Permissions** (`GET`/`PUT /users/{id}/permissions`). On a plan without the feature, stored exceptions are kept but not applied.
- **Contracted modules gate their permissions**: a clinic without vaccination, applications or procedures gets none of their permissions, whatever its roles say.
- `granted(role, stored, modules, adjustments)` combines all of the above; the presentation layer puts the result in `ActorContext.permissions`.
- The frontend uses the same model: the UI adapts to the actor's effective permissions, and the **Roles & Permissions** screen edits the overrides (`role_permissions` router: `GET`/`PUT`/`DELETE`).

**Guardrails** (enforced in the backend, mirrored in the UI):

- The `admin` role is not customizable and always has full access (except signing/amending records).
- `records.sign` and `records.amend` are doctor-only: never granted to other roles or users, never taken from doctors.
- `permissions.manage` is admin-only: it can't be delegated to a role or a user.
- Only an admin acts on admin accounts (edit, change role, suspend, reset password, close sessions) or makes someone an admin. A delegated `users.manage` manages the rest of the staff.
- Nobody edits their own permissions.

**What the clinic manages and what Medicore support manages:**

| | Clinic admin | Platform console |
|---|---|---|
| Legal name, tax ID, ICD version | ✅ (`organization.manage`) | ✅ |
| Sites (create, rename) | ✅ within the plan's limit (`locations.manage`) | ✅ same limit |
| Timezone | read-only | ✅ (it moves the clinic's "today", agenda and reminders) |
| Slug (sign-in identifier) | read-only | fixed at creation |
| Plan, modules, limits, paid period, payments | read-only | ✅ |
| Users, roles, per-user permissions | ✅ (within seat limits) | support actions (reset password, unlock, suspend) |

---

## Subscriptions and plans

Each clinic has a **subscription** (`Subscription` value object on `Tenant`): plan, optional modules, paid-until date, trial flag, grace days and special terms (limit overrides, negotiated price). Activation is manual — clinics pay by bank transfer and support records it from the platform console.

- **Plan catalog** (`plans`, editable in **Plans & pricing**): Profesional independiente, Clínica, Clínica Plus and Empresarial (custom quote). Each sets limits for doctors, support staff (nursing, reception and admins beyond the first), sites and storage, plus features (`user_permissions`).
- **Optional modules** (`addon_pricing`): vaccination, applications and procedures, each with a monthly price and a bundle price for all three.
- **Quotas** are enforced in the use cases (invite, role change, reactivation, new site): growing above a limit is refused with `plan.quota_*`; a clinic already above it (after a downgrade) keeps what it has.
- **Payments and renewal** (`subscription_payments`): recording a payment extends the paid period by 1–24 months. After the period ends the clinic keeps working for the grace days; then it becomes **read-only** (`plan.read_only`: it can view but not change data until renewed). The app shows banners as expiry approaches.
- Clinics see their plan, usage and payment history in **Settings → Organization**.

The public demo shows two plans: `clinica-demo` on **Clínica Plus** with every module, and `centro-norte` on **Clínica** with vaccination only (3 doctors, support seats full), so locked modules and quota messages can be tried too.

---

## Security

- **Sessions in an httpOnly cookie** (SameSite=Lax, `Secure` in production) with **double-submit CSRF** (`mc_csrf` + `X-CSRF-Token` header); the token is never reachable from JavaScript. `Authorization: Bearer` is still accepted for API clients.
- **Revocable sessions** (`sessions` table + `sid` claim): real logout; changing the password ends the other sessions; suspending or resetting a user ends all of them.
- **Login lockout** with exponential backoff (5 failures → 1 min, doubling up to 15) and a 429 response with `Retry-After`.
- **No enumeration**: constant-time login; an unknown slug or email answers exactly like a wrong password.
- `X-Forwarded-For` is only honored from the proxies listed in `TRUSTED_PROXIES`.
- Security headers on the API and a strict CSP in the frontend build.

Pending findings are tracked in [`docs/BACKLOG.md`](docs/BACKLOG.md).

---

## Notifications and dashboard

- **In-app notifications**: appointments created, rescheduled, cancelled or marked as no-show (to the doctor), record amendments (to the original author), uploaded documents (to the treating doctor) and new users or role changes (to administrators). A bell in the top bar with an unread counter (polled every 60 s), an unread-only filter and deep links to the item, plus a full **inbox page** (`/notifications`) filterable by status and category and grouped by day. Kept for 90 days.
- **Dashboard with real data** (`GET /dashboard/summary`): today's appointments, pending ones, registered patients and schedule occupancy, each compared with the previous week, plus the next pending appointments from now on (`GET /appointments/upcoming`). Doctors see their own schedule; other roles see the whole clinic.

---

## API errors

Every error response has the same shape:

```json
{"detail": "user with email x@y.test already exists", "code": "user.email_taken", "params": {"email": "x@y.test"}}
```

`code` is stable and the frontend translates it (`err.<code>` keys in `frontend/src/lib/i18n.ts`), interpolating `params`; `detail` is English text for API clients and logs. A test fails if the backend emits a code without a translation in both languages. Details in [`backend/README.md`](backend/README.md#error-format).

---

## Monorepo layout

```
medicore/
├── README.md                 # This file
├── README.es.md              # Spanish version
├── LICENSE
├── docs/
│   └── BACKLOG(.es).md       # Deferred work, pending findings and future plans
├── backend/
│   ├── .env.example          # Environment variable template (no secrets)
│   ├── .env                  # Real values — gitignored, never commit
│   ├── Dockerfile            # Production image (non-root user, uvicorn :8000)
│   ├── alembic.ini           # Alembic config (URL injected from .env)
│   ├── migrations/           # 14 Alembic migrations
│   ├── scripts/
│   │   ├── seed_demo.py            # Demo data: ~8 weeks of history + 4 of agenda, via the use cases
│   │   ├── import_icd.py           # Loads the ICD-10/ICD-11 catalog
│   │   └── create_platform_admin.py # Creates a platform superadmin
│   ├── pyproject.toml        # Metadata + deps + pytest/ruff config
│   ├── src/medicore/         # Source code (see Architecture above)
│   └── tests/
│       ├── domain/           # Domain tests (VOs, FSM, slot_resolver…)
│       ├── application/      # Use-case tests with in-memory repos
│       ├── presentation/     # HTTP endpoint tests (TestClient)
│       ├── infrastructure/   # Tests against real PostgreSQL (skipped without a DB)
│       └── support/          # InMemoryStore, repos, UoW, fakes, builders
└── frontend/                 # React + TS + Vite SPA
    └── src/
        ├── api/              # Axios client (cookies, CSRF, error translation)
        │                     # + 19 per-resource modules
        ├── stores/           # Zustand: auth + platformAuth + ui (theme/language/sidebar)
        ├── lib/              # ES/EN i18n, formatting, QueryClient, notifications, timezones…
        ├── types/            # TS types mirroring the backend domain
        ├── components/       # ui/ + shell/ (top bar, notification bell…)
        │                     # + appointments/ + audit/ + patients/ + permissions/
        │                     # + records/ + settings/ + vaccination/ + applications/
        │                     # + procedures/
        │                     # + guards (RequireAuth…)
        └── pages/            # 20 clinic screens (Login, Dashboard, Patients,
                              # PatientDetail, Appointments, Schedule, Consultation,
                              # Records, Availability, Insurers, Users, Settings,
                              # Audit, Permissions, Notifications, ChangePassword,
                              # Vaccination, Applications, Procedures,
                              # ProcedureDetail)
                              # + platform/ (5 superadmin screens)
```

---

## Project status

| Phase | Scope | Status |
|---|---|---|
| **1** | Complete domain | ✅ Done |
| **2** | Use cases (interactors) + in-memory repos | ✅ Done |
| **3** | SQLAlchemy, Alembic, JWT, bcrypt, multi-tenancy | ✅ Done |
| **4** | FastAPI API under `/api/v1/` | ✅ Done |
| **5** | React frontend — every clinic screen | ✅ Done |
| **6** | Superadmin platform, ICD catalog and insurers | ✅ Done |
| **7** | Granular permissions with per-tenant overrides + permission-driven UI | ✅ Done |
| **8** | Production hardening (dev-safe defaults) + Dockerfile | ✅ Done |
| **9** | Security: cookie sessions + CSRF, revocable sessions, login lockout, anti-enumeration | ✅ Done |
| **10** | In-app notifications (backend, bell and inbox) | ✅ Done |
| **11** | Real dashboard metrics, fully ES/EN interface and translatable API errors | ✅ Done |
| **12** | Vaccination module (El Salvador national scheme, patient card, worklist) | ✅ Done |
| **13** | In-clinic applications (orders from the consultation or an outside prescription, observation, allergy alert) | ✅ Done |
| **14** | Minor procedures (per-clinic catalog, consent on paper, signed note with amendments, pathology specimen, follow-up) | ✅ Done |
| **15** | SaaS subscriptions (plan catalog, optional modules, quotas, manual payments and renewal, read-only after grace, per-user permissions) | ✅ Done |
| **16** | Password policy (length, blocklist, nothing personal, live requirements in the UI) | ✅ Done |
| **17** | Platform console: Business (MRR, collections, expirations, adoption, seats) and Monitoring (health, 500 errors without patient data, sign-ins, open support access, `/health/ready`) | ✅ Done |
| — | Email/SMS notifications and appointment reminders | 🗓️ Future |
| — | Vaccine lot inventory and vaccination reminders | 🗓️ Future |
| — | Applications: frequent-drug catalog, printable record, inventory and billing | 🗓️ Future |
| — | Procedures: pathology result tracking, printable note, rooms/equipment, inventory and billing | 🗓️ Future |

---

## Setup and development

### Requirements
- Python 3.12+
- PostgreSQL (with a `medicore` database created)
- Node.js (for the frontend)

### Backend

```bash
cd backend

# 1. Environment and install (includes dev dependencies)
python -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 2. Configure environment variables
cp .env.example .env
#   DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/medicore
#   JWT_SECRET=$(openssl rand -hex 32)

# 3. Create the tables
.venv/bin/alembic upgrade head

# 4. (Optional) ICD-10/ICD-11 catalog and demo data
.venv/bin/python scripts/import_icd.py
.venv/bin/python scripts/seed_demo.py        # idempotent (--reset recreates)

# 5. Start the API
.venv/bin/uvicorn medicore.presentation.main:app --reload
# API at http://localhost:8000/api/v1/ · docs at /api/v1/docs · health at /health (liveness) and /health/ready (database)
```

The seed replays ~8 weeks of clinic activity and the next 4 weeks of agenda relative to the day it runs (re-run it with `--reset` to refresh the dates). Demo users get the password from `DEMO_PASSWORD` (**`demo1234`** in development when it isn't set) and the clinic admins the one from `DEMO_ADMIN_PASSWORD` (the same `DEMO_PASSWORD` when unset); in production both are required and must differ. See
[`backend/README.md`](backend/README.md) for details.

### Frontend

```bash
cd frontend
npm install            # first time
npm run dev            # http://localhost:3000 (proxies /api → :8000)
npm run lint           # eslint
npm run build          # type-check (tsc -b) + production build → dist/
```

`VITE_*` variables and deployment are covered in [`frontend/README.md`](frontend/README.md).

### Common commands

```bash
# Backend
.venv/bin/pytest                          # full suite (581 tests)
.venv/bin/pytest tests/domain/            # domain tests only
.venv/bin/ruff check src tests            # lint (--fix to autofix)

# Migrations
.venv/bin/alembic upgrade head            # apply pending migrations
.venv/bin/alembic revision --autogenerate -m "description"  # new migration
```

---

## Database

**31 tables**, created by the initial migration (`a622afdfaa21`) and extended by later migrations:

| Table | Description |
|---|---|
| `tenants` + `locations` | Organization / clinic and its sites |
| `users` + `doctor_profiles` | User accounts and clinical profile |
| `sessions` | Active (revocable) clinic, support and platform sessions |
| `login_attempts` | Failed-login counter for the lockout |
| `patients` | Patients (demographics, assigned doctor, tags, allergies) |
| `appointments` | Appointments with a status FSM |
| `consultations` | Consultation in progress (mutable draft) |
| `medical_records` | Signed, immutable medical records |
| `prescriptions` | Issued prescriptions |
| `medical_documents` | Medical files (metadata) |
| `insurers` | The clinic's insurers |
| `doctor_availability` + `availability_exceptions` | Working hours + exceptions |
| `notifications` | In-app notifications (JSONB payload) |
| `audit_logs` | Per-tenant HIPAA/GDPR audit trail |
| `tenant_counters` | Counters for human-readable codes (`P-00142`, `A-2401`…) |
| `vaccination_records` | Vaccine doses recorded (national scheme) |
| `application_orders` + `application_records` | In-clinic application orders and the doses applied |
| `procedure_types` + `procedures` | Per-clinic procedure catalog and the procedures ordered/performed |
| `role_permission_overrides` | Per-role, per-tenant permission customization |
| `plans` + `addon_pricing` | Plan catalog and optional-module pricing (global) |
| `subscription_payments` | Payments recorded per clinic (renewals) |
| `diagnosis_codes` | ICD-10/ICD-11 catalog (global, for autocomplete) |
| `platform_admins` | Platform superadmins |
| `platform_audit_logs` | Global audit of platform operations |
| `error_events` | Unexpected server errors (route, type and location; no patient data; 30 days) |

---

## Tests

Almost the entire suite is **database-independent** — it uses in-memory adapters that honor the same multi-tenant contract as the SQLAlchemy repos. Infrastructure tests run against **real PostgreSQL** inside a transaction that is always rolled back, and are skipped when no database is available.

```
581 passing tests
   120  — domain (VOs, FSM, slot_resolver, Consultation.sign, MedicalRecord.amend,
            immunization schedule, applications, procedures, allergy matching)
   240  — application (auth, sessions, appointments, consultations, records, notifications,
            dashboard, platform, granular permissions, multi-tenant isolation)
   171  — presentation (HTTP endpoints: auth guards, CSRF, booking, lifecycle, 403 per
            permission, error codes, validation, platform)
    50  — infrastructure (SQLAlchemy repositories against PostgreSQL)
```

Among other things, the tests verify:
- `SignConsultation` atomicity: a failure rolls back the record, prescriptions and appointment status.
- Multi-tenant isolation: one tenant's repos never leak another tenant's data.
- Effective permissions per role and per-tenant override, plus platform scope.
- Login lockout, session revocation and CSRF protection.
- That every backend error code has a Spanish and an English translation.

---

## Environment variables (backend)

| Variable | Description | Default |
|---|---|---|
| `ENVIRONMENT` | `development` or `production`. Production enables strict validation. | `development` |
| `DATABASE_URL` | PostgreSQL connection URL (psycopg3) | `postgresql+psycopg://localhost/medicore` |
| `JWT_SECRET` | HMAC key for tokens. **Required and strong in production** (`openssl rand -hex 32`) | `change-me` (dev only) |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `JWT_EXPIRE_MINUTES` | Token lifetime in minutes | `1440` (24 h) |
| `JWT_SUPPORT_EXPIRE_MINUTES` | Lifetime (min) of impersonation/support sessions — shorter for safety | `60` (1 h) |
| `CORS_ORIGINS` | Allowed origins (comma-separated); `*` only in development | `*` |
| `ENABLE_DOCS` | Expose Swagger/OpenAPI at `/api/v1/docs` | `true` (dev) / `false` (prod) |
| `TRUSTED_PROXIES` | IPs/CIDRs of reverse proxies whose `X-Forwarded-For` is honored; empty → socket IP | empty |
| `SOURCE_COMMIT` | Deployed commit, shown on the Monitoring page | empty |
| `DEMO_PASSWORD` | Password for the demo users created by `scripts/seed_demo.py` (≥ 8 chars). **Required in production**, where the public default is rejected | `demo1234` (dev only) |
| `DEMO_ADMIN_PASSWORD` | Password for the demo clinic admins (≥ 8 chars), kept private so the shared demo password doesn't open the administration. **Required in production** and different from `DEMO_PASSWORD` | `DEMO_PASSWORD` |

> In **production** (`ENVIRONMENT=production`) the app **refuses to start** if `JWT_SECRET` is still the insecure default or too short, or if `CORS_ORIGINS` is `*`; API docs are also disabled unless `ENABLE_DOCS=true` is set explicitly. Nothing is validated in development and the defaults work as-is.

---

## Deployment

The backend ships a production-ready `Dockerfile` (non-root user, uvicorn on port 8000). The frontend is served as static files (`dist/`) on the same origin behind a reverse proxy, or from a separate host with `VITE_API_BASE_URL` set at build time. Step-by-step instructions in [`backend/README.md`](backend/README.md) and [`frontend/README.md`](frontend/README.md).

### Deployment with Docker Compose / Coolify

The root [`docker-compose.yml`](docker-compose.yml) runs the whole stack on a **single origin**: `db` (PostgreSQL 16, persistent volume), `backend` (applies `alembic upgrade head` on start) and `frontend` (nginx serving the SPA, proxying `/api/` to the backend and adding the security headers). Only `frontend` gets a public domain; TLS is terminated by the edge proxy (Traefik in Coolify).

1. Generate the secrets: `openssl rand -hex 32` (`JWT_SECRET`) and `openssl rand -base64 24` (`POSTGRES_PASSWORD`), and choose `DEMO_PASSWORD` (shared with whoever tries the demo) and `DEMO_ADMIN_PASSWORD` (private, for the clinic admins).
2. In Coolify: **New Resource → Public Repository** → this repo, branch `main`, **Build Pack: Docker Compose**, compose file `/docker-compose.yml`.
3. Environment variables: `POSTGRES_PASSWORD`, `JWT_SECRET`, `APP_ORIGIN` (e.g. `https://medicore.example.com`), `DEMO_PASSWORD` and `DEMO_ADMIN_PASSWORD`. Optional: `POSTGRES_DB`, `POSTGRES_USER`, `ENABLE_DOCS`, `JWT_EXPIRE_MINUTES`, `WEB_CONCURRENCY` (uvicorn workers, default 2). If a required one is missing the stack doesn't start, on purpose.
4. Assign the domain to the **frontend** service only, then **Deploy**.
5. One-time data load, in a terminal of the `backend` container:
   ```sh
   python scripts/import_icd.py cie11 data/cie11.csv
   python scripts/import_icd.py cie10 data/cie10.csv
   python scripts/seed_demo.py            # --reset to refresh the demo dates
   python scripts/create_platform_admin.py <email> "<name>" '<password>'
   ```

Redeploys keep the data (volume `medicore-pgdata`) and apply new migrations on start.

For a public demo, add a nightly **Scheduled Task** in Coolify on the `backend` container running `python scripts/seed_demo.py --reset` (e.g. `0 9 * * *`, 03:00 in El Salvador): it undoes whatever visitors changed, keeps the data from piling up and moves the dates to the current day. The ICD catalog and the platform admins are not touched.

**Monitoring.** The console's *Monitoring* page only loads while the API answers, so to hear about an outage point an external monitor (UptimeRobot, Better Stack…) at `https://<your-domain>/api/v1/health/ready`: it answers `200` when the API and the database are fine and `503` when the database does not respond. The deployed commit on that page comes from `SOURCE_COMMIT`, which Coolify injects into the container. Do not declare it in the compose file: Coolify locks compose variables and an empty one would shadow its own. Outside Coolify, set it yourself; if it is missing, the page says so.

---

## Backlog and future plans

Deferred work, pending security findings and planned future features (email/SMS notifications, appointment reminders) are listed in [`docs/BACKLOG.md`](docs/BACKLOG.md).
