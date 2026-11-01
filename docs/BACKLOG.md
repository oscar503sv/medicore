# Backlog — deferred work and pending findings

**English** · [Español](BACKLOG.es.md)

An inventory of partially implemented functionality and of security findings that were
**documented but deliberately not addressed yet** (June 2026 audit). When picking one up, check
that the references are still accurate.

## Incomplete functionality (the backend has more than is used)

### Notification system
Complete in-app notifications: emitted from appointments, amendments, documents and user
management; `/notifications` router; a bell in the top bar with an unread counter (polled every
60 s) and a dropdown with deep links (`/appointments?date=`, `/patients/:id?tab=…&record=…`);
full inbox page at `/notifications` (filters by status and category, grouped by day).
External channels and reminders are planned as a future evolution (see [Future](#future)).

### Other loose ends
- The `AttachDocument` use case (`application/use_cases/consultations.py`) has no endpoint:
  attaching documents to a consultation in progress isn't reachable through the API.
- The `Money` value object (`domain/value_objects/money.py`) is unused — presumably reserved
  for billing.
- Medical document storage keeps **metadata only** (name, mime type, size, `storage_key`);
  there is no file backend (S3/disk). The UI says so explicitly.

## Future

Functionality planned for a later stage of the product, with no set date.

### Notifications through external channels
Notify people outside the app too (today only the in-app bell and inbox exist). The groundwork is in
place: per-user, per-topic preferences (`appointments`, `reminders`, `lab_results`,
`internal_messages`, `weekly_reports`) with an `email | push | sms | none` channel are stored
(`domain/value_objects/user_preferences.py`), but nothing reads them: there is no endpoint, no
preferences screen and no delivery provider.

Requires: a delivery port + adapter (SMTP or a service such as SendGrid/Twilio), honoring the
preferences when emitting each notification, a preferences screen in the profile, and
background delivery so requests aren't blocked.

### Appointment reminders
Time-triggered notices: a reminder to the patient (e.g. 24 h before) to reduce no-shows and,
optionally, a daily schedule summary for the doctor. Requires an idempotent scheduled process
(cron/worker) that finds upcoming appointments without sending duplicates; it uses the contact
details from the patient's file. Depends on the external channels: patients don't use the app.

Suggested order: (1) email, the simplest and cheapest channel; (2) appointment reminders to
patients by email; (3) SMS/WhatsApp, with a per-message cost and an external provider.

### Vaccination — next phases
Phase 1 (national scheme, patient card, recording/voiding and the worklist) is done. Next:

- **Phase 2 — clinical depth:** an official printable vaccination card (PDF); catch-up schemes
  with minimum intervals between doses (today only the recommended age and catch-up limit
  are modelled); risk-group indications driven by the patient's conditions/tags; a doctor's
  order ("indicate this vaccine") that the nurse then administers; and a periodic review of
  the scheme data against the MINSAL guidelines in force.
- **Phase 3 — inventory and reminders:** vaccine **lot inventory** (stock in, expiry dates,
  automatic decrement when a dose is recorded, low-stock and expiry alerts, cold-chain log)
  and **reminders** to families for upcoming/overdue doses. Reminders depend on the external
  channels above.

### Applications — next phases
Phase 1 (orders from the consultation or an outside prescription, dose recording and voiding,
observation window, allergy alert, nursing worklist) is done. Next:

- **Phase 2 — speed and documents:** a catalog of the clinic's frequent drugs (drug, dose and
  route prefilled); duration tracking for IV fluids and nebulizations (start/end, rate); and a
  printable application record for the patient.
- **Phase 3 — inventory and billing:** stock of medicines and supplies shared with the vaccine
  lot inventory (automatic decrement when a dose is recorded, expiry alerts) and charging
  each application, which depends on billing.

### Procedures — next phases
Phase 1 (per-clinic catalog, orders from the consultation or direct, checklist and vitals,
consent on paper, signed note with amendments, pathology specimen mark, suggested follow-up)
is done. Next:

- **Phase 2 — results and documents:** track the pathology result (received, reported to the
  patient) with reminders for overdue results; a printable procedure note and consent form;
  rooms and equipment for procedure appointments.
- **Phase 3 — inventory and billing:** supplies used per procedure (sutures, anesthetics,
  IUDs) decremented from the shared inventory, and charging each procedure, which depends on
  billing.

## Security — consciously deferred

Quick wins already applied (June 2026): constant-time login, CORS/docs validation in
production, security headers, upload metadata validation, auditing of chart reads
(`patient.chart_viewed`) and `startswith` in the audit filter. In addition, the session token
is no longer stored in localStorage: it lives in an httpOnly cookie (SameSite=Lax, Secure in
production) with double-submit CSRF (`mc_csrf` + `X-CSRF-Token`); the
`Authorization: Bearer` header is still accepted for API clients. Also: integration tests of
the SQL audit repository against real PostgreSQL
(`tests/infrastructure/test_audit_repository_sql.py` — they uncovered and fixed a missing
LIKE wildcard escape in the category filters) and a strict CSP injected into the SPA build
(meta tag in `dist/index.html` through a Vite plugin; the full header with `frame-ancestors`
is documented for the reverse proxy in the frontend README).

Resolved in June 2026 (without Redis — the counter and the sessions live in PostgreSQL, which
is already queried on every authenticated request):

- **Login lockout**: a failure counter in the DB per `(slug, email)` with a temporary lockout
  and exponential backoff (5 failures → 1 min, doubling up to 15); answers 429 with
  `Retry-After`, also counts non-existent accounts (anti-enumeration) and audits
  `auth.login_locked`.
- **Session revocation**: a `sessions` table + a `sid` claim in the JWT validated on every
  request; real logout, a password change revokes the other sessions, suspension/reset
  revokes all of them, and support (impersonation) sessions are revocable too.
- **Trusted `X-Forwarded-For`**: the header is only honored from proxies listed in
  `TRUSTED_PROXIES` (IPs/CIDRs; the chain is walked right to left discarding trusted hops);
  empty → the socket IP is recorded. The Docker image starts uvicorn with
  `--no-proxy-headers` so the app is the only one interpreting the header.
- **Organization enumeration at login**: an unknown or invalid slug answers exactly like a
  wrong password (`invalid credentials`) and runs the verify against the dummy hash, so
  neither the message nor the timing reveals which slugs exist. The clinic's status
  (`this organization is not active`) is only reported after valid credentials, just like
  the account's.

Pending, in rough order of value:

1. **Password policy** — the current minimum is 8 characters with no other requirements
   (`use_cases/auth.py`). NIST suggests ≥12 or an entropy check (zxcvbn).
2. **Demo seed password** — `scripts/seed_demo.py` uses a fixed `demo1234`. It's explicitly a
   development script, but it could generate a random password and print it.
