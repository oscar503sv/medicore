# Medicore

Sistema de gestión clínica **multi-tenant** construido con **Clean Architecture**.

Cubre el ciclo completo de atención: autenticación, dashboard, gestión de pacientes, agenda y citas, consulta en curso (bitácora SOAP), historiales clínicos firmados e inmutables, archivos médicos, disponibilidad por doctor, gestión de usuarios y ajustes de organización.

---

## Stack

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.14 |
| ORM | SQLAlchemy 2.0 (sync) |
| Migraciones | Alembic 1.18 |
| Base de datos | PostgreSQL (psycopg3) |
| Auth | PyJWT 2.13 + passlib/bcrypt |
| Validación config | pydantic-settings |
| API | FastAPI 0.136 |
| Frontend *(pendiente)* | React + TypeScript + Vite |
| Tests | pytest 9 + in-memory adapters |
| Lint | ruff |

---

## Arquitectura

El backend sigue **Clean Architecture** estricta con cuatro capas. La regla de dependencia apunta siempre hacia adentro — `domain` no importa nada externo:

```
src/medicore/
├── domain/           # Núcleo de negocio — sin dependencias de framework
│   ├── enums.py
│   ├── shared/       # Errores de dominio + identificadores UUID tipados
│   ├── value_objects/  # TimeRange, Vitals, IcdCode, Slug, SoapNote…
│   ├── entities/     # Aggregates: Appointment (FSM), Consultation, MedicalRecord…
│   ├── services/     # slot_resolver — lógica de disponibilidad pura
│   └── repositories/ # Interfaces (puertos), 12 Protocols
│
├── application/      # Casos de uso (interactors) + puertos de infra
│   ├── ports/        # Clock, PasswordHasher, TokenIssuer, CodeGenerator, UnitOfWork
│   ├── common/       # ActorContext, errores de app, permisos por rol, audit_entry
│   └── use_cases/    # auth, patients, appointments, consultations, records,
│                     # availability, users, organization
│
├── infrastructure/   # Implementaciones concretas
│   ├── config.py     # Settings desde .env (pydantic-settings)
│   ├── database/     # Engine SQLAlchemy + session factory
│   ├── persistence/
│   │   ├── models/   # ORM models (15 tablas; VOs complejos como JSONB)
│   │   ├── mappers/  # ORM ↔ domain entity (sin contaminar el dominio)
│   │   └── repositories/  # Implementaciones SQLAlchemy de los 12 puertos
│   └── auth/         # JwtTokenIssuer, BcryptPasswordHasher, DbSequentialCodeGenerator
│
└── presentation/
    ├── app.py           # Factory: crea FastAPI + CORS + error handlers + routers
    ├── main.py          # Entry point (uvicorn medicore.presentation.main:app)
    ├── dependencies.py  # DI: get_actor (JWT→ActorContext), get_uow, get_codes, get_clock
    ├── serializers.py   # domain entity → dict (sin tocar el dominio)
    ├── error_handlers.py# DomainError/AppError → HTTP 4xx/5xx
    ├── schemas/         # Pydantic request + response por recurso
    └── routers/         # 8 routers, 47 endpoints bajo /api/v1/
```

### Multi-tenant
Toda entidad de negocio lleva `tenant_id`. El filtro se aplica **en cada repositorio**, no en el caller — la golden rule del `DOMAIN_MODEL.md` se cumple estructuralmente. El `UnitOfWork` está scoped por tenant: `factory.for_tenant(tenant_id)`.

### Reglas de negocio críticas
- Citas solo dentro de la disponibilidad del doctor, sin solapes, respetando `BookingRules`.
- `MedicalRecord` firmado es **inmutable**; correcciones = enmiendas versionadas.
- `SignConsultation` es **atómico**: record + recetas + cita `completed` en una transacción.
- Permisos por rol validados en la capa de aplicación (no solo en UI).
- Auditoría de accesos y cambios sensibles (HIPAA/GDPR).

---

## Estructura del monorepo

```
medicore_v1/
├── .env.example              # Plantilla de variables de entorno (sin secretos)
├── backend/
│   ├── .env                  # Variables reales — gitignoreado, nunca commitear
│   ├── alembic.ini           # Config de Alembic (URL inyectada desde .env)
│   ├── migrations/           # Migraciones Alembic (autogenerate)
│   ├── pyproject.toml        # Metadata + deps + config pytest/ruff
│   └── src/medicore/         # Código fuente (ver Arquitectura arriba)
│   └── tests/
│       ├── domain/           # Tests de dominio (VOs, FSM, slot_resolver…)
│       ├── application/      # Tests de casos de uso con repos en memoria
│       └── support/          # InMemoryStore, repos, UoW, fakes, builders
└── frontend/                 # SPA React + TS + Vite  [fase 4]
```

---

## Estado del proyecto

| Fase | Contenido | Estado |
|---|---|---|
| **1** | Dominio completo + 73 tests | ✅ Completada |
| **2** | 53 casos de uso + 37 tests (repos en memoria) | ✅ Completada |
| **3** | SQLAlchemy, Alembic, JWT, bcrypt, multi-tenant | ✅ Completada |
| **4** | API FastAPI — 47 endpoints, 37 tests | ✅ Completada |
| **5** | UI pantalla por pantalla (React + TS + Vite) | 🔜 Pendiente |

---

## Configuración y desarrollo

### Requisitos
- Python 3.12+
- PostgreSQL (base de datos `medicore` creada)

### Primera vez

```bash
cd backend

# 1. Instalar dependencias
.venv/bin/pip install -e ".[dev]"

# 2. Configurar variables de entorno
cp .env.example .env
# Editar .env con los valores reales:
#   DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/medicore
#   JWT_SECRET=<openssl rand -hex 32>

# 3. Crear tablas
.venv/bin/alembic upgrade head

# 4. Ejecutar tests
.venv/bin/pytest

# 5. Lint
.venv/bin/ruff check src tests
```

### Levantar el servidor

```bash
cd backend
.venv/bin/uvicorn medicore.presentation.main:app --reload
# API disponible en http://localhost:8000/api/v1/
# Docs interactivos en http://localhost:8000/api/v1/docs
```

### Comandos habituales

```bash
# Tests
.venv/bin/pytest                          # suite completa (110 tests)
.venv/bin/pytest tests/domain/            # solo tests de dominio
.venv/bin/pytest tests/application/      # solo tests de aplicación

# Lint
.venv/bin/ruff check src tests            # verificar
.venv/bin/ruff check --fix src tests      # corregir

# Migraciones
.venv/bin/alembic upgrade head            # aplicar migraciones pendientes
.venv/bin/alembic revision --autogenerate -m "descripción"  # nueva migración
.venv/bin/alembic downgrade -1            # revertir última migración
```

---

## Base de datos

15 tablas creadas por la migración inicial (`a622afdfaa21`):

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
| `doctor_availability` + `availability_exceptions` | Horario + excepciones |
| `notifications` | Notificaciones in-app |
| `audit_logs` | Trazabilidad HIPAA/GDPR |
| `tenant_counters` | Contadores para códigos legibles (`P-00142`, `A-2401`…) |

---

## Tests

La suite de pruebas es **independiente de la base de datos** — usa adaptadores en memoria que ejercen el mismo contrato multi-tenant que los repos SQLAlchemy.

```
147 tests en verde
  73  — dominio (VOs, FSM, slot_resolver, Consultation.sign, MedicalRecord.amend)
  37  — aplicación (auth, citas, consultas, records, permisos, aislamiento multi-tenant)
  37  — presentación (endpoints HTTP: auth guards, booking, lifecycle, rol 403)
```

Los tests de la capa de aplicación verifican:
- Atomicidad de `SignConsultation`: un fallo revierte record, recetas y estado de cita.
- Aislamiento multi-tenant: los repos de un tenant no filtran datos de otro.
- Guardas de permiso por rol (receptionist, nurse, doctor, admin).

---

## Variables de entorno

| Variable | Descripción | Ejemplo |
|---|---|---|
| `DATABASE_URL` | URL de conexión PostgreSQL | `postgresql+psycopg://user:pass@localhost:5432/medicore` |
| `JWT_SECRET` | Clave HMAC para tokens (≥32 bytes aleatorios) | `openssl rand -hex 32` |
| `JWT_ALGORITHM` | Algoritmo JWT | `HS256` |
| `JWT_EXPIRE_MINUTES` | Expiración del token en minutos | `1440` (24 h) |
