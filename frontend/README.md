# Medicore — Frontend

Interfaz web de Medicore: panel clínico multi-tenant y consola de plataforma (superadmin).

## Stack

- **React 18** + **TypeScript** + **Vite 6**
- **Tailwind CSS 3** (PostCSS + autoprefixer) — estilos
- **TanStack Query** — fetching y caché de datos del servidor
- **Zustand** — estado global (sesión, plataforma, preferencias de UI)
- **React Router 6** — enrutado
- **Axios** — cliente HTTP
- **date-fns** / **date-fns-tz** — formateo de fechas con zona horaria de la clínica
- **lucide-react** — iconos
- **i18n propio** (español / inglés) en `src/lib/i18n.ts`
- **ESLint 9** (flat config) + **typescript-eslint**

## Estructura

```
src/
├── api/          # cliente axios (client.ts) + módulos por dominio (patients, appointments…)
├── components/   # primitivos de UI, componentes de dominio y el shell de la app
├── pages/        # pantallas del tenant (Patients, Appointments, Records, Audit, Settings…)
│   └── platform/ # consola de superadmin (Clinics, GlobalStats, GlobalAudit…)
├── stores/       # zustand: auth (tenant), platformAuth (superadmin), ui (tema/idioma)
├── lib/          # i18n, format, cn, audit, validation, timezones
└── types/        # tipos compartidos (entidades, respuestas de API)
```

## Puesta en marcha

```bash
npm install
cp .env.example .env       # opcional (los valores por defecto sirven para desarrollo local)
npm run dev                # http://localhost:3000
```

El servidor de desarrollo proxyea las peticiones `/api` al backend (por defecto
`http://localhost:8000`), así que **el backend debe estar corriendo**. Consulta `backend/README.md`.

## Variables de entorno

Vite expone variables con prefijo `VITE_` (ver `.env.example`):

| Variable | Descripción | Default |
|----------|-------------|---------|
| `VITE_API_BASE_URL` | URL base del backend para el **build**. Útil cuando frontend y backend están en orígenes distintos (p. ej. `https://api.midominio.com/api/v1`). | `/api/v1` (mismo origen) |
| `VITE_API_PROXY_TARGET` | Solo desarrollo: a dónde proxyea `vite dev` las peticiones `/api`. | `http://localhost:8000` |

## Scripts

```bash
npm run dev       # servidor de desarrollo (HMR) en :3000
npm run build     # type-check (tsc -b) + build de producción → dist/
npm run preview   # sirve el build de producción localmente
npm run lint      # ESLint
```

## Despliegue

Dos modelos según cómo se sirva la app:

- **Mismo origen** (recomendado): un reverse-proxy (p. ej. nginx) sirve el contenido estático de
  `dist/` y enruta `/api/v1` al backend. No hace falta configurar nada — el cliente usa la ruta
  relativa `/api/v1` por defecto.
- **Orígenes distintos** (frontend y backend en hosts separados): define
  `VITE_API_BASE_URL=https://<tu-backend>/api/v1` **al hacer el build**. El backend ya habilita CORS.
