# Backlog — deferred work and pending findings

**English** · [Español](BACKLOG.es.md)

An inventory of partially implemented functionality and of security findings that were
**documented but deliberately not addressed yet** (June 2026 audit). When picking one up, check
that the references are still accurate.

## Incomplete functionality (the backend has more than is used)

### Notification system
Complete in-app notifications: emitted from appointments, documents and user
management; `/notifications` router; a bell in the top bar with an unread counter (polled every
60 s) and a dropdown with deep links (`/appointments?date=`, `/patients/:id?tab=…&record=…`);
full inbox page at `/notifications` (filters by status and category, grouped by day).
External channels and reminders are planned as a future evolution (see [Future](#future)).

### Other loose ends
- The `AttachDocument` use case was removed (it had no endpoint, so attaching documents to a consultation in progress wasn't reachable through the API). When that endpoint exists, it must load the document with `documents.get_by_id` inside the tenant (the port only has `list_by_patient`, `save` and `delete` today, so add it), require `document.patient_id == consultation.patient_id`, and build the reference with `document.as_ref()`, never accepting it from the client.
- The `Money` value object (`domain/value_objects/money.py`) is unused — presumably reserved
  for billing.
- Medical document storage keeps **metadata only** (name, mime type, size). The server generates the `storage_key` (`{tenant_id}/{patient_id}/{document_id}`) and never returns it. There is no file backend (S3/disk) yet, and the UI says so explicitly. The future `DocumentStorage` port (R2/S3, adapter in `infrastructure`) will use this key.
- Amendment follow-ups (OZK-94, OZK-98): `procedure.amended` and `certificate.voided` store the
  reason text in the audit log, unlike record amendments and prescription cancellations (which keep
  only its length, `reason_chars`); align them.
  `platform_reads.signed_records` and `signed_per_week` (platform console) count amendments as new
  signed records; they should exclude them.
- OZK-99 (immutability trigger on `medical_records`) must go in a migration after
  `f8a9b0c1d2e4`.
- Active prescriptions that nobody can close: since OZK-100 only the prescriber completes or cancels
  a prescription, and administrators don't hold `prescriptions.manage`, so a prescription of a doctor
  who left the clinic (or was deleted) stays active (query 5 in the
  [backend README](../backend/README.md#prescriptions-closed-by-someone-else)). Decide whether the
  treating doctor or an administrator may close it, with a reason and an audit entry.
- Notify the treating doctor when a prescription was issued by another doctor (for example, when the
  prescriber leaves the clinic). OZK-100 notifies no one, since only the prescriber acts.
- An amendment does not move the documents linked to the previous version to the new one: they stay on the replaced version. Decide whether they should follow the current one.
- Control characters in file names: the upload only rejects `/`, `\`, `..` and NUL, so a name with line breaks or other control characters is accepted.
- Extension and MIME type consistency: an upload does not check that the file extension matches its `mime_type`.

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

### Performance — session cache in Redis

Every authenticated request runs two transactions: `get_actor` reads the session (so it can
be revoked server-side) and the role's permission override, then the endpoint opens its
own. Acceptable at the current volume; when it weighs, caching the session and per-role
permissions in Redis (invalidated on revocation or permission changes) would save that
extra database round trip. Already applied (Nov 2026): 2 uvicorn workers
(`WEB_CONCURRENCY`), trigram indexes for the patient search, batched availability reads in
the dashboard and purging stale `login_attempts` on login.

### Subscriptions — annual billing

Plans are priced monthly today. Offer an annual option (e.g. two months free): an annual
price per plan, editable from the console like the monthly one, and renewal adding a year to
the paid period instead of a month. The subscription itself does not change, since it already
stores the date it is paid until.

### Vital signs triage before the consultation
Today nurses record vital signs inside the consultation once it is open. A triage step before the consultation starts (nursing records weight, blood pressure and temperature when the patient arrives) would let the doctor see them as soon as the consultation opens, and would give the waiting list an order. It needs a triage state on the appointment and vital-sign readings that exist without an open consultation.

### Vital signs readings per patient — projected query
`GET /patients/{id}/vitals` loads every record of the patient, with its full content, and projects the vital signs in memory. A query that reads only the vital-sign columns, with a limit, would avoid loading the rest of a long history on each request.

## Security — consciously deferred

Quick wins already applied (June 2026): same hashing work at login whether or not the account exists, CORS/docs validation in
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

- **Login lockout**: three DB counters (per IP: 30 attempts in 15 min; per account and IP: 5 failures → 1 min, doubling up to 15; per account: 20 attempts in 15 min, exempt for IPs that signed in recently), reserved atomically before the password check; answers 429 with
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
  wrong password (`invalid credentials`) and runs one check against a dummy hash computed once per process, so
  neither the message nor the timing reveals which slugs exist. The clinic's status
  (`this organization is not active`) is only reported after valid credentials, just like
  the account's.

Resolved in November 2026:

- **Password policy** (`domain/services/password_policy.py`): at least 10 characters (at most 72 bytes), letters plus a number or symbol, not a common password, nothing from the person's name, email or clinic, and different from the current one, wherever a password is set. Live requirements in the UI.
- **JWT**: tokens carry a per-type audience and mandatory claims, cross-checked against their session row (`auth.wrong_session`); `JWT_SECRET` must be at least 32 bytes in production, and `JWT_ALGORITHM` accepts only HS256/HS384/HS512.
- **Cache-Control: no-store** on every `/api/` response (except those that set their own).
- **Input limits** on slug, email, password, names, user agent and IP; 422 errors no longer echo the submitted value.
- **Lockout on password change and superadmin MFA management**: 5 failed attempts with the current password → 429 with backoff, per account.
- **Permission exceptions** are cleared on role change; admins keep their role's full set.
- **Seat checks** lock the clinic's row, so simultaneous invitations can't exceed the plan.
- **Session purge**: a scheduled job deletes expired or revoked sessions and is monitored (`session_purge`).
- **Consultation signing serialized per consultation**: the sign locks the consultation row, and a partial unique index allows a single original record per consultation (OZK-93).
- **Clinical content of records is doctor-only** (OZK-96): `records.read_clinical` (doctor-only, not delegable) gates the note, diagnoses, record prescriptions, vaccines, exams, the full copy, certificates and the clinical history. The backend answers 403 on `GET /records/{id}` for other roles, and the frontend follows the same rule.
- **Paginated, audited records list** (OZK-97): `GET /records` returns `{items, total, offset, limit}` with server-side filters (patient, type, dates, search), metadata only outside the doctor's clinical reading, an index on `(tenant_id, encounter_at)`, and an audit entry per page (`record.listed`).
- **Consultation content is the doctor's** (OZK-95): `consultations.edit` is doctor-only (not delegable) and gates the note, diagnoses and drafts, which only the owning doctor reads or edits. Nurses record vital signs with `consultations.vitals` (delegable); administrators can start a consultation but not open it; support impersonation can't touch clinical content. Reads and edits are audited with names only (`consultation.viewed`, `consultation.note_updated`, `consultation.vitals_updated`, `consultation.template_changed`, `consultation.draft_changed`), and migration `d5e6f7a8b9c1` moves the existing grants.
- **Record amendments** (OZK-94, OZK-98): one line of versions per record. Only the current version
  is amended, at most once, by the record's author (who never changes), with a reason of 10 to 1000
  characters; serialized with a row lock and a partial unique index. The reason is stored on the
  version and shown in the history and in the printed copy, but not in the audit log; lists and
  summaries show only current versions; amendments no longer notify. The printed certificate uses the
  original signature time as the end of the consultation. Migration `e6f7a8b9c0d2` enforces the line
  (see [Branched amendment chains](../backend/README.md#branched-amendment-chains)).
- **Prescriptions closed by their prescriber** (OZK-100): only the doctor who issued a prescription
  completes or cancels it (`prescriptions.manage` is doctor-only). Cancelling needs a reason of 10 to
  500 characters, kept on the prescription and only its length in the audit log; the reason reaches
  clinical readers only. Migration `f7a8b9c0d1e3` adds the closing fields and the CHECK, and moves the
  permission (see [Prescriptions closed by someone else](../backend/README.md#prescriptions-closed-by-someone-else)).
- **Medical documents without client-chosen keys** (OZK-101): the server generates each `storage_key` (`{tenant_id}/{patient_id}/{document_id}`), it is never accepted from or returned to the client, and it is unique in the database. A document can be linked only to a record of the same patient (its current version), and support sessions can't register documents. Migration `f8a9b0c1d2e4` unlinks the documents of another patient's record and rewrites the keys (see [Document storage keys](../backend/README.md#document-storage-keys)).

No pending findings remain in this list.
