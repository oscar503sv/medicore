# Medicore — Frontend

**English** · [Español](README.es.md)

Medicore's web interface: the multi-tenant clinic panel and the platform console (superadmin).

The UI **adapts to the actor's effective permissions**: every action and navigation entry is
shown according to the permissions the backend resolves for the user's role (with the clinic's
overrides already applied), and the **Roles & Permissions** screen lets an admin edit those
overrides. Enforcement always lives in the backend; the UI only mirrors the same model.

## Stack

- **React 18** + **TypeScript** + **Vite 6**
- **Tailwind CSS 3** (PostCSS + autoprefixer) — styling
- **TanStack Query** — server data fetching and caching
- **Zustand** — global state (session, platform, UI preferences)
- **React Router 6** — routing
- **Axios** — HTTP client
- **date-fns** / **date-fns-tz** — date formatting in the clinic's timezone
- **lucide-react** — icons
- **Custom i18n** (Spanish / English) in `src/lib/i18n.ts`
- **ESLint 9** (flat config) + **typescript-eslint**

## Structure

```
src/
├── api/          # axios client (client.ts: cookies, CSRF, error translation)
│                 # + 16 per-domain modules (patients, appointments, notifications…)
├── components/   # ui/ primitives, shell/ (top bar, notification bell…), domain
│                 # components (appointments, audit, patients, permissions, records,
│                 # settings) and guards (RequireAuth, RequirePlatformAuth)
├── pages/        # 17 tenant screens (Patients, PatientDetail, Appointments, Schedule,
│                 # Consultation, Records, Availability, Insurers, Users, Audit,
│                 # Permissions, Notifications, Settings…)
│   └── platform/ # 5 superadmin screens (ClinicsList, ClinicDetail, GlobalStats,
│                 # GlobalAudit, PlatformLogin)
├── stores/       # zustand: auth (tenant), platformAuth (superadmin), ui (theme/language)
├── lib/          # i18n, format, cn, audit, notifications, validation, timezones…
└── types/        # shared types (entities, API responses)
```

## Getting started

```bash
npm install
cp .env.example .env       # optional (the defaults work for local development)
npm run dev                # http://localhost:3000
```

The dev server proxies `/api` requests to the backend (by default `http://localhost:8000`),
so **the backend must be running**. See `backend/README.md`.

## Languages and error messages

The whole interface is available in Spanish and English (`src/lib/i18n.ts`). API errors carry a
stable `code` and its `params`; `errorMessage()` (`src/api/client.ts`) translates it through the
`err.<code>` key, showing permissions, statuses and roles with their translated labels. The
`detail` text sent by the backend (in English) is never shown to the user.

## Environment variables

Vite exposes variables prefixed with `VITE_` (see `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_API_BASE_URL` | Backend base URL for the **build**. Useful when frontend and backend live on different origins (e.g. `https://api.mydomain.com/api/v1`). | `/api/v1` (same origin) |
| `VITE_API_PROXY_TARGET` | Development only: where `vite dev` proxies `/api` requests. | `http://localhost:8000` |

## Scripts

```bash
npm run dev       # dev server (HMR) on :3000
npm run build     # type-check (tsc -b) + production build → dist/
npm run preview   # serves the production build locally
npm run lint      # ESLint
```

## Deployment

Two models, depending on how the app is served:

- **Same origin** (recommended): a reverse proxy (e.g. nginx) serves the static content of
  `dist/` and routes `/api/v1` to the backend. Nothing to configure — the client uses the
  relative path `/api/v1` by default.
- **Different origins** (frontend and backend on separate hosts): set
  `VITE_API_BASE_URL=https://<your-backend>/api/v1` **at build time**. The backend already
  enables CORS.

### Content-Security-Policy

The build automatically injects a strict CSP meta tag into `dist/index.html`
(`script-src 'self'`, Google Fonts allowed, `connect-src` includes the origin of
`VITE_API_BASE_URL` when it is absolute). It only applies to the production build: it isn't
injected during `npm run dev` because Vite's HMR uses inline scripts.

`frame-ancestors` can't be declared through a meta tag — the reverse proxy should add it as a
real header (which then makes the whole policy take precedence over the meta):

```nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-src 'none'; frame-ancestors 'none'" always;
```
