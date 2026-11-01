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

By the numbers: **17 entities** and **10 value objects** in the domain, **17 repositories
(Protocols)**, **5 application ports** (Clock, CodeGenerator, PasswordHasher, TokenIssuer,
UnitOfWork), **17 use-case groups** and **16 routers / 99 endpoints** under `/api/v1/`.

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
  **amendment** (a new record with `status=amended` that references the original).

## Features

- **Authentication** with JWT and roles (`admin`, `doctor`, `nurse`, `receptionist`), with a
  forced password change on first sign-in. The session travels in an **httpOnly cookie**
  (`mc_session` / `mc_platform`, SameSite=Lax, Secure in production) with **double-submit
  CSRF** (`mc_csrf` cookie + `X-CSRF-Token` header on mutations); the
  `Authorization: Bearer` header is accepted as an alternative for API clients.
- **Server-side revocable sessions**: every login creates a row in `sessions` referenced by
  the JWT's `sid` claim and validated on every request. Logout really revokes, changing the
  password revokes the user's other sessions, and suspending an account or resetting its
  password ends all its sessions immediately. **Active sessions** view: each user sees and
  ends their own (Settings), an admin those of any user in their clinic, and the superadmin
  those of a whole clinic (third-party revocations audited as `session.revoked`).
- **Login lockout**: failed-attempt counter per `(organization, email)` with a temporary
  lock and exponential backoff (HTTP 429 + `Retry-After`); it also counts non-existent
  accounts so it doesn't reveal which ones exist.
- **Granular permissions** (`application/common/permissions.py`): a catalog of **23
  permissions** (`Permission`, `StrEnum`), a default set per role (`ROLE_PERMISSIONS`) and
  **per-tenant overrides** via `RolePermissionOverride`. `effective_permissions(role, stored)`
  resolves defaults vs. override and intersects with the current catalog; the presentation
  layer puts them in `ActorContext.permissions`, so every `ensure_permission(...)` honors the
  clinic's customization. The `role_permissions` router (`GET`/`PUT`/`DELETE`) manages them.
- **Scheduling**: per-doctor availability, slot resolution, appointment lifecycle
  (scheduled → confirmed → in progress → completed).
- **Consultation → record**: signing a consultation issues an immutable `MedicalRecord` plus
  the prescriptions and completes the appointment, all in one transaction.
- **In-app notifications** (`application/common/notifications.py`): use cases emit them inside
  their own transaction — they are saved together with the action or not at all — and never
  to the author themselves. Events: appointment created/rescheduled/cancelled/no-show (to the
  appointment's doctor), record amended (to the original author), document uploaded (to the
  patient's assigned doctor or, if none, the doctor of their last completed appointment) and
  user created/role changed (to active admins). Only `type` + `data` are stored (ids and
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
  readable `subject` in its metadata for a useful detail column.
- **Platform console** (superadmin): clinic onboarding/management, global stats, consolidated
  audit and **support sessions** (impersonation with a short TTL and a trail).

## Configuration

Copy `.env.example` to `.env` and adjust the values:

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | `development` or `production`. Production enables strict validation. | `development` |
| `DATABASE_URL` | PostgreSQL connection string (psycopg3) | `postgresql+psycopg://localhost/medicore` |
| `JWT_SECRET` | Secret used to sign tokens. **Required and strong in production** (`openssl rand -hex 32`). | `change-me` (dev only) |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `JWT_EXPIRE_MINUTES` | Token lifetime | `1440` (24 h) |
| `JWT_SUPPORT_EXPIRE_MINUTES` | Lifetime of support/impersonation sessions | `60` (1 h) |
| `CORS_ORIGINS` | Allowed origins (comma-separated); `*` only in development | `*` |
| `ENABLE_DOCS` | Expose Swagger/OpenAPI at `/api/v1/docs` | `true` (dev) / `false` (prod, unless explicitly enabled) |
| `TRUSTED_PROXIES` | IPs/CIDRs (comma-separated) of the reverse proxies whose `X-Forwarded-For` header is honored (e.g. `127.0.0.1` or `10.0.0.0/8`). Empty → the header is ignored and the socket IP is recorded. An invalid value prevents startup. | empty |

> In **production** (`ENVIRONMENT=production`) the app **refuses to start** if `JWT_SECRET` is
> still the insecure default or too short, or if `CORS_ORIGINS` is `*`. API docs are also
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

# 4) Demo data: 2 clinics with ~8 weeks of history and 4 weeks of agenda, generated by
#    running the real use cases with a simulated clock (audit + notifications included)
.venv/bin/python scripts/seed_demo.py            # idempotent
.venv/bin/python scripts/seed_demo.py --reset    # deletes the demo tenants and recreates them

# 5) (optional) Create a platform superadmin
.venv/bin/python scripts/create_platform_admin.py

# 6) Start the API
.venv/bin/uvicorn medicore.presentation.main:app --reload
```

- API at `http://localhost:8000/api/v1`, interactive docs at `/api/v1/docs`, health check at
  `/health`.
- After running the seed, every demo user has the password **`demo1234`**.

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

## Tests and linting

A suite of **496 tests** (89 domain · 205 application · 158 presentation · 44 infrastructure),
almost entirely database-independent thanks to in-memory adapters that honor the same
multi-tenant contract as the SQLAlchemy repos.

The integration tests against real PostgreSQL (`tests/infrastructure/test_audit_repository_sql.py`,
`test_diagnosis_catalog_sql.py` — ranking and trigram search for the diagnosis autocomplete —
`test_login_throttle_sql.py` — atomic UPSERT of the login lockout — and
`test_notification_repository_sql.py` — JSONB and bulk UPDATE/DELETE of the inbox) use
`TEST_DATABASE_URL` (or the configured `DATABASE_URL`), run inside a transaction that is always
rolled back — they leave no trace in the development database — and are **skipped
automatically** when PostgreSQL isn't reachable.

```bash
.venv/bin/pytest
.venv/bin/ruff check src tests
```

## Deployment

Production-ready Docker image (`Dockerfile` in this folder; non-root user, starts uvicorn on
port 8000):

```bash
# Build
docker build -t medicore-backend .

# Migrations (a separate step, before starting the app)
docker run --rm --env-file .env medicore-backend alembic upgrade head

# Start the API
docker run -d -p 8000:8000 --env-file .env medicore-backend
```

Production checklist (via environment variables, see the **Configuration** table):

- `ENVIRONMENT=production`
- A strong `JWT_SECRET` (`openssl rand -hex 32`) — the app won't start if it's insecure.
- `DATABASE_URL` pointing to the real database.
- `CORS_ORIGINS` with the frontend's origins (not `*`).
- `TRUSTED_PROXIES` with the reverse proxy's IP (e.g. `127.0.0.1` if nginx runs on the same
  host) so the audit trail records the real client IP.
- Optional: `ENABLE_DOCS=false` to hide Swagger/OpenAPI.

> For multiple workers: `uvicorn ... --workers N` (overriding the `CMD`) or a process manager.
> The app is served behind a reverse proxy that terminates TLS and forwards `X-Forwarded-For`.
> The header is **only honored** if the connection comes from a proxy listed in
> `TRUSTED_PROXIES` (walking the chain right to left and discarding trusted hops); otherwise
> the socket IP is recorded. The image starts uvicorn with `--no-proxy-headers` so the app is
> the only one interpreting the header — keep it that way if you override the `CMD`.
