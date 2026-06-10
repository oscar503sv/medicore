# Medicore

Sistema de gestión clínica **multi-tenant** construido con **Clean Architecture**.

Cubre el ciclo completo de atención: autenticación por organización, dashboard, gestión de pacientes, agenda y citas, consulta en curso (bitácora SOAP) con **catálogo de diagnósticos CIE-10/CIE-11**, historiales clínicos firmados e inmutables, archivos médicos, disponibilidad por doctor, aseguradoras, gestión de usuarios, **permisos granulares por rol con personalización por clínica** y ajustes de organización.

Incluye además una **consola de plataforma (superadmin)** por encima del límite multi-tenant: alta y administración de clínicas, estadísticas y auditoría globales, soporte de cuentas (reseteo de contraseña, desbloqueo, suspensión) e **impersonación auditada** de una clínica para dar soporte.

---

## Stack

| Capa | Tecnología |
|---|---|
| Lenguaje | Python ≥ 3.12 |
| API | FastAPI ≥ 0.115 + Uvicorn |
| ORM | SQLAlchemy 2.0 (sync) |
| Migraciones | Alembic ≥ 1.13 |
| Base de datos | PostgreSQL (psycopg3) |
| Auth | PyJWT ≥ 2.8 + bcrypt ≥ 4 |
| Validación config | pydantic-settings |
| Tests / Lint | pytest ≥ 8 + ruff (adaptadores en memoria) |
| Frontend | React 18 + TypeScript 5 + Vite 6 |
| Estado / datos (FE) | Zustand + TanStack Query + Axios |
| Estilos (FE) | Tailwind CSS 3 + design tokens |
| Enrutado / i18n (FE) | React Router 6 + i18n propio ES/EN |

---

## Arquitectura

El backend sigue **Clean Architecture** estricta con cuatro capas. La regla de dependencia apunta siempre hacia adentro — `domain` no importa nada externo:

```
src/medicore/
├── domain/           # Núcleo de negocio — sin dependencias de framework
│   ├── enums.py
│   ├── shared/         # Errores de dominio + identificadores UUID tipados
│   ├── value_objects/  # 10 VOs: TimeRange, DateRange, Vitals, IcdCode, Slug,
│   │                   # SoapNote, ContactInfo, BloodType, Money, UserPreferences
│   ├── entities/       # 16 agregados: Appointment (FSM), Consultation, MedicalRecord,
│   │                   # Prescription, Patient, User, Tenant, Insurer, MedicalDocument,
│   │                   # Availability, Notification, AuditLog, CatalogDiagnosis,
│   │                   # RolePermissionOverride, PlatformAdmin, PlatformAuditLog
│   ├── services/       # slot_resolver — lógica de disponibilidad pura
│   └── repositories/   # Interfaces (puertos): 16 Protocols de repositorio
│
├── application/      # Casos de uso (interactors) + puertos de infra
│   ├── ports/          # 5 puertos: Clock, CodeGenerator, PasswordHasher,
│   │                   # TokenIssuer, UnitOfWork
│   ├── common/         # ActorContext, errores de app, catálogo de permisos
│   │                   # (permissions.py), timezone, audit_entry
│   └── use_cases/      # 13 grupos: auth, patients, appointments, consultations,
│                       # records, availability, users, organization, insurers,
│                       # diagnoses, audit, role_permissions, platform
│
├── infrastructure/   # Implementaciones concretas
│   ├── config.py       # Settings desde .env (pydantic-settings) — dev-safe por defecto
│   ├── database/       # Engine SQLAlchemy + session factory
│   ├── persistence/
│   │   ├── models/     # ORM models (20 tablas; VOs complejos como JSONB)
│   │   ├── mappers/    # ORM ↔ domain entity (sin contaminar el dominio)
│   │   └── repositories/  # Implementaciones SQLAlchemy de los puertos
│   └── auth/           # JwtTokenIssuer, BcryptPasswordHasher, DbSequentialCodeGenerator
│
└── presentation/
    ├── app.py           # Factory: crea FastAPI + CORS + error handlers + routers
    ├── main.py          # Entry point (uvicorn medicore.presentation.main:app)
    ├── dependencies.py  # DI: get_actor / get_platform_actor (JWT→Context),
    │                    # get_uow (yield, cierra sesión), get_codes, get_clock
    ├── serializers.py   # domain entity → dict (sin tocar el dominio)
    ├── error_handlers.py# DomainError/AppError → HTTP 4xx/5xx
    ├── schemas/         # Pydantic request + response por recurso
    └── routers/         # 13 routers, 80 endpoints bajo /api/v1/
```

### Multi-tenant
Toda entidad de negocio lleva `tenant_id`. El filtro se aplica **en cada repositorio**, no en el caller — el aislamiento se cumple estructuralmente. El `UnitOfWork` está scoped por tenant: `factory.for_tenant(tenant_id)`. Las operaciones globales (resolución de slug, superadmin) usan un `UnitOfWork` no scopeado o helpers de solo lectura.

### Plataforma (superadmin)
Sesión separada (token de scope `platform`) que opera por encima del límite multi-tenant: alta/edición de clínicas, cambio de estado (activa / suspendida / archivada), estadísticas y auditoría globales, soporte de cuentas (reseteo de contraseña, desbloqueo, suspensión de usuarios) e **impersonación**. La impersonación emite un token de tenant marcado con `impersonated_by` y con TTL más corta, de modo que toda escritura durante el soporte queda auditada.

### Reglas de negocio críticas
- Citas solo dentro de la disponibilidad del doctor, sin solapes, respetando las reglas de reserva.
- `MedicalRecord` firmado es **inmutable**; las correcciones son **enmiendas versionadas** (`status=amended` que referencia al original).
- `SignConsultation` es **atómico**: record + recetas + cita `completed` en una sola transacción.
- Diagnósticos en consulta limitados al catálogo de la **versión CIE configurada por cada clínica** (CIE-10 / CIE-11), con autocompletado.
- **Permisos granulares** validados en la capa de aplicación (no solo en UI) — ver sección siguiente.
- Contraseña temporal con cambio forzado en el primer ingreso.
- Auditoría de accesos y cambios sensibles (HIPAA/GDPR), por tenant y global.

---

## Permisos

El control de acceso es **granular y personalizable por clínica** (`application/common/permissions.py`):

- **Catálogo de 22 permisos** (`Permission`, `StrEnum`) agrupados por recurso: `patients.*`, `appointments.*`, `availability.manage`, `consultations.*`, `records.*` (incluye `sign` y `amend`), `diagnoses.view`, `insurers.*`, `users.*`, `organization.*`, `audit.view`, `permissions.manage`.
- **4 roles** — `admin`, `doctor`, `nurse`, `receptionist` — con un conjunto de permisos por defecto en `ROLE_PERMISSIONS`.
- **Overrides por tenant**: cada clínica puede personalizar el set de un rol mediante una fila `RolePermissionOverride`. `effective_permissions(role, stored)` resuelve defaults vs. override (e intersecta con el catálogo vigente para tolerar permisos retirados).
- En cada request, la capa de presentación coloca los permisos efectivos en `ActorContext.permissions`, de modo que toda comprobación `ensure_permission(...)` honra la personalización de la clínica.
- El frontend consume el mismo modelo: la UI se condiciona por los permisos efectivos del actor y la pantalla **Roles & Permisos** edita los overrides (router `role_permissions`: `GET`/`PUT`/`DELETE`).

---

## Estructura del monorepo

```
medicore/
├── README.md                 # Este archivo
├── LICENSE
├── backend/
│   ├── .env.example          # Plantilla de variables de entorno (sin secretos)
│   ├── .env                  # Variables reales — gitignoreado, nunca commitear
│   ├── Dockerfile            # Imagen de producción (usuario no-root, uvicorn :8000)
│   ├── alembic.ini           # Config de Alembic (URL inyectada desde .env)
│   ├── migrations/           # 10 migraciones Alembic (autogenerate)
│   ├── scripts/
│   │   ├── seed_demo.py            # Datos demo: clínicas, staff por rol, pacientes
│   │   ├── import_icd.py           # Carga del catálogo CIE-10/CIE-11
│   │   └── create_platform_admin.py # Alta de superadmin de plataforma
│   ├── pyproject.toml        # Metadata + deps + config pytest/ruff
│   ├── src/medicore/         # Código fuente (ver Arquitectura arriba)
│   └── tests/
│       ├── domain/           # Tests de dominio (VOs, FSM, slot_resolver…)
│       ├── application/      # Tests de casos de uso con repos en memoria
│       ├── presentation/     # Tests de endpoints HTTP (TestClient)
│       ├── infrastructure/   # Tests del repositorio SQLAlchemy real
│       └── support/          # InMemoryStore, repos, UoW, fakes, builders
└── frontend/                 # SPA React + TS + Vite
    └── src/
        ├── api/              # Cliente Axios + 14 módulos por recurso
        ├── stores/           # Zustand: auth + platformAuth + ui (tema/idioma/sidebar)
        ├── lib/              # i18n ES/EN, formato, QueryClient, cn(), timezones
        ├── types/            # Tipos TS espejo del dominio backend
        ├── components/       # ui/ + shell/ + appointments/ + audit/ + patients/
        │                     # + permissions/ + records/ + guards (RequireAuth…)
        └── pages/            # 16 pantallas de clínica (Login, Dashboard, Patients,
                              # PatientDetail, Appointments, Schedule, Consultation,
                              # Records, Availability, Insurers, Users, Settings,
                              # Audit, Permissions, ChangePassword, ComingSoon)
                              # + platform/ (5 pantallas de superadmin)
```

---

## Estado del proyecto

| Fase | Contenido | Estado |
|---|---|---|
| **1** | Dominio completo | ✅ Completada |
| **2** | Casos de uso (interactors) + repos en memoria | ✅ Completada |
| **3** | SQLAlchemy, Alembic, JWT, bcrypt, multi-tenant | ✅ Completada |
| **4** | API FastAPI bajo `/api/v1/` | ✅ Completada |
| **5** | Frontend React — todas las pantallas de clínica | ✅ Completada |
| **6** | Plataforma superadmin, catálogo CIE y aseguradoras | ✅ Completada |
| **7** | Permisos granulares con overrides por tenant + UI por permisos | ✅ Completada |
| **8** | Hardening de producción (dev-safe defaults) + Dockerfile | ✅ Completada |

---

## Configuración y desarrollo

### Requisitos
- Python 3.12+
- PostgreSQL (base de datos `medicore` creada)
- Node.js (para el frontend)

### Backend

```bash
cd backend

# 1. Entorno e instalación (incluye dependencias de desarrollo)
python -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 2. Configurar variables de entorno
cp .env.example .env
#   DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/medicore
#   JWT_SECRET=$(openssl rand -hex 32)

# 3. Crear tablas
.venv/bin/alembic upgrade head

# 4. (Opcional) Catálogo CIE-10/CIE-11 y datos demo
.venv/bin/python scripts/import_icd.py
.venv/bin/python scripts/seed_demo.py        # idempotente (--reset recrea)

# 5. Levantar la API
.venv/bin/uvicorn medicore.presentation.main:app --reload
# API en http://localhost:8000/api/v1/ · docs en /api/v1/docs · health en /health
```

Tras el seed, todos los usuarios demo usan la contraseña **`demo1234`**. Ver detalles en
[`backend/README.md`](backend/README.md).

### Frontend

```bash
cd frontend
npm install            # primera vez
npm run dev            # http://localhost:3000 (proxy /api → :8000)
npm run build          # type-check (tsc -b) + build de producción → dist/
```

Detalles de variables `VITE_*` y despliegue en [`frontend/README.md`](frontend/README.md).

### Comandos habituales

```bash
# Backend
.venv/bin/pytest                          # suite completa (271 tests)
.venv/bin/pytest tests/domain/            # solo tests de dominio
.venv/bin/ruff check src tests            # lint (--fix para corregir)

# Migraciones
.venv/bin/alembic upgrade head            # aplicar migraciones pendientes
.venv/bin/alembic revision --autogenerate -m "descripción"  # nueva migración
```

---

## Base de datos

**20 tablas**, creadas por la migración inicial (`a622afdfaa21`) y ampliadas por las migraciones posteriores (aseguradoras, estado de clínica + versión CIE, overrides de permisos por rol, superadmin de plataforma, catálogo de diagnósticos):

| Tabla | Descripción |
|---|---|
| `tenants` + `locations` | Organización / clínica y sus sedes |
| `users` + `doctor_profiles` | Cuentas de acceso y perfil clínico |
| `patients` | Pacientes (datos demográficos, etiquetas, alergias) |
| `appointments` | Citas con FSM de estado |
| `consultations` | Consulta en curso (borrador mutable) |
| `medical_records` | Historiales firmados e inmutables |
| `prescriptions` | Recetas emitidas |
| `medical_documents` | Archivos médicos |
| `insurers` | Aseguradoras de la clínica |
| `doctor_availability` + `availability_exceptions` | Horario + excepciones |
| `notifications` | Notificaciones in-app |
| `audit_logs` | Trazabilidad HIPAA/GDPR por tenant |
| `tenant_counters` | Contadores para códigos legibles (`P-00142`, `A-2401`…) |
| `role_permission_overrides` | Personalización de permisos por rol y tenant |
| `diagnosis_codes` | Catálogo CIE-10/CIE-11 (global, para autocompletado) |
| `platform_admins` | Superadmins de la plataforma |
| `platform_audit_logs` | Auditoría global de operaciones de plataforma |

---

## Tests

Casi toda la suite es **independiente de la base de datos** — usa adaptadores en memoria que ejercen el mismo contrato multi-tenant que los repos SQLAlchemy; un grupo pequeño de tests de infraestructura ejerce además el repositorio SQLAlchemy real.

```
271 tests en verde
    78  — dominio (VOs, FSM, slot_resolver, Consultation.sign, MedicalRecord.amend)
   119  — aplicación (auth, citas, consultas, records, diagnósticos, plataforma,
            permisos granulares, aislamiento multi-tenant)
    71  — presentación (endpoints HTTP: auth guards, booking, lifecycle, 403 por permiso, plataforma)
     3  — infraestructura (repositorio SQLAlchemy real)
```

Los tests verifican, entre otras cosas:
- Atomicidad de `SignConsultation`: un fallo revierte record, recetas y estado de cita.
- Aislamiento multi-tenant: los repos de un tenant no filtran datos de otro.
- Permisos efectivos por rol y override por tenant, y de scope de plataforma.
- Login de todos los roles y cierre correcto de las sesiones de BD (sin fuga de conexiones).

---

## Variables de entorno (backend)

| Variable | Descripción | Default |
|---|---|---|
| `ENVIRONMENT` | `development` o `production`. En producción se activan validaciones estrictas. | `development` |
| `DATABASE_URL` | URL de conexión PostgreSQL (psycopg3) | `postgresql+psycopg://localhost/medicore` |
| `JWT_SECRET` | Clave HMAC para tokens. **Obligatoria y fuerte en producción** (`openssl rand -hex 32`) | `change-me` (solo dev) |
| `JWT_ALGORITHM` | Algoritmo JWT | `HS256` |
| `JWT_EXPIRE_MINUTES` | Expiración del token en minutos | `1440` (24 h) |
| `JWT_SUPPORT_EXPIRE_MINUTES` | Expiración (min) de sesiones de impersonación/soporte — más corta por seguridad | `60` (1 h) |
| `CORS_ORIGINS` | Orígenes permitidos (coma-separados) o `*` para cualquiera | `*` |
| `ENABLE_DOCS` | Exponer Swagger/OpenAPI en `/api/v1/docs` | `true` |

> En **producción** (`ENVIRONMENT=production`) la app **falla al arrancar** si `JWT_SECRET` sigue siendo el default inseguro o es demasiado corto. En desarrollo no se valida y los defaults funcionan tal cual.

---

## Despliegue

El backend incluye un `Dockerfile` listo para producción (usuario no-root, uvicorn en el puerto 8000). El frontend se sirve como estático (`dist/`) en el mismo origen tras un reverse-proxy, o en un host separado con `VITE_API_BASE_URL` definido al hacer el build. Pasos detallados en [`backend/README.md`](backend/README.md) y [`frontend/README.md`](frontend/README.md).

---

## Backlog

El trabajo diferido (funcionalidad a medio implementar y hallazgos de seguridad pendientes) está inventariado en [`docs/BACKLOG.md`](docs/BACKLOG.md).
