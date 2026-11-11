# Medicore

[English](README.md) · **Español**

Sistema de gestión clínica **multi-tenant** construido con **Clean Architecture**.

Cubre el ciclo completo de atención: autenticación por organización, dashboard con métricas reales, gestión de pacientes, agenda y citas, consulta en curso (bitácora SOAP) con **catálogo de diagnósticos CIE-10/CIE-11**, historiales clínicos firmados e inmutables, archivos médicos, disponibilidad por doctor, aseguradoras, gestión de usuarios, **permisos granulares por rol con personalización por clínica**, **notificaciones in-app**, **vacunación según el esquema nacional de El Salvador**, **aplicaciones de medicamentos en la clínica**, **procedimientos menores**, ajustes de organización y una **guía de primeros pasos** para médicos y administradores que se marca sola con los datos reales. La interfaz está disponible en **español e inglés**, incluidos los mensajes de error del backend.

Incluye además una **consola de plataforma (superadmin)** por encima del límite multi-tenant: alta y administración de clínicas, un panel de **Negocio** (MRR, cobros, vencimientos, adopción y cupos por clínica), **Monitoreo** (salud de la API y la base de datos, errores del servidor, intentos fallidos y bloqueos, sesiones y accesos de soporte abiertos, rendimiento de la API por ruta), auditoría global, soporte de cuentas (reseteo de contraseña, desbloqueo, suspensión) e **impersonación auditada** de una clínica para dar soporte.

---

## Stack

| Capa | Tecnología |
|---|---|
| Lenguaje | Python ≥ 3.12 |
| API | FastAPI ≥ 0.115 + Uvicorn |
| ORM | SQLAlchemy 2.0 (sync) |
| Migraciones | Alembic ≥ 1.13 |
| Base de datos | PostgreSQL (psycopg3) |
| Auth | PyJWT ≥ 2.8 + bcrypt ≥ 4 · cookie httpOnly + CSRF double-submit |
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
│   ├── shared/         # Errores de dominio (con código traducible) + identificadores UUID tipados
│   ├── value_objects/  # 10 VOs: TimeRange, DateRange, Vitals, IcdCode, Slug,
│   │                   # SoapNote, ContactInfo, BloodType, Money, UserPreferences
│   ├── entities/       # 22 agregados: Appointment (FSM), Consultation, MedicalRecord,
│   │                   # Prescription, Patient, User, Tenant, Insurer, MedicalDocument,
│   │                   # Availability, Notification, AuditLog, AuthSession,
│   │                   # CatalogDiagnosis, RolePermissionOverride, PlatformAdmin,
│   │                   # PlatformAuditLog, VaccinationRecord, ApplicationOrder,
│   │                   # ApplicationRecord, ProcedureType, Procedure
│   ├── services/       # slot_resolver (disponibilidad), immunization (esquema), allergies,
│   │                   # procedure_catalog (catálogo por defecto)
│   └── repositories/   # Interfaces (puertos): 20 Protocols de repositorio
│
├── application/      # Casos de uso (interactors) + puertos de infra
│   ├── ports/          # 5 puertos: Clock, CodeGenerator, PasswordHasher,
│   │                   # TokenIssuer, UnitOfWork
│   ├── common/         # ActorContext, errores de app, catálogo de permisos,
│   │                   # auditoría, lockout de login, emisión de notificaciones, timezone
│   └── use_cases/      # 20 grupos: auth, sessions, patients, appointments,
│                       # consultations, records, prescriptions, availability, users,
│                       # organization, insurers, diagnoses, audit, role_permissions,
│                       # notifications, dashboard, vaccinations, applications,
│                       # procedures, platform
│
├── infrastructure/   # Implementaciones concretas
│   ├── config.py       # Settings desde .env (pydantic-settings) — dev-safe por defecto
│   ├── database/       # Engine SQLAlchemy + session factory
│   ├── persistence/
│   │   ├── models/     # ORM models (33 tablas; VOs complejos como JSONB)
│   │   ├── mappers/    # ORM ↔ domain entity (sin contaminar el dominio)
│   │   └── repositories/  # Implementaciones SQLAlchemy de los puertos
│   └── auth/           # JwtTokenIssuer, BcryptPasswordHasher, generador de códigos, SystemClock
│
└── presentation/
    ├── app.py           # Factory: crea FastAPI + CORS + security headers + error handlers + routers
    ├── main.py          # Entry point (uvicorn medicore.presentation.main:app)
    ├── dependencies.py  # DI: get_actor / get_platform_actor (cookie o Bearer → Context,
    │                    # sesión revocable, CSRF), get_uow, get_codes, get_clock
    ├── cookies.py       # Cookies de sesión httpOnly + token CSRF
    ├── client_ip.py     # IP real del cliente (X-Forwarded-For solo desde proxies confiables)
    ├── serializers.py   # domain entity → dict (sin tocar el dominio)
    ├── errors.py        # ApiError: HTTPException con código traducible
    ├── error_handlers.py# Errores → {"detail", "code", "params"} con su status HTTP
    ├── schemas/         # Pydantic request + response por recurso
    └── routers/         # 19 routers, 130 endpoints bajo /api/v1/
```

### Multi-tenant
Toda entidad de negocio lleva `tenant_id`. El filtro se aplica **en cada repositorio**, no en el caller — el aislamiento se cumple estructuralmente. El `UnitOfWork` está scoped por tenant: `factory.for_tenant(tenant_id)`. Las operaciones globales (resolución de slug, superadmin) usan un `UnitOfWork` no scopeado o helpers de solo lectura.

### Plataforma (superadmin)
Sesión separada (token de scope `platform`) que opera por encima del límite multi-tenant: alta/edición de clínicas (incluidas la zona horaria y las sedes), la **suscripción** de cada clínica (plan, módulos, periodo pagado, condiciones especiales, pagos), cambio de estado (activa / suspendida / archivada), estadísticas y auditoría globales, soporte de cuentas (reseteo de contraseña, desbloqueo, suspensión de usuarios) e **impersonación**. La impersonación emite un token de tenant marcado con `impersonated_by` y con TTL más corta, de modo que toda escritura durante el soporte queda auditada.

### Reglas de negocio críticas
- Citas solo dentro de la disponibilidad del doctor, sin solapes, respetando las reglas de reserva.
- `MedicalRecord` firmado es **inmutable**; las correcciones son **enmiendas versionadas** (`status=amended` que referencia al original).
- `SignConsultation` es **atómico**: record + recetas + cita `completed` en una sola transacción.
- Diagnósticos en consulta limitados al catálogo de la **versión CIE configurada por cada clínica** (CIE-10 / CIE-11), con autocompletado.
- **Vacunación** según el esquema nacional de El Salvador (MINSAL), para niños, adolescentes y adultos: el carné de cada paciente calcula el estado de cada dosis (aplicada, toca, atrasada, próxima…) a partir de su edad y sus registros; los registros no se editan, uno erróneo se anula con motivo. Una lista de trabajo muestra las dosis atrasadas y próximas de toda la clínica.
- **Aplicaciones en la clínica** (inyecciones, sueros, nebulizaciones…): el médico las indica en la consulta y se vuelven órdenes para enfermería al firmarla; las que llegan sin cita con receta externa registran al médico que receta y su número de JVPM. Cada dosis se registra con lote, sitio y signos vitales, no se edita (una errónea se anula con motivo) y abre una observación (30 min por defecto, configurable por orden) que se cierra "sin reacción" o como reacción adversa, lo que notifica al médico que la indicó. Aplicar un medicamento que choca con las alergias del paciente exige una justificación escrita y auditada.
- **Procedimientos menores** (suturas, biopsias, curaciones, DIU, electrocardiograma…): cada clínica tiene un catálogo configurable, precargado con los más comunes, que dice quién puede realizar cada uno (solo médico, o médico o enfermería), si requiere consentimiento informado, si suele tomar muestra para patología y el control sugerido. Se indican en la consulta (quedan pendientes al firmarla) o se registran directamente, opcionalmente ligados a una cita de procedimiento. Antes de realizarlo: revisión de alergias, anticoagulantes, ayuno y signos vitales; el consentimiento firmado en papel se registra con quién firmó y un testigo (sin archivo). La nota (anestesia, técnica, hallazgos, materiales, complicaciones, indicaciones, muestra enviada a patología) no se edita una vez firmada — las correcciones son enmiendas — y al firmar se sugiere la fecha de control y se notifica al médico que lo indicó si lo realizó otra persona.
- **Permisos granulares** validados en la capa de aplicación (no solo en UI) — ver sección siguiente.
- Contraseña temporal con cambio forzado en el primer ingreso.
- **Política de contraseñas** (`domain/services/password_policy.py`, al estilo NIST SP 800-63B) en todos los puntos donde se fija una contraseña — invitar, restablecer (clínica o consola), cambiarla, alta de clínica, script de superadmin: al menos 10 caracteres (máximo 72 bytes, el límite de bcrypt), letras y un número o símbolo, que no sea una contraseña común, nada del nombre, correo o clínica de la persona, y distinta de la actual. Sin caducidad periódica; la fuerza bruta la cubre el bloqueo de inicio de sesión. La UI muestra los requisitos en vivo y genera contraseñas temporales que siempre cumplen.
- Auditoría de accesos y cambios sensibles (HIPAA/GDPR), por tenant y global.

---

## Permisos

El control de acceso es **granular y personalizable por clínica** (`application/common/permissions.py`):

- **Catálogo de 31 permisos** (`Permission`, `StrEnum`) agrupados por recurso: `patients.*`, `appointments.*`, `availability.manage`, `consultations.*`, `records.*` (incluye `sign` y `amend`), `prescriptions.manage`, `diagnoses.view`, `insurers.*`, `users.*`, `organization.*`, `locations.manage`, `audit.view`, `permissions.manage`, `vaccinations.*`, `applications.*`, `procedures.*`.
- **4 roles** — `admin`, `doctor`, `nurse`, `receptionist` — con un conjunto de permisos por defecto en `ROLE_PERMISSIONS`.
- **Overrides por tenant**: cada clínica puede personalizar el set de un rol mediante una fila `RolePermissionOverride`. `effective_permissions(role, stored)` resuelve defaults vs. override (e intersecta con el catálogo vigente para tolerar permisos retirados).
- En cada request, la capa de presentación coloca los permisos efectivos en `ActorContext.permissions`, de modo que toda comprobación `ensure_permission(...)` honra la personalización de la clínica.
- **Excepciones por usuario** (planes con la función `user_permissions`, desde Clínica): una persona puede recibir algunos permisos extra o perder algunos de su rol. Se guardan como diferencia con el rol (`PermissionAdjustments` en `User`), así que los cambios posteriores del rol le siguen llegando. Se editan desde **Usuarios → Permisos** (`GET`/`PUT /users/{id}/permissions`). En un plan sin la función, las excepciones guardadas se conservan pero no se aplican.
- **Los módulos contratados condicionan sus permisos**: una clínica sin vacunación, aplicaciones o procedimientos no recibe ninguno de sus permisos, digan lo que digan sus roles.
- `granted(role, stored, modules, adjustments)` combina todo lo anterior; la capa de presentación coloca el resultado en `ActorContext.permissions`.
- El frontend consume el mismo modelo: la UI se condiciona por los permisos efectivos del actor y la pantalla **Roles & Permisos** edita los overrides (router `role_permissions`: `GET`/`PUT`/`DELETE`).

**Salvaguardas** (aplicadas en el backend y reflejadas en la UI):

- El rol `admin` no es personalizable y siempre tiene acceso completo (salvo firmar/enmendar expedientes).
- `records.sign` y `records.amend` son exclusivos de médicos: nunca se otorgan a otros roles o usuarios ni se les quitan a los médicos.
- `permissions.manage` es exclusivo de administradores: no se puede delegar a un rol ni a un usuario.
- Solo un admin actúa sobre cuentas de admin (editar, cambiar rol, desactivar, restablecer contraseña, cerrar sesiones) o nombra a alguien admin. Un `users.manage` delegado gestiona al resto del personal.
- Nadie edita sus propios permisos.

**Qué gestiona la clínica y qué gestiona el soporte de Medicore:**

| | Admin de la clínica | Consola de plataforma |
|---|---|---|
| Razón social, NIT, versión CIE | ✅ (`organization.manage`) | ✅ |
| Sedes (crear, renombrar) | ✅ dentro del límite del plan (`locations.manage`) | ✅ mismo límite |
| Zona horaria | solo lectura | ✅ (mueve el "hoy", la agenda y los recordatorios de la clínica) |
| Slug (identificador de inicio de sesión) | solo lectura | fijo desde la creación |
| Plan, módulos, límites, periodo pagado, pagos | solo lectura | ✅ |
| Usuarios, roles, permisos por usuario | ✅ (dentro de los cupos) | acciones de soporte (restablecer contraseña, desbloquear, desactivar) |

---

## Suscripciones y planes

Cada clínica tiene una **suscripción** (value object `Subscription` en `Tenant`): plan, módulos opcionales, fecha de pago, indicador de prueba, días de gracia y condiciones especiales (límites a la medida, precio negociado). La activación es manual: las clínicas pagan por transferencia bancaria y el soporte lo registra desde la consola de plataforma.

- **Catálogo de planes** (`plans`, editable en **Planes y precios**): Profesional independiente, Clínica, Clínica Plus y Empresarial (cotización). Cada uno fija límites de médicos, personal de apoyo (enfermería, recepción y administradores adicionales al primero), sedes y almacenamiento, además de funciones (`user_permissions`).
- **Módulos opcionales** (`addon_pricing`): vacunación, aplicaciones y procedimientos, cada uno con precio mensual y un precio de paquete por los tres.
- **Cupos** aplicados en los casos de uso (invitar, cambiar rol, reactivar, nueva sede): crecer por encima del límite se rechaza con `plan.quota_*`; una clínica que ya lo supera (tras bajar de plan) conserva lo que tiene.
- **Pagos y renovación** (`subscription_payments`): registrar un pago extiende el periodo de 1 a 24 meses. Al vencer, la clínica sigue operando durante los días de gracia; después queda en **solo lectura** (`plan.read_only`: puede consultar pero no modificar hasta renovar). La app muestra avisos al acercarse el vencimiento.
- Las clínicas ven su plan, uso e historial de pagos en **Ajustes → Organización**.

La demo pública muestra dos planes: `clinica-demo` en **Clínica Plus** con todos los módulos, y `centro-norte` en **Clínica** solo con vacunación (3 médicos, cupos de apoyo llenos), para probar también los módulos bloqueados y los mensajes de cupo.

---

## Seguridad

- **Sesiones en cookie httpOnly** (SameSite=Lax, `Secure` en producción) con **CSRF double-submit** (`mc_csrf` + cabecera `X-CSRF-Token`); el token nunca está al alcance de JavaScript. `Authorization: Bearer` sigue aceptándose para clientes de API.
- **Sesiones revocables** (tabla `sessions` + claim `sid`): logout real; cambiar la contraseña cierra las demás sesiones; suspender o resetear un usuario cierra todas.
- **Lockout de login** con backoff exponencial (5 fallos → 1 min, duplicando hasta 15) y respuesta 429 con `Retry-After`.
- **Sin enumeración**: login en tiempo constante; un slug o un email inexistente responde igual que una contraseña incorrecta.
- `X-Forwarded-For` solo se honra desde los proxies listados en `TRUSTED_PROXIES`.
- Security headers en la API y CSP estricta en el build del frontend.

Los hallazgos pendientes están en [`docs/BACKLOG.es.md`](docs/BACKLOG.es.md).

---

## Notificaciones y dashboard

- **Notificaciones in-app**: citas creadas, reprogramadas, canceladas o marcadas como no-show (al doctor), enmiendas de historial (al autor original), documentos subidos (al médico tratante) y altas o cambios de rol de usuarios (a los administradores). Campana en la barra superior con contador (sondeo cada 60 s), filtro de no leídas y enlaces directos al elemento, además de una **página de buzón** (`/notifications`) filtrable por estado y categoría y agrupada por día. Se conservan 90 días.
- **Dashboard con datos reales** (`GET /dashboard/summary`): citas de hoy, pendientes, pacientes registrados y ocupación de la agenda, cada uno comparado con la semana anterior, y las próximas citas pendientes a partir de ahora (`GET /appointments/upcoming`). El doctor ve su propia agenda; los demás roles, la clínica completa.

---

## Errores de la API

Toda respuesta de error tiene la misma forma:

```json
{"detail": "user with email x@y.test already exists", "code": "user.email_taken", "params": {"email": "x@y.test"}}
```

`code` es estable y el frontend lo traduce (claves `err.<code>` en `frontend/src/lib/i18n.ts`), interpolando `params`; `detail` es texto en inglés para clientes de API y logs. Un test falla si el backend emite un código sin traducción en ambos idiomas. Detalles en [`backend/README.es.md`](backend/README.es.md#formato-de-errores).

---

## Estructura del monorepo

```
medicore/
├── README.md                 # Versión en inglés
├── README.es.md              # Este archivo
├── LICENSE
├── docs/
│   └── BACKLOG(.es).md       # Trabajo diferido, hallazgos pendientes y planes a futuro
├── backend/
│   ├── .env.example          # Plantilla de variables de entorno (sin secretos)
│   ├── .env                  # Variables reales — gitignoreado, nunca commitear
│   ├── Dockerfile            # Imagen de producción (usuario no-root, uvicorn :8000)
│   ├── alembic.ini           # Config de Alembic (URL inyectada desde .env)
│   ├── migrations/           # 14 migraciones Alembic
│   ├── scripts/
│   │   ├── seed_demo.py            # Datos demo: ~8 semanas de historia + 4 de agenda, vía casos de uso
│   │   ├── import_icd.py           # Carga del catálogo CIE-10/CIE-11
│   │   └── create_platform_admin.py # Alta de superadmin de plataforma
│   ├── pyproject.toml        # Metadata + deps + config pytest/ruff
│   ├── src/medicore/         # Código fuente (ver Arquitectura arriba)
│   └── tests/
│       ├── domain/           # Tests de dominio (VOs, FSM, slot_resolver…)
│       ├── application/      # Tests de casos de uso con repos en memoria
│       ├── presentation/     # Tests de endpoints HTTP (TestClient)
│       ├── infrastructure/   # Tests contra PostgreSQL real (se saltan si no hay BD)
│       └── support/          # InMemoryStore, repos, UoW, fakes, builders
└── frontend/                 # SPA React + TS + Vite
    └── src/
        ├── api/              # Cliente Axios (cookies, CSRF, traducción de errores)
        │                     # + 19 módulos por recurso
        ├── stores/           # Zustand: auth + platformAuth + ui (tema/idioma/sidebar)
        ├── lib/              # i18n ES/EN, formato, QueryClient, notificaciones, timezones…
        ├── types/            # Tipos TS espejo del dominio backend
        ├── components/       # ui/ + shell/ (topbar, campana de notificaciones…)
        │                     # + appointments/ + audit/ + patients/ + permissions/
        │                     # + records/ + settings/ + vaccination/ + applications/
        │                     # + procedures/
        │                     # + guards (RequireAuth…)
        └── pages/            # 20 pantallas de clínica (Login, Dashboard, Patients,
                              # PatientDetail, Appointments, Schedule, Consultation,
                              # Records, Availability, Insurers, Users, Settings,
                              # Audit, Permissions, Notifications, ChangePassword,
                              # Vaccination, Applications, Procedures,
                              # ProcedureDetail)
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
| **9** | Seguridad: sesiones en cookie + CSRF, sesiones revocables, lockout de login, anti-enumeración | ✅ Completada |
| **10** | Notificaciones in-app (backend, campana y buzón) | ✅ Completada |
| **11** | Dashboard con métricas reales, interfaz 100 % ES/EN y errores de la API traducibles | ✅ Completada |
| **12** | Módulo de vacunación (esquema nacional de El Salvador, carné del paciente, lista de trabajo) | ✅ Completada |
| **13** | Aplicaciones en la clínica (órdenes desde la consulta o receta externa, observación, alerta de alergias) | ✅ Completada |
| **14** | Procedimientos menores (catálogo por clínica, consentimiento en papel, nota firmada con enmiendas, muestra a patología, control) | ✅ Completada |
| **15** | Suscripciones SaaS (catálogo de planes, módulos opcionales, cupos, pagos y renovación manuales, solo lectura tras la gracia, permisos por usuario) | ✅ Completada |
| **16** | Política de contraseñas (longitud, lista de bloqueo, nada personal, requisitos en vivo en la UI) | ✅ Completada |
| **17** | Consola de plataforma: Negocio (MRR, cobros, vencimientos, adopción, cupos) y Monitoreo (salud, conexiones, errores 500 sin datos de pacientes con su commit y tendencia, accesos y bloqueos, accesos a la consola auditados, soporte abierto, tareas programadas, rendimiento por ruta con p50/p95 y tasas 4xx/5xx, `/health/ready`) | ✅ Completada |
| — | Notificaciones por email/SMS y recordatorios de citas | 🗓️ A futuro |
| — | Inventario de lotes de vacunas y recordatorios de vacunación | 🗓️ A futuro |
| — | Aplicaciones: catálogo de medicamentos frecuentes, constancia imprimible, inventario y facturación | 🗓️ A futuro |
| — | Procedimientos: seguimiento del resultado de patología, nota imprimible, salas/equipo, inventario y facturación | 🗓️ A futuro |

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
# API en http://localhost:8000/api/v1/ · docs en /api/v1/docs · health en /health (vida) y /health/ready (BD)
```

El seed reproduce ~8 semanas de actividad de la clínica y las próximas 4 semanas de agenda respecto al día en que se ejecuta (vuelve a correrlo con `--reset` para actualizar las fechas). Los usuarios demo usan la contraseña de `DEMO_PASSWORD` (en desarrollo, si no se define, **`demo1234`**) y los admins de clínica la de `DEMO_ADMIN_PASSWORD` (la misma `DEMO_PASSWORD` si no se define); en producción ambas son obligatorias y deben ser distintas. Ver detalles en
[`backend/README.es.md`](backend/README.es.md).

### Frontend

```bash
cd frontend
npm install            # primera vez
npm run dev            # http://localhost:3000 (proxy /api → :8000)
npm run lint           # eslint
npm run build          # type-check (tsc -b) + build de producción → dist/
```

Detalles de variables `VITE_*` y despliegue en [`frontend/README.es.md`](frontend/README.es.md).

### Comandos habituales

```bash
# Backend
.venv/bin/pytest                          # suite completa (581 tests)
.venv/bin/pytest tests/domain/            # solo tests de dominio
.venv/bin/ruff check src tests            # lint (--fix para corregir)

# Migraciones
.venv/bin/alembic upgrade head            # aplicar migraciones pendientes
.venv/bin/alembic revision --autogenerate -m "descripción"  # nueva migración
```

---

## Base de datos

**33 tablas**, creadas por la migración inicial (`a622afdfaa21`) y ampliadas por las migraciones posteriores:

| Tabla | Descripción |
|---|---|
| `tenants` + `locations` | Organización / clínica y sus sedes |
| `users` + `doctor_profiles` | Cuentas de acceso y perfil clínico |
| `sessions` | Sesiones activas (revocables) de clínica, soporte y plataforma |
| `login_attempts` | Contador de fallos de login para el lockout |
| `patients` | Pacientes (datos demográficos, médico asignado, etiquetas, alergias) |
| `appointments` | Citas con FSM de estado |
| `consultations` | Consulta en curso (borrador mutable) |
| `medical_records` | Historiales firmados e inmutables |
| `prescriptions` | Recetas emitidas |
| `medical_documents` | Archivos médicos (metadata) |
| `insurers` | Aseguradoras de la clínica |
| `doctor_availability` + `availability_exceptions` | Horario + excepciones |
| `notifications` | Notificaciones in-app (payload JSONB) |
| `audit_logs` | Trazabilidad HIPAA/GDPR por tenant |
| `tenant_counters` | Contadores para códigos legibles (`P-00142`, `A-2401`…) |
| `vaccination_records` | Dosis de vacunas registradas (esquema nacional) |
| `application_orders` + `application_records` | Órdenes de aplicación en la clínica y las dosis aplicadas |
| `procedure_types` + `procedures` | Catálogo de procedimientos por clínica y los procedimientos indicados/realizados |
| `role_permission_overrides` | Personalización de permisos por rol y tenant |
| `plans` + `addon_pricing` | Catálogo de planes y precios de módulos opcionales (global) |
| `subscription_payments` | Pagos registrados por clínica (renovaciones) |
| `diagnosis_codes` | Catálogo CIE-10/CIE-11 (global, para autocompletado) |
| `platform_admins` | Superadmins de la plataforma |
| `platform_audit_logs` | Auditoría global de operaciones de plataforma |
| `error_events` | Errores inesperados del servidor (ruta, tipo, ubicación y commit; sin datos de pacientes; 30 días) |
| `job_runs` | Ejecuciones de tareas programadas (p. ej. el reset nocturno de la demo) y su resultado |
| `request_stats` | Peticiones a la API por hora y plantilla de ruta: volumen, 4xx/5xx e histograma de latencia (30 días) |

---

## Tests

Casi toda la suite es **independiente de la base de datos** — usa adaptadores en memoria que ejercen el mismo contrato multi-tenant que los repos SQLAlchemy. Los tests de infraestructura corren contra **PostgreSQL real** dentro de una transacción que siempre se revierte, y se saltan si no hay base de datos disponible.

```
581 tests en verde
   120  — dominio (VOs, FSM, slot_resolver, Consultation.sign, MedicalRecord.amend,
            esquema de vacunación, aplicaciones, procedimientos, cruce de alergias)
   240  — aplicación (auth, sesiones, citas, consultas, records, notificaciones, dashboard,
            plataforma, permisos granulares, aislamiento multi-tenant)
   171  — presentación (endpoints HTTP: auth guards, CSRF, booking, lifecycle, 403 por
            permiso, códigos de error, validación, plataforma)
    50  — infraestructura (repositorios SQLAlchemy contra PostgreSQL)
```

Los tests verifican, entre otras cosas:
- Atomicidad de `SignConsultation`: un fallo revierte record, recetas y estado de cita.
- Aislamiento multi-tenant: los repos de un tenant no filtran datos de otro.
- Permisos efectivos por rol y override por tenant, y de scope de plataforma.
- Lockout de login, revocación de sesiones y protección CSRF.
- Que todo código de error del backend tenga traducción en español e inglés.

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
| `CORS_ORIGINS` | Orígenes permitidos (coma-separados); `*` solo en desarrollo | `*` |
| `ENABLE_DOCS` | Exponer Swagger/OpenAPI en `/api/v1/docs` | `true` (dev) / `false` (prod) |
| `TRUSTED_PROXIES` | IPs/CIDRs de reverse-proxies cuyo `X-Forwarded-For` se honra; vacío → IP del socket | vacío |
| `SOURCE_COMMIT` | Commit desplegado, que muestra la página de Monitoreo | vacío |
| `DEMO_PASSWORD` | Contraseña de los usuarios demo que crea `scripts/seed_demo.py` (≥ 8 caracteres). **Obligatoria en producción**, donde se rechaza la contraseña pública por defecto | `demo1234` (solo dev) |
| `DEMO_ADMIN_PASSWORD` | Contraseña de los admins de clínica de la demo (≥ 8 caracteres), privada para que la contraseña compartida no abra la administración. **Obligatoria en producción** y distinta de `DEMO_PASSWORD` | `DEMO_PASSWORD` |

> En **producción** (`ENVIRONMENT=production`) la app **falla al arrancar** si `JWT_SECRET` sigue siendo el default inseguro o es demasiado corto, o si `CORS_ORIGINS` es `*`; además los docs quedan desactivados salvo `ENABLE_DOCS=true` explícito. En desarrollo no se valida y los defaults funcionan tal cual.

---

## Despliegue

El backend incluye un `Dockerfile` listo para producción (usuario no-root, uvicorn en el puerto 8000). El frontend se sirve como estático (`dist/`) en el mismo origen tras un reverse-proxy, o en un host separado con `VITE_API_BASE_URL` definido al hacer el build. Pasos detallados en [`backend/README.es.md`](backend/README.es.md) y [`frontend/README.es.md`](frontend/README.es.md).

### Despliegue con Docker Compose / Coolify

El [`docker-compose.yml`](docker-compose.yml) de la raíz levanta todo el stack en un **único origen**: `db` (PostgreSQL 16, volumen persistente), `backend` (aplica `alembic upgrade head` al arrancar) y `frontend` (nginx que sirve el SPA, redirige `/api/` al backend y agrega las cabeceras de seguridad). Solo `frontend` lleva dominio público; el TLS lo termina el proxy de borde (Traefik en Coolify).

1. Genera los secretos: `openssl rand -hex 32` (`JWT_SECRET`) y `openssl rand -base64 24` (`POSTGRES_PASSWORD`), y elige `DEMO_PASSWORD` (la que compartes con quien prueba la demo) y `DEMO_ADMIN_PASSWORD` (privada, para los admins de clínica).
2. En Coolify: **New Resource → Public Repository** → este repo, rama `main`, **Build Pack: Docker Compose**, archivo `/docker-compose.yml`.
3. Variables de entorno: `POSTGRES_PASSWORD`, `JWT_SECRET`, `APP_ORIGIN` (p. ej. `https://medicore.ejemplo.com`), `DEMO_PASSWORD` y `DEMO_ADMIN_PASSWORD`. Opcionales: `POSTGRES_DB`, `POSTGRES_USER`, `ENABLE_DOCS`, `JWT_EXPIRE_MINUTES`, `WEB_CONCURRENCY` (workers de uvicorn, por defecto 2). Si falta una obligatoria el stack no arranca, a propósito.
4. Asigna el dominio solo al servicio **frontend** y pulsa **Deploy**.
5. Carga inicial de datos (una vez), en una terminal del contenedor `backend`:
   ```sh
   python scripts/import_icd.py cie11 data/cie11.csv
   python scripts/import_icd.py cie10 data/cie10.csv
   python scripts/seed_demo.py            # --reset para actualizar las fechas de la demo
   python scripts/create_platform_admin.py <correo> "<nombre>" '<contraseña>'
   ```

Los redeploys conservan los datos (volumen `medicore-pgdata`) y aplican las migraciones nuevas al arrancar.

Para una demo pública, agrega en Coolify una **Scheduled Task** nocturna en el contenedor `backend` que ejecute `python scripts/seed_demo.py --reset` (p. ej. `0 9 * * *`, las 03:00 en El Salvador): deshace lo que hayan cambiado los visitantes, evita que se acumulen datos y mueve las fechas al día actual. No toca el catálogo CIE ni los superadmins de la plataforma. Cada ejecución queda registrada y la página *Monitoreo* marca la tarea si falla o si pasan más de 26 h sin un reset exitoso.

**Monitoreo.** La página *Monitoreo* de la consola solo carga si la API responde, así que para enterarte de una caída configura un monitor externo (UptimeRobot, Better Stack…) contra `https://<tu-dominio>/api/v1/health/ready`: responde `200` si la API y la base de datos están bien y `503` si la base de datos no responde. El commit desplegado que muestra la página sale de `SOURCE_COMMIT`, que Coolify inyecta en el contenedor. No la declares en el compose: Coolify bloquea las variables del compose y una vacía taparía la suya. Fuera de Coolify, defínela tú; si falta, la página lo indica.

---

## Backlog y planes a futuro

El trabajo diferido, los hallazgos de seguridad pendientes y la funcionalidad planificada a futuro (notificaciones por email/SMS, recordatorios de citas) están en [`docs/BACKLOG.es.md`](docs/BACKLOG.es.md).
