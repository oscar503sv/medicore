# Medicore

[English](README.md) · **Español**

Sistema de gestión clínica **multi-tenant** construido con **Clean Architecture**.

Cubre el ciclo completo de atención: autenticación por organización, dashboard con métricas reales, gestión de pacientes, agenda y citas, consulta en curso (**plantillas de nota clínica**: SOAP, P-SOAP, historia completa, evolución, narrativa) con **catálogo de diagnósticos CIE-10/CIE-11**, historiales clínicos firmados e inmutables, archivos médicos, disponibilidad por doctor, aseguradoras, gestión de usuarios, **permisos granulares por rol con personalización por clínica**, **notificaciones in-app**, **vacunación según el esquema nacional de El Salvador**, **aplicaciones de medicamentos en la clínica**, **procedimientos menores**, ajustes de organización y una **guía de primeros pasos** para médicos y administradores que se marca sola con los datos reales. La interfaz está disponible en **español e inglés**, incluidos los mensajes de error del backend.

Incluye además una **consola de plataforma (superadmin)** por encima del límite multi-tenant: alta y administración de clínicas, un panel de **Negocio** (MRR, cobros, vencimientos, adopción y cupos por clínica), **Monitoreo** (salud de la API y la base de datos, errores del servidor, intentos fallidos y bloqueos, sesiones y accesos de soporte abiertos, rendimiento de la API por ruta), auditoría global, soporte de cuentas (reseteo de contraseña, reactivación, suspensión) e **impersonación auditada** de una clínica para dar soporte, ambas con motivo obligatorio.

---

## Stack

| Capa | Tecnología |
|---|---|
| Lenguaje | Python ≥ 3.12 |
| API | FastAPI ≥ 0.115 + Uvicorn |
| ORM | SQLAlchemy 2.0 (sync) |
| Migraciones | Alembic ≥ 1.13 |
| Base de datos | PostgreSQL (psycopg3) |
| Auth | PyJWT ≥ 2.8 + bcrypt ≥ 4 · cookies httpOnly + CSRF ligado a la sesión |
| Cifrado en reposo | cryptography ≥ 45 · AES-256-GCM para los secretos MFA de superadmins |
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
│   │   ├── models/     # ORM models (34 tablas; VOs complejos como JSONB)
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
    └── routers/         # 26 routers, 183 endpoints bajo /api/v1/
```

### Multi-tenant
Toda entidad de negocio lleva `tenant_id`. El filtro se aplica **en cada repositorio**, no en el caller — el aislamiento se cumple estructuralmente. El `UnitOfWork` está scoped por tenant: `factory.for_tenant(tenant_id)`. Las operaciones globales (resolución de slug, superadmin) usan un `UnitOfWork` no scopeado o helpers de solo lectura.

### Plataforma (superadmin)
Sesión separada (token de scope `platform`, con cookie propia `mc_console`) que opera por encima del límite multi-tenant: alta/edición de clínicas (incluidas la zona horaria y las sedes), la **suscripción** de cada clínica (plan, módulos, periodo pagado, condiciones especiales, pagos), cambio de estado (activa / suspendida / archivada), estadísticas y auditoría globales, soporte de cuentas (reseteo de contraseña, reactivación, suspensión de usuarios) e **impersonación**. La impersonación y los reseteos de contraseña desde soporte exigen un motivo (5–500 caracteres) que queda en la auditoría. Las acciones de soporte sobre usuarios de una clínica (reseteo de contraseña, edición, cambio de rol, suspensión, reactivación) y la entrada o salida de impersonación quedan en la auditoría de esa clínica como «Soporte de la plataforma», con IP y navegador pero sin nombre ni email del superadmin, y se notifican en la campana a los admins activos de la clínica y al usuario afectado (la entrada de impersonación, solo a los admins). No se duplican en la auditoría global de la consola. La impersonación emite un token de tenant marcado con `impersonated_by` y con TTL más corta, de modo que toda escritura durante el soporte queda auditada. Se puede impersonar una clínica suspendida, pero no una archivada.

### Reglas de negocio críticas
- Citas solo dentro de la disponibilidad del doctor, sin solapes, respetando las reglas de reserva.
- `MedicalRecord` firmado es **inmutable**; las correcciones son **enmiendas versionadas** (`status=amended` que referencia al original). Solo el autor del expediente lo enmienda, y solo su versión vigente: un expediente se enmienda como máximo una vez, así que las versiones forman una sola línea. El motivo es obligatorio (de 10 a 1000 caracteres), y cada versión guarda quién la firmó y cuándo (`signed_by_id`, `signed_at`), de modo que el autor nunca cambia. Las enmiendas no notifican a nadie, y la auditoría guarda las secciones cambiadas y la longitud del motivo, nunca su texto, porque los administradores la leen sin acceso clínico.
- **Enmiendas en el panel lateral del expediente**: **Enmendar** aparece solo al autor y solo en la versión vigente; el modal pide el motivo con un contador. El **historial de versiones** lista cada versión con quién la firmó, la fecha, el motivo y la marca de vigente. Una versión antigua muestra el aviso *Versión reemplazada* con un enlace a la vigente, y oculta enmendar, imprimir y las constancias. La copia impresa del expediente tiene una sección **Enmienda** (versión, firma original y motivo); la receta no muestra el motivo.
- `SignConsultation` es **atómico**: record + recetas + cita `completed` en una sola transacción. La firma bloquea primero la fila de la consulta, así que una segunda firma (doble clic, reintento, otra pestaña) responde 409 `consultation.already_signed` y editar una consulta ya firmada también responde 409; un índice único parcial mantiene un solo expediente original por consulta.
- Diagnósticos en consulta limitados al catálogo de la **versión CIE configurada por cada clínica** (CIE-10 / CIE-11), con autocompletado.
- **Vacunación** según el esquema nacional de El Salvador (MINSAL), para niños, adolescentes y adultos: el carné de cada paciente calcula el estado de cada dosis (aplicada, toca, atrasada, próxima…) a partir de su edad y sus registros; los registros no se editan, uno erróneo se anula con motivo. Una lista de trabajo muestra las dosis atrasadas y próximas de toda la clínica.
- **Aplicaciones en la clínica** (inyecciones, sueros, nebulizaciones…): el médico las indica en la consulta y se vuelven órdenes para enfermería al firmarla; las que llegan sin cita con receta externa registran al médico que receta y su número de JVPM. Cada dosis se registra con lote, sitio y signos vitales, no se edita (una errónea se anula con motivo) y abre una observación (30 min por defecto, configurable por orden) que se cierra "sin reacción" o como reacción adversa, lo que notifica al médico que la indicó. Aplicar un medicamento que choca con las alergias del paciente exige una justificación escrita y auditada.
- **Procedimientos menores** (suturas, biopsias, curaciones, DIU, electrocardiograma…): cada clínica tiene un catálogo configurable, precargado con los más comunes, que dice quién puede realizar cada uno (solo médico, o médico o enfermería), si requiere consentimiento informado, si suele tomar muestra para patología y el control sugerido. Se indican en la consulta (quedan pendientes al firmarla) o se registran directamente, opcionalmente ligados a una cita de procedimiento. Antes de realizarlo: revisión de alergias, anticoagulantes, ayuno y signos vitales; el consentimiento firmado en papel se registra con quién firmó y un testigo (sin archivo). La nota (anestesia, técnica, hallazgos, materiales, complicaciones, indicaciones, muestra enviada a patología) no se edita una vez firmada — las correcciones son enmiendas — y al firmar se sugiere la fecha de control y se notifica al médico que lo indicó si lo realizó otra persona.
- **El contenido clínico de los expedientes es para médicos**: la nota, los diagnósticos, las recetas del expediente, las vacunas, los exámenes, la copia completa, las constancias y el historial clínico requieren `records.read_clinical` (exclusivo de médicos, no delegable). El listado de expedientes está paginado y se filtra en el servidor, y muestra solo metadatos (código, fecha, tipo, médico, sede, estado, paciente; nunca el motivo de consulta, la nota ni los signos vitales). `records.view` cubre ese listado, las recetas, los signos vitales y los documentos. El backend responde 403 `permission.missing` en `GET /records/{id}` a quien no es médico, y cada página del listado queda en la auditoría (`record.listed`, nunca el texto buscado).
- **El contenido de la consulta es del médico**: la nota, los diagnósticos y los borradores (recetas, exámenes, aplicaciones, procedimientos), así como la firma, pertenecen al médico dueño de la consulta. `consultations.edit` es exclusivo de médicos (`DOCTOR_ONLY`, no delegable). Otro médico recibe 403 `consultation.not_own`, otros roles 403 `permission.missing` y la suplantación de soporte 403 `support.clinical_forbidden`. La enfermería registra signos vitales con `consultations.vitals` (delegable, por defecto enfermería), desde **Citas** (el botón *Signos vitales* en las citas en curso) o dentro de la consulta. El admin puede iniciar una consulta pero no abrirla, y solo el médico dueño pasa a la nota. La pantalla de consulta se actualiza cada 30 s para mostrar los signos vitales de enfermería.
- **Auditoría de consultas**: `consultation.viewed` (alcance `full` o `vitals`), `consultation.note_updated`, `consultation.vitals_updated`, `consultation.template_changed` y `consultation.draft_changed` guardan solo nombres de secciones y campos, nunca texto clínico. Las lecturas y las ediciones de nota y vitales de un mismo actor dentro de 10 minutos se agregan por clave, para que el autoguardado y el sondeo no llenen la bitácora.
- **Permisos granulares** validados en la capa de aplicación (no solo en UI) — ver sección siguiente.
- Contraseña temporal con cambio forzado en el primer ingreso: mientras no se reemplace, el backend solo permite cambiarla, ver el perfil y cerrar sesión; cualquier otra cosa responde 403 `auth.password_change_required`. Las sesiones de soporte (impersonación) están exentas.
- **Política de contraseñas** (`domain/services/password_policy.py`, al estilo NIST SP 800-63B) en todos los puntos donde se fija una contraseña — invitar, restablecer (clínica o consola), cambiarla, alta de clínica, script de superadmin: al menos 10 caracteres (máximo 72 bytes, el límite de bcrypt), letras y un número o símbolo, que no sea una contraseña común, nada del nombre, correo o clínica de la persona, y distinta de la actual. Sin caducidad periódica; la fuerza bruta la cubre el bloqueo de inicio de sesión. La UI muestra los requisitos en vivo y genera contraseñas temporales que siempre cumplen.
- Auditoría de accesos y cambios sensibles (HIPAA/GDPR), por tenant y global.

---

## Permisos

El control de acceso es **granular y personalizable por clínica** (`application/common/permissions.py`):

- **Catálogo de 39 permisos** (`Permission`, `StrEnum`) agrupados por recurso: `patients.*`, `appointments.*`, `availability.manage`, `consultations.*`, `records.*` (`view`, y `read_clinical`, `sign` y `amend`, exclusivos de médicos), `prescriptions.manage`, `diagnoses.view`, `insurers.*`, `users.*`, `organization.*`, `locations.manage`, `audit.view`, `permissions.manage`, `vaccinations.*`, `applications.*`, `procedures.*`.
- **4 roles** — `admin`, `doctor`, `nurse`, `receptionist` — con un conjunto de permisos por defecto en `ROLE_PERMISSIONS`.
- **Overrides por tenant**: cada clínica puede personalizar el set de un rol mediante una fila `RolePermissionOverride`. `effective_permissions(role, stored)` resuelve defaults vs. override (e intersecta con el catálogo vigente para tolerar permisos retirados).
- En cada request, la capa de presentación coloca los permisos efectivos en `ActorContext.permissions`, de modo que toda comprobación `ensure_permission(...)` honra la personalización de la clínica.
- **Excepciones por usuario** (planes con la función `user_permissions`, desde Clínica): una persona puede recibir algunos permisos extra o perder algunos de su rol. Se guardan como diferencia con el rol (`PermissionAdjustments` en `User`), así que los cambios posteriores del rol le siguen llegando. Se editan desde **Usuarios → Permisos** (`GET`/`PUT /users/{id}/permissions`). En un plan sin la función, las excepciones guardadas se conservan pero no se aplican. Cambiar el rol de un usuario borra sus excepciones, y los admins conservan siempre el conjunto completo de permisos de su rol.
- **Los módulos contratados condicionan sus permisos**: una clínica sin vacunación, aplicaciones o procedimientos no recibe ninguno de sus permisos, digan lo que digan sus roles.
- `granted(role, stored, modules, adjustments)` combina todo lo anterior; la capa de presentación coloca el resultado en `ActorContext.permissions`.
- El frontend consume el mismo modelo: la UI se condiciona por los permisos efectivos del actor y la pantalla **Roles & Permisos** edita los overrides (router `role_permissions`: `GET`/`PUT`/`DELETE`).

**Salvaguardas** (aplicadas en el backend y reflejadas en la UI):

- El rol `admin` no es personalizable y siempre tiene acceso completo (salvo el contenido clínico de los expedientes y de las consultas, firmar y enmendar; puede iniciar una consulta pero no abrirla).
- `records.sign`, `records.amend`, `records.read_clinical` y `consultations.edit` son exclusivos de médicos: nunca se otorgan a otros roles o usuarios ni se les quitan a los médicos.
- `permissions.manage` es exclusivo de administradores: no se puede delegar a un rol ni a un usuario.
- Solo un admin actúa sobre cuentas de admin o de médico (editar, cambiar rol, desactivar, restablecer contraseña, cerrar sesiones) o asigna esos roles. Un `users.manage` delegado gestiona al resto del personal (enfermería, recepción).
- Nadie gestiona su propia cuenta desde **Usuarios** (cambiar su rol, editarse, suspenderse, reactivarse, restablecer su contraseña o cerrar sus sesiones): su perfil, contraseña y sesiones se gestionan en **Ajustes**. Esto aplica también a los admins.
- Nadie edita sus propios permisos.
- **Último administrador**: ninguna operación (desde la clínica o desde la consola de plataforma) puede dejar una clínica sin admins activos (409 `users.last_admin`), ni siquiera con cambios simultáneos.

**Qué gestiona la clínica y qué gestiona el soporte de Medicore:**

| | Admin de la clínica | Consola de plataforma |
|---|---|---|
| Razón social, NIT, versión CIE | ✅ (`organization.manage`) | ✅ |
| Sedes (crear, renombrar) | ✅ dentro del límite del plan (`locations.manage`) | ✅ mismo límite |
| Zona horaria | solo lectura | ✅ (mueve el "hoy", la agenda y los recordatorios de la clínica) |
| Slug (identificador de inicio de sesión) | solo lectura | fijo desde la creación |
| Plan, módulos, límites, periodo pagado, pagos | solo lectura | ✅ |
| Usuarios, roles, permisos por usuario | ✅ (dentro de los cupos) | acciones de soporte (restablecer contraseña, editar, cambiar rol, suspender, reactivar) |

---

## Suscripciones y planes

Cada clínica tiene una **suscripción** (value object `Subscription` en `Tenant`): plan, módulos opcionales, fecha de pago, indicador de prueba, días de gracia y condiciones especiales (límites a la medida, precio negociado). La activación es manual: las clínicas pagan por transferencia bancaria y el soporte lo registra desde la consola de plataforma.

- **Catálogo de planes** (`plans`, editable en **Planes y precios**): Profesional independiente, Clínica, Clínica Plus y Empresarial (cotización). Cada uno fija límites de médicos, personal de apoyo (enfermería, recepción y administradores adicionales al primero), sedes y almacenamiento, además de funciones (`user_permissions`; `custom_note_templates` desde Clínica Plus) y su **nivel de analítica** (`basic` < `clinic` < `operations`: panel básico, panel de la clínica, métricas operativas).
- **Módulos opcionales** (`addon_pricing`): vacunación, aplicaciones y procedimientos, cada uno con precio mensual y un precio de paquete por los tres; y **analítica avanzada** ($20), que sube la clínica a métricas operativas, se cobra aparte del paquete y no se vende a planes que ya la incluyen (`plan.analytics_included`).
- **Cupos** aplicados en los casos de uso (invitar, cambiar rol, reactivar, nueva sede): crecer por encima del límite se rechaza con `plan.quota_*`; una clínica que ya lo supera (tras bajar de plan) conserva lo que tiene. La comprobación de asientos bloquea la fila de la clínica (`FOR NO KEY UPDATE`), así que dos altas simultáneas no pueden exceder el plan.
- **Pagos y renovación** (`subscription_payments`): registrar un pago extiende el periodo de 1 a 24 meses. Al vencer, la clínica sigue operando durante los días de gracia; después queda en **solo lectura** (`plan.read_only`: puede consultar pero no modificar hasta renovar). La app muestra avisos al acercarse el vencimiento.
- Las clínicas ven su plan, uso e historial de pagos en **Ajustes → Organización**.

La demo pública tiene tres clínicas, una por plan. Los slugs y correos existentes se conservan.

| Clínica (slug) | Plan | Asientos médicos | Asientos de apoyo¹ | Módulos clínicos | Analítica |
|---|---|---|---|---|---|
| Policlínica Escalón (`clinica-demo`) | Clínica Plus | 5/5 | 4/6 | Los tres | Operativa |
| Centro Médico Familiar del Norte (`centro-norte`) | Clínica | 3/3 | 3/3 | Vacunación | Clínica |
| Consultorio Médico Dra. Sofía Alvarenga (`doc-demo`) | Profesional independiente | 1/1 | 1/1 | Ninguno | Básica |

¹ El primer admin no ocupa asiento de apoyo. Escalón incluye una recepcionista invitada.
Sofía atiende a adultos y niños; Yesenia Ramos agenda. Accede con
`sofia.alvarenga@doc-demo.test` o `yesenia.ramos@doc-demo.test`; su admin es `admin@doc-demo.test`.
Las contraseñas siguen saliendo de `DEMO_PASSWORD` y `DEMO_ADMIN_PASSWORD`.

El reset nocturno recrea solo esos tres slugs; conserva las clínicas reales como `clinica-loida`.
Antes de desplegar, confirma que `doc-demo` no esté ocupado en producción (se comprobó ausente el 2026-11-15).
Prueba el seed y `--reset` solo en una BD desechable, nunca en la BD local de trabajo.

---

## Seguridad

- **Sesiones en cookies httpOnly** (`Secure` fuera de desarrollo, con prefijos `__Host-` / `__Secure-`): `mc_session` para clínicas (SameSite=Lax) y `mc_console` para la consola de plataforma (SameSite=Strict, enviada solo a la API de plataforma). El token CSRF (`mc_csrf` / `mc_console_csrf` + cabecera `X-CSRF-Token`) es un HMAC del id de sesión, así que un token de un ámbito no sirve en el otro, y cerrar sesión en una clínica deja intacta la sesión de consola. El token de sesión en sí nunca está al alcance de JavaScript. `Authorization: Bearer` sigue aceptándose para clientes de API.
- **Tokens firmados**: cada tipo de token tiene su propia audiencia (`medicore:tenant`, `medicore:platform`, `medicore:mfa`) y claims obligatorios (`exp`, `iat`, `sub`, `aud`, `scope`, `sid`). Un token de otro tipo responde 401 `auth.wrong_session`, y sus claims se cruzan con la fila de sesión del servidor (usuario, clínica, scope e impersonador). `JWT_ALGORITHM` acepta solo `HS256`, `HS384` o `HS512`. Los tokens emitidos antes de esta versión no tienen audiencia: todos los usuarios, incluidos los superadmins, vuelven a iniciar sesión una vez al desplegarla.
- **Sesiones revocables** (tabla `sessions` + claim `sid`): logout real; cambiar la contraseña cierra las demás sesiones; suspender o resetear un usuario cierra todas; suspender o archivar una clínica cierra todas sus sesiones (también las de soporte). En cada petición se comprueba que la clínica y la cuenta sigan activas, con una sola regla de acceso compartida con el login. Soporte puede abrir una sesión nueva en una clínica suspendida, pero nunca en una archivada.
- **Lockout de login** con tres contadores, todos reservados de forma atómica antes de verificar la contraseña (las peticiones en paralelo no superan los límites):
  - **Por IP**: 30 intentos en 15 min → bloqueo de 15 min (IPv6 se agrupa por /64).
  - **Por cuenta desde una misma IP**: 5 fallos → 1 min, duplicando hasta 15, así el dueño puede entrar desde otra dirección aunque alguien ataque su cuenta.
  - **Por cuenta en total**: 20 intentos en 15 min contra ataques distribuidos; queda exenta una IP desde la que esa cuenta entró bien en los últimos 30 días.
  Un intento bloqueado responde 429 con `Retry-After`; un bloqueo por IP responde igual exista o no la cuenta. Un login correcto borra los fallos de esa cuenta desde esa IP, pero no los totales de la IP ni de la cuenta (solo les devuelve su intento). Reactivar o restablecer la contraseña desde soporte también levanta el bloqueo de login de esa cuenta, no el contador por IP. El segundo factor de la consola mantiene su límite de 5 por superadmin, independiente de la IP. La página Monitoreo muestra también los bloqueos por IP y la IP de los bloqueos por cuenta.
- **Límites de la sesión de consola**: la sesión de la consola de superadmin caduca tras 30 min sin actividad (`PLATFORM_SESSION_IDLE_MINUTES`) y como máximo 8 h después del login (`PLATFORM_SESSION_MAX_MINUTES`). El refresco en segundo plano de Monitoreo no cuenta como actividad, un superadmin desactivado pierde el acceso en la siguiente petición, y `scripts/create_platform_admin.py` revoca las sesiones del admin al actualizarlo.
- **MFA TOTP opcional para superadmins**: se activa desde la consola, en *Seguridad de la cuenta* (`/platform/security`). Con MFA activo, el login de la consola pide la contraseña y después un código de 6 dígitos de una app de autenticación, o un código de recuperación. El desafío es de un solo uso, válido 5 min y va en una cookie httpOnly limitada a `/api/v1/platform/login`. Un código no se puede reutilizar, y tras 5 intentos fallidos el bloqueo es progresivo. Hay 10 códigos de recuperación de un solo uso, mostrados una sola vez y guardados como hash. El secreto TOTP se cifra con AES-256-GCM. Activar MFA, regenerar los códigos de recuperación o desactivarlo exige la contraseña actual, y cada cambio queda en la auditoría de plataforma.
- **Bloqueo al cambiar contraseña**: 5 intentos fallidos con la contraseña actual bloquean nuevos intentos de esa cuenta (429 con `Retry-After`, con backoff). Una contraseña nueva débil no cuenta. Las acciones MFA del superadmin (alta, códigos de recuperación, desactivación) también están limitadas, y Monitoreo muestra estos bloqueos con la cuenta de la clínica.
- **Límites de entrada**: slug ≤ 63 caracteres, email ≤ 254 (guardado en minúsculas y sin espacios, con validación de formato al invitar o crear un usuario: `user.invalid_email`), contraseña ≤ 256, nombres ≤ 255. El user-agent se recorta a 400 y la IP a 45 caracteres en sesiones y auditoría. Los errores de validación (422) ya no devuelven el valor enviado (`input`).
- **Perfil actualizado**: al cargar la app se refresca el perfil del usuario (nombre, rol, permisos, cambio de contraseña pendiente, nombre de la clínica y zona horaria), así que los cambios hechos desde otro lugar se aplican en la siguiente carga.
- **Despliegue recomendado**: sirve la consola de plataforma desde un origen o subdominio propio (p. ej. `console.example.com`), para que un XSS en la app de clínicas no comparta origen con ella. Es una recomendación; la app no lo impone.
- **Sin enumeración**: el login hace el mismo trabajo de hash exista o no la organización o la cuenta (una verificación bcrypt por intento), y un slug o un email inexistente responde igual que una contraseña incorrecta.
- `X-Forwarded-For` solo se honra desde los proxies listados en `TRUSTED_PROXIES`.
- Security headers en la API, `Cache-Control: no-store` en cada respuesta de `/api/` (salvo las que fijan la suya, como las descargas CSV) y CSP estricta en el build del frontend.

Los hallazgos pendientes están en [`docs/BACKLOG.es.md`](docs/BACKLOG.es.md).

---

## Notificaciones y dashboard

- **Notificaciones in-app**: citas creadas, reprogramadas, canceladas o marcadas como no-show (al doctor), documentos subidos (al médico tratante) y altas o cambios de rol de usuarios (a los administradores) y acciones de soporte sobre usuarios de la clínica (a los admins activos y al usuario afectado; la entrada de impersonación, solo a los admins). Campana en la barra superior con contador (sondeo cada 60 s), filtro de no leídas y enlaces directos al elemento, además de una **página de buzón** (`/notifications`) filtrable por estado y categoría y agrupada por día. Se conservan 90 días. Las enmiendas ya no notifican; las notificaciones que generaron antes siguen visibles.
- **Dashboard con datos reales** (`GET /dashboard/summary`): citas de hoy, pendientes, pacientes registrados y ocupación de la agenda, cada uno comparado con la semana anterior, y las próximas citas pendientes a partir de ahora (`GET /appointments/upcoming`). El doctor ve su propia agenda; los demás roles, la clínica completa. Quien puede ver métricas también recibe ahí un **resumen del mes**.

## Métricas de la práctica

`GET /analytics/overview` agrega citas, cobros, aseguradoras, procedimientos, vacunas y aplicaciones: solo conteos y montos, nunca texto clínico. Lo que devuelve depende del **nivel de analítica** de la clínica (las secciones por encima llegan vacías y la interfaz muestra lo que añadiría el plan):

| Nivel | Contenido |
|---|---|
| **Panel básico** | Mes en curso contra los mismos días del mes anterior: consultas atendidas, pacientes nuevos, inasistencia, cancelaciones e ingreso estimado |
| **Panel de la clínica** | Cualquier periodo (esta semana, este mes, mes anterior, últimos 90 días, rango personalizado de hasta un año), tabla y filtro por médico, tendencia de 12 semanas, tipos de cita y aseguradoras |
| **Métricas operativas** | Mapa de calor día × hora, anticipación con que agendan, pacientes que regresan vs. primera vez y actividad de los módulos |

- **Quién ve qué**: `analytics.own` (las citas propias de un médico), `analytics.clinic` (toda la clínica) y `analytics.money` (ingresos en las métricas que puede ver). El ingreso es el cobro registrado en consultas atendidas y procedimientos realizados, no dinero recibido.
- **Modelo de la clínica** (`tenants.practice_model`, en **Roles y permisos**): *médicos asociados* (por defecto: cada médico pone sus precios y ve sus ingresos; la administración ve la actividad sin dinero) o *médicos empleados* (la administración pone los precios y ve los ingresos; los médicos ven sus métricas sin dinero). Cambiarlo solo mueve los valores por defecto de tarifas e ingresos; el resto de un rol personalizado se conserva, y el cambio queda auditado (`organization.practice_model_changed`).

### Reportes

`GET /reports/{kind}?start=&end=` devuelve las filas detrás de las métricas en dos tablas (resumen y detalle), con las mismas reglas de alcance y dinero; `GET /reports/{kind}/csv` descarga cualquiera de las dos (`part=detail|summary`) en español o inglés (UTF-8 con BOM, fechas ISO, montos simples; el texto que parece una fórmula se neutraliza). Descargar requiere `reports.export` (administradores y médicos por defecto) y queda auditado como `report.exported` con el reporte, el periodo y el número de filas, nunca las filas.

| Reporte | Resumen | Detalle |
|---|---|---|
| **Citas** | Por estado | Todas las citas del periodo (nunca el motivo) |
| **Ingresos** (requiere `analytics.money`) | Por médico: consultas, procedimientos, ingreso | Consultas atendidas y procedimientos realizados con precio de lista, cobro y nota |
| **Aseguradoras** | Consultas atendidas (e ingreso) por aseguradora, particulares al final | Consultas con seguro, para cobrar a cada aseguradora |
| **Inasistencias y cancelaciones** | Por médico: agendadas, no asistió, canceladas | Citas perdidas con el teléfono del paciente |
| **Vacunación** (módulo) | Dosis por vacuna y dosis según grupos de edad del MINSAL | Dosis aplicadas en la clínica (no los registros de dosis aplicadas en otro lugar) |
| **Procedimientos** (módulo) | Por tipo de procedimiento | Procedimientos realizados, marcando los incluidos en la consulta |
| **Aplicaciones** (módulo) | Dosis por medicamento | Dosis aplicadas (sin las rechazadas o anuladas) |

El nivel básico genera reportes del mes en curso o del anterior; desde el nivel clínica, cualquier periodo de hasta un año.

---

## Notas clínicas

La nota de la consulta se escribe con una **plantilla**, no con un SOAP fijo. Incluidas: **SOAP**, **P-SOAP** (orientada a problemas, criterio de auditoría del ISSS; su sección *Problemas* parte de las condiciones del paciente), **Historia clínica completa** (primera consulta), **Nota de evolución** (controles) y **Narrativa** (texto libre). Cada sección tiene un *rol* (subjetivo, objetivo, análisis, plan, antecedentes, problemas, libre): al cambiar de plantilla en plena consulta el texto se conserva —lo que no tiene sección equivalente queda bajo su título anterior— y el rol *plan* alimenta las indicaciones generales de la receta, se llame como se llame la sección.

En **Ajustes → Notas clínicas** el administrador habilita plantillas, elige la predeterminada, define una por tipo de cita y para la **primera consulta** del paciente en la clínica, y puede hacer el formato **obligatorio**. La consulta se abre con: regla de primera consulta → regla del tipo de cita → **formato preferido** del médico (si no es obligatorio) → predeterminado de la clínica. En el plan de médico independiente lo configura el propio médico. El expediente firmado guarda la plantilla y los títulos con que se escribió, y las enmiendas editan sus secciones. La completitud (y el mínimo de 60% para firmar) cuenta las secciones obligatorias de la plantilla.

Desde **Clínica Plus**, la clínica puede crear **plantillas propias** (hasta 12 secciones, cada una con título, rol y si es obligatoria). Aparecen junto a las incluidas en los formatos habilitados, las reglas y el preferido del médico. Editarlas no cambia las notas ya escritas, que guardan su versión; eliminarlas las retira de los ajustes sin tocar expedientes ni consultas en curso. Si la clínica baja de plan, dejan de ofrecerse.

---

## Documentos imprimibles

Todo documento se imprime desde el navegador (`/print/:kind/:id`; "Guardar como PDF" también funciona) con el encabezado de la clínica, los datos del paciente y el nombre y número de **JVPM** del médico. El tamaño de papel (**media carta** por defecto, o carta) y el papel membretado (el encabezado se deja en blanco) se configuran en **Ajustes → Organización → Impresión** y se pueden cambiar al imprimir.

| Documento | Dónde | Notas |
|---|---|---|
| **Receta** | Consulta firmada (al firmar, en el expediente, en las recetas del paciente) | Incluye el *plan* de la nota como "Indicaciones generales" solo si el médico lo escribió (se puede omitir al imprimir). Quien no tiene `records.read_clinical` (enfermería, admin) la imprime sin ellas |
| **Orden de exámenes** | Consulta firmada | Exámenes indicados en la consulta (laboratorio, imagen, otros) con atajos de los más comunes. Requiere `records.read_clinical` |
| **Constancia médica** | Consulta firmada — solo la emite el médico que la firmó | Reposo/incapacidad (hasta 90 días, con fechas) o asistencia (horario de la consulta); diagnóstico solo si el paciente lo autoriza; código `CM-{año}-{n}`, reimprimible y anulable con motivo. Listar e imprimir requiere `records.read_clinical` |
| **Copia de expediente** | Consulta firmada | Signos vitales, la nota clínica en su plantilla, diagnósticos, recetas, vacunas y exámenes. Requiere `records.read_clinical` |
| **Procedimiento** | Detalle del procedimiento | Indicaciones de cuidado, consentimiento para firmar en papel, solicitud de patología |
| **Carné de vacunación** | Paciente → Vacunas | Dosis aplicadas y próximas |
| **Comprobante de cita** | Citas | Fecha, médico, tipo y lugar — **nunca el precio** |
| **Agenda del día** | Agenda (vista de día) | El día de un médico |

Cada impresión queda en la auditoría (`document.printed`, con el documento y el paciente); las constancias además registran `certificate.issued` / `certificate.voided`.

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
│   ├── migrations/           # 37 migraciones Alembic
│   ├── scripts/
│   │   ├── seed_demo.py            # Datos demo: ~8 semanas de historia + 4 de agenda, vía casos de uso
│   │   ├── import_icd.py           # Carga del catálogo CIE-10/CIE-11
│   │   ├── create_platform_admin.py # Alta de superadmin de plataforma
│   │   ├── reset_platform_mfa.py    # Desactiva el MFA de un superadmin (dispositivo perdido)
│   │   └── purge_expired_sessions.py # Borra sesiones caducadas o revocadas (tarea diaria)
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
        │                     # + 21 módulos por recurso
        ├── stores/           # Zustand: auth + platformAuth + ui (tema/idioma/sidebar)
        ├── lib/              # i18n ES/EN, formato, QueryClient, notificaciones, timezones…
        ├── types/            # Tipos TS espejo del dominio backend
        ├── components/       # ui/ + shell/ (topbar, campana de notificaciones…)
        │                     # + appointments/ + audit/ + patients/ + permissions/
        │                     # + records/ + settings/ + vaccination/ + applications/
        │                     # + procedures/ + analytics/
        │                     # + guards (RequireAuth…)
        └── pages/            # 25 pantallas de clínica (Login, Dashboard, Analytics, Reports,
                              # Patients, PatientDetail, Appointments, Schedule,
                              # Consultation, Records, Availability, Insurers, Fees,
                              # Users, Settings, Audit, Permissions, Notifications,
                              # ChangePassword, Vaccination, Applications, Procedures,
                              # ProcedureDetail, ProcedureCatalog, Print)
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
| **18** | Tarifas: precio por médico y tipo de cita, precio en el catálogo de procedimientos, copia del precio en cada cita y procedimiento, ajustes de cobro con motivo, procedimientos incluidos en la consulta, permisos `fees.manage_own` / `fees.manage_all` | ✅ Completada |
| **19** | Niveles de analítica por plan (panel básico, de la clínica, métricas operativas) y complemento de analítica avanzada | ✅ Completada |
| **20** | Métricas de la práctica por nivel (comparación de periodos, por médico, tendencia semanal, tipos, aseguradoras, mapa de calor, anticipación, pacientes que regresan, módulos), permisos `analytics.*` y modelo de la clínica (médicos asociados o empleados) | ✅ Completada |
| **21** | Impresión: receta (con indicaciones generales), órdenes de exámenes, constancias médicas (reposo/asistencia, anulables), copia de expediente, documentos de procedimientos, carné de vacunación, comprobante de cita sin precio y agenda del día; media carta o carta, papel membretado, JVPM del médico, cada impresión auditada | ✅ Completada |
| **22** | Reportes con exportación CSV (citas, ingresos, aseguradoras, inasistencias, vacunación por grupos de edad del MINSAL, procedimientos, aplicaciones), permiso `reports.export`, exportaciones auditadas | ✅ Completada |
| **23** | Plantillas de nota clínica (SOAP, P-SOAP con problemas desde las condiciones del paciente, historia completa, evolución, narrativa), reglas de la clínica por tipo de cita y primera consulta, formato obligatorio, formato preferido del médico, el texto se conserva al cambiar; pantalla de consulta con completitud en vivo, lo que falta para firmar, contexto del paciente y autoguardado seguro | ✅ Completada |
| **24** | Plantillas de nota propias de la clínica (Clínica Plus y superiores): editor de secciones con rol y obligatoriedad, versiones conservadas en las notas escritas, auditoría, característica de plan editable desde la plataforma | ✅ Completada |
| — | Notificaciones por email/SMS y recordatorios de citas | 🗓️ A futuro |
| — | Inventario de lotes de vacunas y recordatorios de vacunación | 🗓️ A futuro |
| — | Aplicaciones: catálogo de medicamentos frecuentes, constancia imprimible de la aplicación, inventario y facturación | 🗓️ A futuro |
| — | Procedimientos: seguimiento del resultado de patología, salas/equipo, inventario y facturación | 🗓️ A futuro |

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
.venv/bin/pytest                          # suite completa (1602 tests)
.venv/bin/pytest tests/domain/            # solo tests de dominio
.venv/bin/ruff check src tests            # lint (--fix para corregir)

# Migraciones
.venv/bin/alembic upgrade head            # aplicar migraciones pendientes
.venv/bin/alembic revision --autogenerate -m "descripción"  # nueva migración
```

---

## Base de datos

**34 tablas**, creadas por la migración inicial (`a622afdfaa21`) y ampliadas por las migraciones posteriores:

| Tabla | Descripción |
|---|---|
| `tenants` + `locations` | Organización / clínica y sus sedes |
| `users` + `doctor_profiles` | Cuentas de acceso y perfil clínico |
| `sessions` | Sesiones activas (revocables) de clínica, soporte y plataforma |
| `login_attempts` | Contador de fallos de login para el lockout |
| `patients` | Pacientes (datos demográficos, médico asignado, etiquetas, alergias) |
| `appointments` | Citas con FSM de estado y su cobro (tarifa vigente al agendar, monto cobrado y motivo del ajuste) |
| `doctor_fees` | Tarifa de cada médico por tipo de cita (USD) |
| `consultations` | Consulta en curso (borrador mutable) |
| `medical_records` | Historiales firmados e inmutables (como máximo un original por consulta y una enmienda por expediente); indexado por `(tenant_id, encounter_at)` para el listado de expedientes |
| `prescriptions` | Recetas emitidas |
| `medical_documents` | Archivos médicos (metadata) |
| `insurers` | Aseguradoras de la clínica |
| `doctor_availability` + `availability_exceptions` | Horario + excepciones |
| `notifications` | Notificaciones in-app (payload JSONB) |
| `audit_logs` | Trazabilidad HIPAA/GDPR por tenant |
| `tenant_counters` | Contadores para códigos legibles (`P-00142`, `A-2401`…) |
| `vaccination_records` | Dosis de vacunas registradas (esquema nacional) |
| `application_orders` + `application_records` | Órdenes de aplicación en la clínica y las dosis aplicadas |
| `procedure_types` + `procedures` | Catálogo de procedimientos por clínica (con precio) y los procedimientos indicados/realizados, con su cobro o incluidos en la consulta |
| `role_permission_overrides` | Personalización de permisos por rol y tenant |
| `plans` + `addon_pricing` | Catálogo de planes y precios de módulos opcionales (global) |
| `subscription_payments` | Pagos registrados por clínica (renovaciones) |
| `diagnosis_codes` | Catálogo CIE-10/CIE-11 (global, para autocompletado) |
| `platform_admins` | Superadmins de la plataforma |
| `platform_admin_recovery_codes` | Códigos de recuperación de un solo uso (hash) de superadmins con MFA |
| `platform_audit_logs` | Auditoría global de operaciones de plataforma |
| `error_events` | Errores inesperados del servidor (ruta, tipo, ubicación y commit; sin datos de pacientes; 30 días) |
| `job_runs` | Ejecuciones de tareas programadas (p. ej. el reset nocturno de la demo) y su resultado |
| `request_stats` | Peticiones a la API por hora y plantilla de ruta: volumen, 4xx/5xx e histograma de latencia (30 días) |

---

## Tests

Casi toda la suite es **independiente de la base de datos** — usa adaptadores en memoria que ejercen el mismo contrato multi-tenant que los repos SQLAlchemy. Los tests de infraestructura corren contra **PostgreSQL real** dentro de una transacción que siempre se revierte, y se saltan si no hay base de datos disponible.

```
1602 tests en verde
   319  — dominio (VOs, FSM, slot_resolver, Consultation.sign, MedicalRecord.amend,
            esquema de vacunación, aplicaciones, procedimientos, cruce de alergias)
   721  — aplicación (auth, sesiones, citas, consultas, records y enmiendas, notificaciones, dashboard,
            plataforma (las acciones de soporte quedan en la auditoría de la clínica y se notifican), permisos granulares, aislamiento multi-tenant)
   378  — presentación (endpoints HTTP: auth guards, CSRF, booking, lifecycle, 403 por
            permiso, códigos de error, validación, plataforma)
    184  — infraestructura (repositorios SQLAlchemy contra PostgreSQL, incluida la cadena de enmiendas)
```

Los tests verifican, entre otras cosas:
- Atomicidad de `SignConsultation`: un fallo revierte record, recetas y estado de cita. Las firmas concurrentes de una consulta dejan un único record.
- Solo los médicos leen el contenido clínico de los expedientes; el listado pagina y filtra en el servidor.
- Consultas: solo el médico dueño lee o edita una consulta, la enfermería solo escribe signos vitales, admin y soporte no leen contenido clínico, y la auditoría guarda nombres y no texto.
- Aislamiento multi-tenant: los repos de un tenant no filtran datos de otro.
- Permisos efectivos por rol y override por tenant, y de scope de plataforma.
- Revocación de sesiones, protección CSRF y caducidad de la sesión de consola.
- Lockout de login por IP y por cuenta, con reservas concurrentes contra PostgreSQL.
- Una clínica nunca se queda sin administrador.
- MFA TOTP de la consola (vectores RFC 6238, anti-replay, recuperación).
- Que todo código de error del backend tenga traducción en español e inglés.

---

## Variables de entorno (backend)

| Variable | Descripción | Default |
|---|---|---|
| `ENVIRONMENT` | `development` o `production`. En producción se activan validaciones estrictas. | `development` |
| `DATABASE_URL` | URL de conexión PostgreSQL (psycopg3) | `postgresql+psycopg://localhost/medicore` |
| `JWT_SECRET` | Clave HMAC para tokens. **Obligatoria en producción, de al menos 32 bytes** (`openssl rand -hex 32`); la app no arranca sin ella | `change-me` (solo dev) |
| `JWT_ALGORITHM` | Algoritmo JWT: solo `HS256`, `HS384` o `HS512` | `HS256` |
| `JWT_EXPIRE_MINUTES` | Expiración del token en minutos | `1440` (24 h) |
| `JWT_SUPPORT_EXPIRE_MINUTES` | Expiración (min) de sesiones de impersonación/soporte — más corta por seguridad | `60` (1 h) |
| `COOKIE_SECURE` | Flag `Secure` y prefijos `__Host-` / `__Secure-` en las cookies de sesión. Sin definir = activas en todo salvo `development`. No puede ser `false` en producción. | según `ENVIRONMENT` |
| `PLATFORM_SESSION_IDLE_MINUTES` | Caducidad por inactividad de la sesión de la consola (min, entre 5 y el máximo) | `30` |
| `PLATFORM_SESSION_MAX_MINUTES` | Duración absoluta de la sesión de la consola (min) | `480` (8 h) |
| `PLATFORM_COOKIE_PATH` | Ruta de la cookie de sesión de la consola (solo se envía a la API de plataforma) | `/api/v1/platform` |
| `MFA_ENCRYPTION_KEY` | Clave que cifra los secretos TOTP de los superadmins (AES-256-GCM): 32 bytes en base64url. **Obligatoria en producción** (la app no arranca sin ella). En desarrollo, si está vacía, se deriva de `JWT_SECRET`. Si se pierde, los MFA ya activados no se pueden verificar. Generarla: `python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"` | vacío |
| `MFA_ISSUER` | Nombre que muestra la app autenticadora junto al código | `Medicore` |
| `CORS_ORIGINS` | Orígenes permitidos (coma-separados); `*` solo en desarrollo | `*` |
| `ENABLE_DOCS` | Exponer Swagger/OpenAPI en `/api/v1/docs` | `true` (dev) / `false` (prod) |
| `TRUSTED_PROXIES` | IPs/CIDRs de reverse-proxies cuyo `X-Forwarded-For` se honra; vacío → IP del socket | vacío |
| `SOURCE_COMMIT` | Commit desplegado, que muestra la página de Monitoreo | vacío |
| `DEMO_PASSWORD` | Contraseña de los usuarios demo que crea `scripts/seed_demo.py` (≥ 8 caracteres). **Obligatoria en producción**, donde se rechaza la contraseña pública por defecto | `demo1234` (solo dev) |
| `DEMO_ADMIN_PASSWORD` | Contraseña de los admins de clínica de la demo (≥ 8 caracteres), privada para que la contraseña compartida no abra la administración. **Obligatoria en producción** y distinta de `DEMO_PASSWORD` | `DEMO_PASSWORD` |

> En **producción** (`ENVIRONMENT=production`) la app **falla al arrancar** si `JWT_SECRET` sigue siendo el default inseguro o tiene menos de 32 bytes, o si `CORS_ORIGINS` es `*`, `COOKIE_SECURE` es `false` o `MFA_ENCRYPTION_KEY` está vacía; además los docs quedan desactivados salvo `ENABLE_DOCS=true` explícito. En desarrollo no se valida y los defaults funcionan tal cual.

---

## Despliegue

El backend incluye un `Dockerfile` listo para producción (usuario no-root, uvicorn en el puerto 8000). El frontend se sirve como estático (`dist/`) en el mismo origen tras un reverse-proxy, o en un host separado con `VITE_API_BASE_URL` definido al hacer el build. Pasos detallados en [`backend/README.es.md`](backend/README.es.md) y [`frontend/README.es.md`](frontend/README.es.md).

### Despliegue con Docker Compose / Coolify

El [`docker-compose.yml`](docker-compose.yml) de la raíz levanta todo el stack en un **único origen**: `db` (PostgreSQL 16, volumen persistente), `backend` (aplica `alembic upgrade head` al arrancar) y `frontend` (nginx que sirve el SPA, redirige `/api/` al backend y agrega las cabeceras de seguridad). Solo `frontend` lleva dominio público; el TLS lo termina el proxy de borde (Traefik en Coolify).

1. Genera los secretos: `openssl rand -hex 32` (`JWT_SECRET`, al menos 32 bytes) y `openssl rand -base64 24` (`POSTGRES_PASSWORD`), la clave MFA (`MFA_ENCRYPTION_KEY`, comando en la tabla de variables de entorno del backend), y elige `DEMO_PASSWORD` (la que compartes con quien prueba la demo) y `DEMO_ADMIN_PASSWORD` (privada, para los admins de clínica).
2. En Coolify: **New Resource → Public Repository** → este repo, rama `main`, **Build Pack: Docker Compose**, archivo `/docker-compose.yml`.
3. Variables de entorno: `POSTGRES_PASSWORD`, `JWT_SECRET`, `APP_ORIGIN` (p. ej. `https://medicore.ejemplo.com`), `DEMO_PASSWORD`, `DEMO_ADMIN_PASSWORD` y `MFA_ENCRYPTION_KEY`. Opcionales: `POSTGRES_DB`, `POSTGRES_USER`, `ENABLE_DOCS`, `JWT_EXPIRE_MINUTES`, `WEB_CONCURRENCY` (workers de uvicorn, por defecto 2). Si falta una obligatoria el stack no arranca, a propósito.
4. Asigna el dominio solo al servicio **frontend** y pulsa **Deploy**.
5. Carga inicial de datos (una vez), en una terminal del contenedor `backend`:
   ```sh
   python scripts/import_icd.py cie11 data/cie11.csv
   python scripts/import_icd.py cie10 data/cie10.csv
   python scripts/seed_demo.py            # --reset para actualizar las fechas de la demo
   python scripts/create_platform_admin.py <correo> "<nombre>" '<contraseña>'
   ```

Los redeploys conservan los datos (volumen `medicore-pgdata`) y aplican las migraciones nuevas al arrancar.

> **Nota:** la migración `d0e1f2a3b4c6` (límites de la sesión de consola) hace que los usuarios de clínica y los superadmins vuelvan a iniciar sesión una vez tras desplegar.

> **Antes de desplegar esta versión:** `MFA_ENCRYPTION_KEY` tiene que llegar al servicio `backend`. Defínela en Coolify y declárala en `docker-compose.yml` (`MFA_ENCRYPTION_KEY: ${MFA_ENCRYPTION_KEY:?set MFA_ENCRYPTION_KEY}`), porque en producción la app no arranca sin ella. La migración `e1f2a3b4c5d7` añade las columnas de MFA a `platform_admins` y la tabla `platform_admin_recovery_codes`.

> **Antes de desplegar esta versión:** todos los usuarios, incluidos los superadmins, vuelven a iniciar sesión una vez: los tokens emitidos antes no tienen audiencia.
>
> **Migración `f2a3b4c5d6e8`:** añade `last_success_at` a `login_attempts` (lockout de login). No requiere variables de entorno nuevas.
>
> **Migración `a3b4c5d6e7f9`:** añade un índice único parcial para que una consulta tenga como máximo un expediente original. **Antes de desplegar, ejecuta la consulta de detección de [`backend/README.es.md`](backend/README.es.md#expedientes-duplicados-por-doble-firma)**: la migración se niega a correr mientras existan duplicados (lista solo sus ids) y nunca los resuelve por sí misma. Crear el índice bloquea escrituras en `medical_records` un instante. El entrypoint de Docker ejecuta `alembic upgrade head`, así que la migración se aplica al desplegar.

> **Migración `c4d5e6f7a8b0`:** añade el índice `ix_records_tenant_encounter` sobre `medical_records(tenant_id, encounter_at)` para el listado de expedientes, y otorga `records.read_clinical` al rol médico de las clínicas que lo habían personalizado. Crear el índice bloquea escrituras en `medical_records` un instante. Su downgrade quita el permiso de las personalizaciones del médico y elimina el índice.

> **Migración `d5e6f7a8b9c1`** (autoría de la consulta): devuelve `consultations.edit` a los roles médicos personalizados y elimina las revocaciones de `edit` a médicos; en roles y usuarios de enfermería y recepción, `consultations.edit` pasa a `consultations.vitals` (si quedan a la vez concedido y revocado, gana la revocación; admin no se toca). **Antes de desplegar, respalda `role_permission_overrides` y la tabla `users` (columna `permission_adjustments`).** Su downgrade convierte `vitals` de nuevo en `edit`, pero no restaura las revocaciones de los médicos.

> **Cambios visibles para los usuarios en esta versión** (avísalos a las clínicas): admin y enfermería ya no ven el motivo de consulta en Expedientes ni en el resumen del paciente; en Expedientes la columna Motivo pasa a Médico y solo el médico puede abrir un expediente; la línea de medicación muestra al médico que la prescribió en vez del código del expediente; admin y enfermería reimprimen recetas sin indicaciones; las pestañas abiertas con la versión anterior fallan en Expedientes hasta recargarlas. Enfermería solo registra signos vitales en la consulta en curso, y admin ya no puede abrirla: solo el médico que la inició pasa a la nota. Para clientes de la API: `POST /consultations/start/{id}` ya no devuelve la nota (devuelve una referencia mínima). Enmiendas de expedientes: solo su autor puede enmendarlo, desde la versión vigente y con un motivo de 10 a 1000 caracteres (`POST /records/{id}/amend` recibe `reason` y rechaza campos desconocidos); los listados de expedientes y el resumen del paciente muestran solo versiones vigentes, así que sus totales pueden bajar respecto a antes; las enmiendas ya no notifican al autor.

Para una demo pública, agrega en Coolify una **Scheduled Task** nocturna en el contenedor `backend` que ejecute `python scripts/seed_demo.py --reset` (p. ej. `0 9 * * *`, las 03:00 en El Salvador): deshace lo que hayan cambiado los visitantes, evita que se acumulen datos y mueve las fechas al día actual. No toca el catálogo CIE ni los superadmins de la plataforma. Cada ejecución queda registrada y la página *Monitoreo* marca la tarea si falla o si pasan más de 26 h sin un reset exitoso.

En cualquier entorno, agrega además una **Scheduled Task** diaria en el contenedor `backend` que ejecute `python scripts/purge_expired_sessions.py` (p. ej. `30 9 * * *`). Borra las sesiones que ya no pueden iniciar sesión (caducadas o revocadas, de clínicas, de la consola y de desafíos de segundo paso). Cada ejecución queda registrada como el job `session_purge`, y Monitoreo la marca si pasan más de 26 h sin una ejecución exitosa.

**Monitoreo.** La página *Monitoreo* de la consola solo carga si la API responde, así que para enterarte de una caída configura un monitor externo (UptimeRobot, Better Stack…) contra `https://<tu-dominio>/api/v1/health/ready`: responde `200` si la API y la base de datos están bien y `503` si la base de datos no responde. El commit desplegado que muestra la página sale de `SOURCE_COMMIT`, que Coolify inyecta en el contenedor. No la declares en el compose: Coolify bloquea las variables del compose y una vacía taparía la suya. Fuera de Coolify, defínela tú; si falta, la página lo indica.

---

## Backlog y planes a futuro

El trabajo diferido, los hallazgos de seguridad pendientes y la funcionalidad planificada a futuro (notificaciones por email/SMS, recordatorios de citas) están en [`docs/BACKLOG.es.md`](docs/BACKLOG.es.md).
