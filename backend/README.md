# Medicore — Backend

API y lógica de negocio de Medicore, un sistema de gestión clínica **multi-tenant**, organizado
en **Clean Architecture**.

## Stack

- **Python ≥ 3.12**
- **FastAPI** + **Uvicorn** — API REST (prefijo `/api/v1`)
- **SQLAlchemy 2.0** + **PostgreSQL** (psycopg3) — persistencia
- **Alembic** — migraciones de esquema
- **PyJWT** + **bcrypt** — autenticación y hashing de contraseñas
- **pydantic-settings** — configuración por entorno
- **pytest** + **ruff** — pruebas y linting

## Capas

```
src/medicore/
├── domain/          # Núcleo del negocio. Sin dependencias de framework.
│   ├── enums.py
│   ├── shared/        # errores de dominio + identificadores (UUID + code)
│   ├── value_objects/ # Vitals, SoapNote, IcdCode, ContactInfo, BloodType, Slug…
│   ├── entities/      # Patient, Appointment, Consultation, MedicalRecord, Prescription…
│   ├── services/      # domain services (lógica que no pertenece a una sola entidad)
│   └── repositories/  # interfaces (puertos); las implementaciones viven en infrastructure
├── application/     # casos de uso (interactors), DTOs, puertos de infra
├── infrastructure/  # SQLAlchemy, auth JWT/bcrypt, generador de códigos, filtro multi-tenant
└── presentation/    # FastAPI: routers, schemas, serializers, manejo de errores
```

La **regla de dependencia** apunta hacia adentro: `domain` no importa de ninguna otra capa;
`application` solo de `domain`; `infrastructure`/`presentation` de las internas.

## Convenciones del dominio

- **Value Objects**: `@dataclass(frozen=True)`, validan invariantes en `__post_init__`.
- **Entidades / agregados**: `@dataclass` mutable; la mutación pasa por métodos que preservan
  invariantes (p. ej. la máquina de estados de `Appointment`, o la firma inmutable de
  `MedicalRecord`).
- **Identidad**: UUID (`*Id`) como clave real; un `code` legible aparte para la UI
  (`P-00142`, `A-2401`, `REC-2026-0512-CR`).
- **Multi-tenant**: toda entidad de negocio lleva `tenant_id`; el filtrado por tenant es
  responsabilidad de los repositorios, no del caller.
- **Inmutabilidad clínica**: un `MedicalRecord` firmado no se modifica; una corrección genera una
  **enmienda** (nuevo registro con `status=amended` que referencia al original).

## Funcionalidades

- **Autenticación** por JWT con roles (`admin`, `doctor`, `nurse`, `receptionist`) y cambio de
  contraseña forzado en el primer ingreso.
- **Agenda**: disponibilidad por médico, resolución de slots, ciclo de vida de la cita
  (agendada → confirmada → en curso → completada).
- **Consulta → historial**: al firmar una consulta se emite un `MedicalRecord` inmutable + las
  recetas, y se completa la cita, todo en una transacción.
- **Auditoría (HIPAA/GDPR)** por tenant y consola global de plataforma; cada acción guarda un
  `subject` legible en su metadata para una columna de detalle útil.
- **Consola de plataforma** (superadmin): alta/gestión de clínicas, estadísticas globales,
  auditoría consolidada y **sesiones de soporte** (impersonación con TTL corto y traza).

## Configuración

Copia `.env.example` a `.env` y ajusta los valores:

| Variable | Descripción | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | `development` o `production`. En producción se activan validaciones estrictas. | `development` |
| `DATABASE_URL` | Cadena de conexión PostgreSQL (psycopg3) | `postgresql+psycopg://localhost/medicore` |
| `JWT_SECRET` | Secreto para firmar tokens. **Obligatorio y fuerte en producción** (`openssl rand -hex 32`). | `change-me` (solo dev) |
| `JWT_ALGORITHM` | Algoritmo JWT | `HS256` |
| `JWT_EXPIRE_MINUTES` | Expiración del token | `1440` (24 h) |
| `JWT_SUPPORT_EXPIRE_MINUTES` | Expiración de sesiones de soporte/impersonación | `60` (1 h) |
| `CORS_ORIGINS` | Orígenes permitidos (coma-separados) o `*` para cualquiera | `*` |
| `ENABLE_DOCS` | Exponer Swagger/OpenAPI en `/api/v1/docs` | `true` |

> En **producción** (`ENVIRONMENT=production`) la app **falla al arrancar** si `JWT_SECRET` sigue
> siendo el default inseguro o es demasiado corto. En desarrollo no se valida nada y los defaults
> funcionan tal cual.

## Puesta en marcha

```bash
# 1) Entorno e instalación (incluye dependencias de desarrollo)
python -m venv .venv
.venv/bin/pip install -e ".[dev]"        # Windows: .venv\Scripts\pip install -e ".[dev]"

# 2) Esquema de base de datos
.venv/bin/alembic upgrade head

# 3) (opcional) catálogo de diagnósticos CIE-10/CIE-11
.venv/bin/python scripts/import_icd.py

# 4) Datos de demo (2 clínicas pobladas: usuarios, pacientes, citas, historiales, auditoría)
.venv/bin/python scripts/seed_demo.py            # idempotente
.venv/bin/python scripts/seed_demo.py --reset    # borra los tenants demo y los recrea

# 5) Levantar la API
.venv/bin/uvicorn medicore.presentation.main:app --reload
```

- API en `http://localhost:8000/api/v1`, documentación interactiva en `/api/v1/docs`,
  health-check en `/health`.
- Tras correr el seed, todos los usuarios demo usan la contraseña **`demo1234`**.

## Pruebas y linting

```bash
.venv/bin/pytest
.venv/bin/ruff check src
```

## Despliegue

Imagen Docker lista para producción (`Dockerfile` en esta carpeta; usuario no-root, arranca con
uvicorn en el puerto 8000):

```bash
# Build
docker build -t medicore-backend .

# Migraciones (paso aparte, antes de levantar la app)
docker run --rm --env-file .env medicore-backend alembic upgrade head

# Levantar la API
docker run -d -p 8000:8000 --env-file .env medicore-backend
```

Checklist de producción (vía variables de entorno, ver tabla de **Configuración**):

- `ENVIRONMENT=production`
- `JWT_SECRET` fuerte (`openssl rand -hex 32`) — la app no arranca si es inseguro.
- `DATABASE_URL` apuntando a la base de datos real.
- `CORS_ORIGINS` con los orígenes del frontend (no `*`).
- Opcional: `ENABLE_DOCS=false` para ocultar Swagger/OpenAPI.

> Para varios workers: `uvicorn ... --workers N` (sobreescribiendo el `CMD`) o un gestor de procesos.
> La app se sirve detrás de un reverse-proxy que termina TLS y reenvía `X-Forwarded-For`
> (la auditoría registra la IP del cliente a partir de esa cabecera).
