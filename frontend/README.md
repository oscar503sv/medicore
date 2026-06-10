# Medicore — Frontend

Interfaz web de Medicore: panel clínico multi-tenant y consola de plataforma (superadmin).

La UI se **condiciona por los permisos efectivos del actor**: cada acción y entrada de navegación
se muestra según los permisos que el backend resuelve para el rol del usuario (con los overrides
de la clínica ya aplicados), y la pantalla **Roles & Permisos** permite a un admin editar esos
overrides. La validación de fondo siempre vive en el backend; la UI solo refleja el mismo modelo.

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
├── api/          # cliente axios (client.ts) + 14 módulos por dominio (patients,
│                 # appointments, permissions, audit, platform…)
├── components/   # primitivos ui/, shell/, componentes de dominio (appointments, audit,
│                 # patients, permissions, records) y guards (RequireAuth, RequirePlatformAuth)
├── pages/        # 16 pantallas del tenant (Patients, PatientDetail, Appointments, Schedule,
│                 # Consultation, Records, Availability, Insurers, Users, Audit,
│                 # Permissions, Settings…)
│   └── platform/ # 5 pantallas de superadmin (ClinicsList, ClinicDetail, GlobalStats,
│                 # GlobalAudit, PlatformLogin)
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
