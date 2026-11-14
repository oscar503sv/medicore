# Medicore — Backend

[English](README.md) · **Español**

API y lógica de negocio de Medicore, un sistema de gestión clínica **multi-tenant**, organizado
en **Clean Architecture**.

## Stack

- **Python ≥ 3.12**
- **FastAPI** + **Uvicorn** — API REST (prefijo `/api/v1`)
- **SQLAlchemy 2.0** + **PostgreSQL** (psycopg3) — persistencia
- **Alembic** — migraciones de esquema
- **PyJWT** + **bcrypt** — autenticación y hashing de contraseñas
- **cryptography** — AES-256-GCM para los secretos MFA de los superadmins
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

En cifras: **22 entidades** y **10 value objects** de dominio, **20 repositorios (Protocols)**,
**5 puertos de aplicación** (Clock, CodeGenerator, PasswordHasher, TokenIssuer, UnitOfWork),
**20 grupos de casos de uso** y **26 routers / 181 endpoints** bajo `/api/v1/`.

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
  contraseña forzado en el primer ingreso. La sesión viaja en una **cookie httpOnly**
  (`mc_session` para clínicas, SameSite=Lax; `mc_console` para la consola de plataforma, SameSite=Strict
  y enviada solo a `/api/v1/platform`; `Secure` con prefijos `__Host-` / `__Secure-` fuera de
  desarrollo) con **token CSRF ligado a la sesión** (`mc_csrf` / `mc_console_csrf` + cabecera
  `X-CSRF-Token` en mutaciones; es un HMAC del id de sesión, así que un token de un ámbito no
  sirve en el otro); el header `Authorization: Bearer` se acepta como alternativa para clientes API.
- **Sesiones revocables server-side**: cada login crea una fila en `sessions` referenciada
  por el claim `sid` del JWT y validada en cada request. El logout revoca de verdad, el
  cambio de contraseña revoca las demás sesiones del usuario, y suspender o resetear la
  contraseña de una cuenta cierra todas sus sesiones al instante. Vista de **sesiones
  activas**: cada usuario ve y cierra las suyas (Configuración), el admin las de cualquier
  usuario de su clínica, y el superadmin las de una clínica completa (revocaciones de
  terceros auditadas como `session.revoked`).
- **Límites de la sesión de consola**: la sesión de la consola de superadmin caduca tras 30 min sin actividad y como máximo 8 h después del login (`PLATFORM_SESSION_IDLE_MINUTES` / `PLATFORM_SESSION_MAX_MINUTES`). El refresco en segundo plano de Monitoreo no cuenta como actividad, y un superadmin desactivado pierde el acceso en la siguiente petición.
- **MFA TOTP opcional para superadmins**: se activa desde la consola, en *Seguridad de la cuenta* (`/platform/security`). Con MFA activo, el login de la consola pide la contraseña y después un código de 6 dígitos de una app de autenticación, o un código de recuperación. El desafío es de un solo uso, válido 5 min y va en una cookie httpOnly limitada a `/api/v1/platform/login`. Un código no se puede reutilizar, y tras 5 intentos fallidos el bloqueo es progresivo. Hay 10 códigos de recuperación de un solo uso, mostrados una sola vez y guardados como hash. El secreto TOTP se cifra con AES-256-GCM. Activar MFA, regenerar los códigos de recuperación o desactivarlo exige la contraseña actual, y cada cambio queda en la auditoría de plataforma.
- **Lockout de login**: contador de intentos fallidos por `(organización, email)` con
  bloqueo temporal y backoff exponencial (HTTP 429 + `Retry-After`); cuenta también
  cuentas inexistentes para no revelar cuáles existen.
- **Permisos granulares** (`application/common/permissions.py`): catálogo de **30 permisos**
  (`Permission`, `StrEnum`), un set por defecto por rol (`ROLE_PERMISSIONS`) y **overrides por
  tenant** vía `RolePermissionOverride`. `effective_permissions(role, stored)` resuelve defaults
  vs. override e intersecta con el catálogo vigente; la capa de presentación los coloca en
  `ActorContext.permissions`, de modo que cada `ensure_permission(...)` honra la personalización
  de la clínica. Router `role_permissions` (`GET`/`PUT`/`DELETE`) para administrarlos.
- **Pacientes**: los filtros del listado (estado, médico de cabecera) se aplican también a la
  búsqueda, que exige cada palabra en el nombre completo, el código o el teléfono, sin importar
  los acentos. Cada paciente trae su última visita completada y la próxima; `GET /patients/stats`
  da las cifras de la página (activos, inactivos, nuevos en 30 días, con cita próxima).
- **Vacunación** (`domain/services/immunization.py`): esquema nacional de El Salvador (MINSAL)
  para infancia, adolescencia y adultos mayores, más las dosis según indicación (embarazo,
  grupos de riesgo). El esquema es nacional, así que vive en código como datos versionados;
  solo se guardan las dosis registradas (`vaccination_records`). El estado de cada dosis
  (aplicada, rechazada, contraindicada, toca, atrasada, próxima, programada, no aplica) se
  calcula a partir de la edad, el sexo y los registros del paciente — las periódicas
  (influenza anual, Td cada 10 años) vuelven a tocar un periodo después de la última. Una
  dosis aplicada en la clínica exige su lote; las copiadas del carné se registran como
  externas. Los registros no se editan: uno erróneo se anula con motivo y queda en el
  historial. Router `vaccinations`: catálogo, carné del paciente, registrar, anular y una lista
  de trabajo de la clínica (tocan/atrasadas, próximas en un horizonte, aplicadas hoy).
  Permisos `vaccinations.view` / `vaccinations.record`.
- **Aplicaciones en la clínica** (`domain/entities/application.py`): una `ApplicationOrder`
  dice qué aplicar (medicamento, dosis, vía, número de dosis e intervalo, minutos de
  observación — 30 por defecto). Las internas se indican en la consulta y se emiten de forma
  atómica al firmarla; las externas (sin cita) registran al médico que receta y su número de
  JVPM. Cada dosis es un `ApplicationRecord` (aplicada, rechazada o contraindicada; lote,
  vencimiento, sitio, presión arterial, temperatura) que no se edita: uno erróneo se anula
  con motivo y su dosis vuelve a tocar. Una dosis aplicada abre una observación que se cierra
  "sin reacción" o como reacción adversa (lo que notifica al médico que la indicó, sin
  contenido clínico). `domain/services/allergies.py` cruza el medicamento con las alergias
  del paciente (nombres directos y familias: penicilinas, cefalosporinas, AINE, sulfonamidas,
  metamizol); aplicarlo de todos modos exige una justificación auditada. Router
  `applications`: lista de trabajo (por aplicar hoy, en observación, registradas hoy),
  historial del paciente, orden externa, cancelar, registrar, cerrar observación y anular.
  Permisos `applications.view` / `applications.administer`.
- **Procedimientos menores** (`domain/entities/procedure.py`): cada clínica tiene un
  catálogo de `ProcedureType`, precargado en la primera lectura desde
  `domain/services/procedure_catalog.py` (14 procedimientos comunes con plantillas de técnica
  e indicaciones) y editable por el admin: quién lo realiza (`doctor` o `doctor_or_nurse`),
  consentimiento informado, muestra habitual a patología y días de control sugerido. Un
  `Procedure` congela esas reglas al indicarse — en la consulta, emitido de forma atómica al
  firmarla, o registrado directamente — y puede ligarse a una cita de tipo `procedure`, que
  se completa al firmar el procedimiento. El consentimiento firmado en papel se registra como
  firmante, parentesco y testigo (sin archivo). Firmar exige el consentimiento (si aplica), la
  revisión de alergias, la técnica y, si se envió muestra, su descripción; una anestesia que
  choca con las alergias del paciente necesita una justificación auditada. Una vez firmada,
  la nota no se edita: las correcciones son enmiendas (quien lo realizó o un médico). Se
  notifica al médico que lo indicó si lo realizó otra persona, sin contenido clínico. Router
  `procedures`: catálogo, lista de trabajo (pendientes, citas de procedimiento de hoy,
  realizados en 30 días), historial del paciente, crear, avance, consentimiento, firmar,
  cancelar y enmendar. Permisos `procedures.view` / `procedures.perform` /
  `procedures.catalog`.
- **Agenda**: disponibilidad por médico, resolución de slots, ciclo de vida de la cita
  (agendada → confirmada → en curso → completada).
- **Consulta → historial**: al firmar una consulta se emite un `MedicalRecord` inmutable + las
  recetas, y se completa la cita, todo en una transacción.
- **Notificaciones in-app** (`application/common/notifications.py`): los casos de uso las
  emiten dentro de su propia transacción —se guardan junto con la acción o no se guardan—,
  nunca al propio autor. Eventos: cita creada/reprogramada/cancelada/no-show (al médico de la
  cita), historial enmendado (al autor original), documento subido (al médico asignado del
  paciente o, si no tiene, al de su última cita completada) y usuario creado/cambio de rol (a
  los admins activos). Se guarda `type` + `data` (ids y etiquetas, nunca contenido clínico ni
  nombres de archivo) y el cliente redacta el texto en su idioma. Router `notifications`:
  listado paginado (filtrable por no leídas y por categoría: `appointment`, `record`,
  `document`, `user`), contador de no leídas, marcar una / todas; las leídas con más de 90 días
  se purgan al marcar. Durante una impersonación se pueden leer pero no se marcan como leídas.
- **Panel** (`GET /dashboard/summary`): métricas reales del día —citas (sin canceladas) y
  pendientes, pacientes registrados y ocupación de la agenda (franjas reservadas sobre franjas
  dentro del horario)— comparadas con el mismo día de la semana anterior. Un médico ve solo su
  agenda; los demás roles, la clínica entera. Sin permiso para una métrica, esta llega como `null`. Junto a
  él, `GET /appointments/upcoming` lista las próximas citas agendadas/confirmadas a partir de
  ahora, aunque sean de otros días (mismo alcance por médico).
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
| `COOKIE_SECURE` | Flag `Secure` y prefijos `__Host-` / `__Secure-` en las cookies de sesión. Sin definir = activas en todo salvo `development`. No puede ser `false` en producción. | según `ENVIRONMENT` |
| `PLATFORM_SESSION_IDLE_MINUTES` | Caducidad por inactividad de la sesión de la consola (min, entre 5 y el máximo) | `30` |
| `PLATFORM_SESSION_MAX_MINUTES` | Duración absoluta de la sesión de la consola (min) | `480` (8 h) |
| `PLATFORM_COOKIE_PATH` | Ruta de la cookie de sesión de la consola (solo se envía a la API de plataforma) | `/api/v1/platform` |
| `MFA_ENCRYPTION_KEY` | Clave que cifra los secretos TOTP de los superadmins (AES-256-GCM): 32 bytes en base64url. **Obligatoria en producción** (la app no arranca sin ella). En desarrollo, si está vacía, se deriva de `JWT_SECRET`. Si se pierde, los MFA ya activados no se pueden verificar. Generarla: `python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"` | vacío |
| `MFA_ISSUER` | Nombre que muestra la app autenticadora junto al código | `Medicore` |
| `CORS_ORIGINS` | Orígenes permitidos (coma-separados); `*` solo en desarrollo | `*` |
| `ENABLE_DOCS` | Exponer Swagger/OpenAPI en `/api/v1/docs` | `true` (dev) / `false` (prod, salvo opt-in explícito) |
| `TRUSTED_PROXIES` | IPs/CIDRs (coma-separados) de los reverse-proxies cuya cabecera `X-Forwarded-For` se honra (p. ej. `127.0.0.1` o `10.0.0.0/8`). Vacío → la cabecera se ignora y se registra la IP del socket. Un valor inválido impide el arranque. | vacío |
| `DEMO_PASSWORD` | Contraseña de los usuarios demo que crea `scripts/seed_demo.py` (≥ 8 caracteres). **Obligatoria en producción**, donde se rechaza la contraseña pública por defecto. | `demo1234` (solo dev) |
| `DEMO_ADMIN_PASSWORD` | Contraseña de los admins de clínica de la demo (≥ 8 caracteres), privada para que la contraseña compartida no abra la administración. **Obligatoria en producción** y distinta de `DEMO_PASSWORD` | `DEMO_PASSWORD` |

> En **producción** (`ENVIRONMENT=production`) la app **falla al arrancar** si `JWT_SECRET` sigue
> siendo el default inseguro o es demasiado corto, o si `CORS_ORIGINS` es `*`, `COOKIE_SECURE` es `false` o `MFA_ENCRYPTION_KEY` está vacía. Además los docs
> quedan desactivados salvo `ENABLE_DOCS=true` explícito. En desarrollo no se valida nada y los
> defaults funcionan tal cual.

## Puesta en marcha

```bash
# 1) Entorno e instalación (incluye dependencias de desarrollo)
python -m venv .venv
.venv/bin/pip install -e ".[dev]"        # Windows: .venv\Scripts\pip install -e ".[dev]"

# 2) Esquema de base de datos
.venv/bin/alembic upgrade head

# 3) (opcional) catálogo de diagnósticos CIE-10/CIE-11
.venv/bin/python scripts/import_icd.py

# 4) Datos de demo: 2 clínicas con ~8 semanas de historia y 4 de agenda, generadas ejecutando
#    los casos de uso reales con un reloj simulado (incluye auditoría y notificaciones)
.venv/bin/python scripts/seed_demo.py            # idempotente
.venv/bin/python scripts/seed_demo.py --reset    # borra los tenants demo y los recrea

# 5) (opcional) Alta de un superadmin de plataforma
.venv/bin/python scripts/create_platform_admin.py

# Superadmin que perdió la app autenticadora y los códigos de recuperación: desactiva su MFA y revoca sus sesiones
.venv/bin/python scripts/reset_platform_mfa.py <correo>

# 6) Levantar la API
.venv/bin/uvicorn medicore.presentation.main:app --reload
```

- API en `http://localhost:8000/api/v1`, documentación interactiva en `/api/v1/docs`,
  liveness en `/health` y readiness (base de datos accesible, `503` si no) en `/health/ready`,
  también servida como `/api/v1/health/ready` para que un monitor externo la alcance vía nginx.
- Tras correr el seed, todos los usuarios demo usan la contraseña de `DEMO_PASSWORD`
  (**`demo1234`** en desarrollo si no se define) y los admins de clínica la de
  `DEMO_ADMIN_PASSWORD` (la misma `DEMO_PASSWORD` si no se define). En producción ambas son
  obligatorias: el seed rechaza la contraseña por defecto y una de admins igual a la compartida.

## Formato de errores

Toda respuesta de error tiene la misma forma:

```json
{"detail": "user with email x@y.test already exists", "code": "user.email_taken", "params": {"email": "x@y.test"}}
```

- `code` es estable y es lo que traduce el frontend (`err.<code>` en `frontend/src/lib/i18n.ts`,
  con `{param}` interpolado desde `params`). `detail` es texto en inglés para clientes de la API y
  logs; no se muestra al usuario.
- Los errores llevan un código por defecto según su clase (`not_found`, `permission_denied`,
  `invalid_transition`…) y uno específico en el punto donde se lanzan (`code="slot.not_bookable"`).
  Las `HTTPException` sin código propio salen como `http.<status>`; la validación de FastAPI (422)
  como `request_invalid` (con `detail` en su formato original de lista y los campos en
  `params.fields`); un fallo inesperado (500) como `internal`.
- Los campos de tipo enum (`role`, `sex`, `kind`, `status`…) se declaran con el enum en los
  schemas: un valor desconocido es un 422 `request_invalid` que nombra el campo, nunca un 500.
- `tests/presentation/test_error_codes_api.py` falla si el backend emite un código sin traducción
  en español **y** en inglés: al añadir un código nuevo hay que añadir sus dos textos.
- 401 solo para "¿quién eres?" (credenciales, sesión): el cliente cierra la sesión ante un 401. Una
  contraseña actual incorrecta al cambiarla es un 400 (`password.current_incorrect`).

## Pruebas y linting

Suite de **1209 tests** (270 dominio · 500 aplicación · 299 presentación · 140 infraestructura), casi
toda independiente de la base de datos gracias a adaptadores en memoria que ejercen el mismo
contrato multi-tenant que los repos SQLAlchemy.

Los tests de integración contra PostgreSQL real (`tests/infrastructure/test_audit_repository_sql.py`,
`test_diagnosis_catalog_sql.py` — ranking y búsqueda por trigram del autocomplete de diagnósticos —
`test_login_throttle_sql.py` — UPSERT atómico del lockout de login — y
`test_notification_repository_sql.py` — JSONB y UPDATE/DELETE masivos de la bandeja —
`test_patient_search_sql.py` — búsqueda sin acentos, dígitos del teléfono, últimas visitas) usan `TEST_DATABASE_URL`
(o `DATABASE_URL` de la configuración),
corren dentro de una transacción que siempre se revierte —no dejan rastro en la BD de desarrollo—
y se **saltan automáticamente** si no hay PostgreSQL accesible.

```bash
.venv/bin/pytest
.venv/bin/ruff check src tests
```

## Despliegue

Imagen Docker lista para producción (`Dockerfile` en esta carpeta; usuario no-root, arranca con
uvicorn en el puerto 8000). Su entrypoint aplica las migraciones pendientes (`alembic upgrade
head`) antes de levantar la app; `SKIP_MIGRATIONS=1` lo omite. Incluye además `scripts/` y los
CSV de CIE en `data/`, para poder importar el catálogo y correr el seed dentro del contenedor.
Para el stack completo (PostgreSQL + backend + nginx) ver el `docker-compose.yml` de la raíz.

```bash
# Build
docker build -t medicore-backend .

# Solo migraciones (el entrypoint ya las corre al arrancar)
docker run --rm --env-file .env medicore-backend alembic upgrade head

# Levantar la API
docker run -d -p 8000:8000 --env-file .env medicore-backend
```

Checklist de producción (vía variables de entorno, ver tabla de **Configuración**):

- `ENVIRONMENT=production`
- `JWT_SECRET` fuerte (`openssl rand -hex 32`) — la app no arranca si es inseguro.
- `MFA_ENCRYPTION_KEY` definida (32 bytes en base64url) — la app no arranca sin ella.
- `DATABASE_URL` apuntando a la base de datos real.
- `CORS_ORIGINS` con los orígenes del frontend (no `*`).
- `TRUSTED_PROXIES` con la IP del reverse-proxy (p. ej. `127.0.0.1` si nginx corre en el
  mismo host) para que la auditoría registre la IP real del cliente.
- Opcional: `ENABLE_DOCS=false` para ocultar Swagger/OpenAPI.

> **Nota de actualización:** tras aplicar la migración `d0e1f2a3b4c6` (límites de la sesión de consola), los usuarios de clínica y los superadmins deben volver a iniciar sesión una vez.

> **Antes de desplegar esta versión:** define `MFA_ENCRYPTION_KEY` (32 bytes en base64url). La migración `e1f2a3b4c5d7` añade las columnas de MFA a `platform_admins` y la tabla `platform_admin_recovery_codes`.

> Para varios workers basta con `WEB_CONCURRENCY=N` (uvicorn la lee; el `docker-compose.yml` usa 2). Cada
> worker tiene su propio pool de hasta 15 conexiones: mantén `N × 15` por debajo de `max_connections` de Postgres.
> La app se sirve detrás de un reverse-proxy que termina TLS y reenvía `X-Forwarded-For`.
> La cabecera **solo se honra** si la conexión viene de un proxy listado en
> `TRUSTED_PROXIES` (recorriendo la cadena de derecha a izquierda y descartando los hops
> confiables); en cualquier otro caso se registra la IP del socket. La imagen arranca
> uvicorn con `--no-proxy-headers` para que la app sea la única que interprete la
> cabecera — mantenlo así si sobreescribes el `CMD`.
