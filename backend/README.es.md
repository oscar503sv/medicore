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
**20 grupos de casos de uso** y **26 routers / 183 endpoints** bajo `/api/v1/`.

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
  **enmienda** (nuevo registro con `status=amended` que referencia al original). Solo el autor del expediente lo enmienda, solo su versión vigente, y siempre con un motivo; las versiones forman una sola cadena (`amends_record_id` es único) y cada versión guarda quién la firmó (`signed_by_id`, `signed_at`).

## Funcionalidades

- **Autenticación** por JWT con roles (`admin`, `doctor`, `nurse`, `receptionist`) y cambio de
  contraseña forzado en el primer ingreso (hasta entonces solo se permiten el cambio, el perfil y cerrar sesión; el resto responde 403 `auth.password_change_required`; las sesiones de soporte están exentas). La sesión viaja en una **cookie httpOnly**
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
- **Tokens firmados**: cada tipo de token lleva su propia audiencia (`medicore:tenant`, `medicore:platform`, `medicore:mfa`) y los claims obligatorios `exp`, `iat`, `sub`, `aud`, `scope` y `sid`. Un token de otro tipo responde 401 `auth.wrong_session`, y sus claims se cruzan con la fila de sesión (usuario, clínica, scope, impersonador). `JWT_ALGORITHM` acepta solo `HS256`, `HS384` o `HS512`. Los tokens emitidos antes de esta versión no tienen audiencia: todos los usuarios, incluidos los superadmins, vuelven a iniciar sesión una vez al desplegar.
- **Límites de la sesión de consola**: la sesión de la consola de superadmin caduca tras 30 min sin actividad y como máximo 8 h después del login (`PLATFORM_SESSION_IDLE_MINUTES` / `PLATFORM_SESSION_MAX_MINUTES`). El refresco en segundo plano de Monitoreo no cuenta como actividad, y un superadmin desactivado pierde el acceso en la siguiente petición.
- **MFA TOTP opcional para superadmins**: se activa desde la consola, en *Seguridad de la cuenta* (`/platform/security`). Con MFA activo, el login de la consola pide la contraseña y después un código de 6 dígitos de una app de autenticación, o un código de recuperación. El desafío es de un solo uso, válido 5 min y va en una cookie httpOnly limitada a `/api/v1/platform/login`. Un código no se puede reutilizar, y tras 5 intentos fallidos el bloqueo es progresivo. Hay 10 códigos de recuperación de un solo uso, mostrados una sola vez y guardados como hash. El secreto TOTP se cifra con AES-256-GCM. Activar MFA, regenerar los códigos de recuperación o desactivarlo exige la contraseña actual, y cada cambio queda en la auditoría de plataforma.
- **Lockout de login** con tres contadores: por IP (30 intentos en 15 min → bloqueo de 15 min, IPv6 por /64); por cuenta desde una misma IP (5 fallos → 1 min, duplicando hasta 15); por cuenta en total (20 intentos en 15 min, exenta una IP que entró bien a esa cuenta en los últimos 30 días). Cada intento se reserva de forma atómica antes de verificar la contraseña. Los intentos bloqueados reciben HTTP 429 + `Retry-After`; un bloqueo por IP responde igual exista o no la cuenta, para no revelar cuáles existen. Un login correcto solo borra los fallos de esa cuenta desde esa IP. Reactivar o restablecer la contraseña desde soporte también levanta el bloqueo de login de esa cuenta, no el contador por IP. El segundo factor de la consola mantiene su límite de 5 por superadmin. El cambio de contraseña tiene su propio bloqueo: 5 intentos fallidos con la contraseña actual bloquean esa cuenta (429 con `Retry-After`, con backoff); una contraseña nueva débil no cuenta. Las acciones MFA del superadmin (alta, códigos de recuperación, desactivación) también están limitadas.
- **Límites de entrada**: slug ≤ 63, email ≤ 254 (en minúsculas y sin espacios, con validación de formato al invitar o crear: `user.invalid_email`), contraseña ≤ 256, nombres ≤ 255; user-agent recortado a 400 e IP a 45 caracteres en sesiones y auditoría. Las respuestas 422 ya no devuelven el valor enviado (`input`).
- **Respuestas**: toda respuesta de `/api/` lleva `Cache-Control: no-store`, salvo las que fijan la suya (como las descargas CSV).
- **Cupos del plan**: la comprobación de asientos bloquea la fila de la clínica (`FOR NO KEY UPDATE`), así que dos altas simultáneas no exceden el plan.
- **Último administrador**: ninguna operación (desde la clínica o desde la consola de plataforma) puede dejar una clínica sin admins activos (409 `users.last_admin`), ni siquiera con cambios simultáneos.
- **Permisos granulares** (`application/common/permissions.py`): catálogo de **39 permisos**
  (`Permission`, `StrEnum`), un set por defecto por rol (`ROLE_PERMISSIONS`) y **overrides por
  tenant** vía `RolePermissionOverride`. `effective_permissions(role, stored)` resuelve defaults
  vs. override e intersecta con el catálogo vigente; la capa de presentación los coloca en
  `ActorContext.permissions`, de modo que cada `ensure_permission(...)` honra la personalización
  de la clínica. Router `role_permissions` (`GET`/`PUT`/`DELETE`) para administrarlos. Cambiar el rol de un usuario borra sus excepciones por usuario; los admins conservan siempre el conjunto completo de su rol.
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
  recetas, y se completa la cita, todo en una transacción. La firma bloquea la fila de la consulta
  antes de validar y de tomar el número de expediente, así que las firmas y ediciones concurrentes
  de una misma consulta se serializan: una segunda firma, o editar una ya firmada, responde 409
  (`consultation.already_signed`); un autoguardado tardío no puede devolverla a borrador, y iniciar
  dos veces la misma cita devuelve la misma consulta.
- **Acceso a la consulta** (`application/use_cases/consultations.py`): la nota, los diagnósticos y los borradores son del médico dueño (`consultations.edit` es `DOCTOR_ONLY`). Otro médico recibe 403 `consultation.not_own`, otros roles 403 `permission.missing` y la suplantación de soporte 403 `support.clinical_forbidden`; el admin puede iniciar una consulta pero no leerla ni modificarla. La enfermería escribe vitales con `consultations.vitals` (delegable, por defecto enfermería): `GET /consultations/by-appointment/{appointment_id}/vitals` responde 404 `consultation.not_started` si la cita aún no tiene consulta, y `PUT /consultations/{id}/vitals` acepta actualizaciones parciales (un campo enviado como `null` se limpia; una consulta firmada responde 409 `consultation.already_signed`). `POST /consultations/start/{appointment_id}` responde una referencia mínima (`id`, `appointment_id`, `patient_id`, `doctor_id`, `status`, `started_at`) sin la nota, y `PATCH /autosave` fusiona los vitales campo a campo.
- **Lectura de expedientes** (`application/use_cases/records.py`, router `records`): el contenido clínico de un expediente (nota, diagnósticos, recetas, vacunas, exámenes, copia completa, constancias e historial clínico) requiere `records.read_clinical`, permiso exclusivo de médicos y no delegable (`DOCTOR_ONLY`); a los demás les responde 403 `permission.missing`. `GET /records` está paginado (`{items, total, offset, limit}`, 25 por defecto, 100 como máximo) y filtra en el servidor: `patient_id`, `type`, `date_from`/`date_to` (días de la clínica) y `q` (código del expediente, nombre o código del paciente); un rango invertido responde 400 `records.invalid_range`. Devuelve solo metadatos (sin motivo de consulta, nota ni signos vitales) y lo respalda el índice `ix_records_tenant_encounter`. Endpoints nuevos: `GET /patients/{id}/records` (historial clínico, solo médicos) y `GET /patients/{id}/vitals` (`records.view`); `GET /patients/{id}` añade `latest_vitals` y `recent_records` (hasta 6, solo metadatos). Auditoría: `record.listed` (cada página; nunca el texto buscado), `record.viewed`, `record.history_viewed`, `patient.vitals_listed`, `prescription.listed` y `document.listed`. En impresión, `GET /print/records/{id}` incluye `document`; para quien no es médico la receta sale sin indicaciones generales, y la copia completa, la orden de exámenes y las constancias (listar e imprimir) requieren `records.read_clinical`.
- **Enmiendas de expedientes** (`application/use_cases/records.py`, router `records`): `POST /records/{id}/amend` recibe `{reason, chief_complaint?, note?}` y rechaza los campos desconocidos (422). Solo el autor del expediente lo enmienda (403 `record.not_own`; las sesiones de soporte reciben 403 `support.clinical_forbidden`), y solo la versión vigente (409 `record.superseded`, con `params.current_id`). Una enmienda sin cambios responde 422 `record.amend_empty`; un motivo fuera de 10 a 1000 caracteres responde 422 `record.amend_reason_invalid` (`params.min`, `params.max`). El motivo se guarda en la versión (`amendment_reason`) y se muestra en el historial y en la copia impresa, pero queda fuera de la auditoría, que registra las secciones cambiadas (`changed`) y la longitud del motivo (`reason_chars`), porque los administradores la leen sin acceso clínico. La comprobación y la inserción corren bajo un lock de fila, y un índice único parcial `uq_medical_records_amends` sobre `amends_record_id` lo respalda. La vigencia se deriva (una versión es vigente cuando nada la enmienda), así que los expedientes firmados nunca se actualizan. `GET /records/{id}/versions` lista la cadena (requiere `records.read_clinical`, auditado como `record.versions_viewed`). `RecordResponse` añade `amendment_reason`, `is_current` y `superseded_by_id`, y `GET /records/{id}` de una versión antigua sigue permitido. Los listados (`GET /records`, `GET /patients/{id}/records`, vitales, y `recent_records` / `records_count` de `GET /patients/{id}`) muestran solo versiones vigentes. `GET /print/records/{id}` resuelve a la versión vigente y añade `version` y `original_signed_at`. Una constancia emitida sobre un expediente reemplazado usa la versión vigente, listar constancias por expediente recorre toda la cadena, y una constancia impresa termina la consulta en la hora de la firma original.
- **Recetas** (`application/use_cases/prescriptions.py`, router `prescriptions`): solo el médico que emitió una receta la completa o la cancela (403 `prescription.not_own`; las sesiones de soporte reciben 403, y los administradores, que no tienen `prescriptions.manage`, reciben `permission.missing`). `prescriptions.manage` es `DOCTOR_ONLY`. Completar es el fin natural del tratamiento; cancelar lo detiene antes y exige un motivo de 10 a 500 caracteres, tras recortarlo (422 `prescription.cancel_reason_invalid`, `params.min`, `params.max`). El motivo se guarda en la receta (`cancel_reason`) y la auditoría solo registra su longitud (`reason_chars`). `closed_at` y `closed_by_id` registran cuándo y quién la cerró. `GET /prescriptions?patient_id=` devuelve `cancel_reason` solo a quien tiene `records.read_clinical`; los demás ven el estado y la fecha. Ambas transiciones bloquean la fila, así que si se completa y se cancela a la vez, la segunda responde 422 `invalid_transition`. No se notifica a nadie: solo el médico que la emitió puede actuar. Imprimir la receta de un expediente (`GET /print/records/{id}?document=prescription`) omite las canceladas; si todas lo están responde 400 `print.nothing_to_print`, y el expediente firmado no cambia. `POST /prescriptions/{id}/cancel` recibe `{"reason": str}` y rechaza los campos desconocidos (422), así que backend y frontend se despliegan juntos.
- **Documentos médicos** (`application/use_cases/records.py`, router `records`; `MedicalDocument.register` y `link_to` en `domain/entities/medical_document.py`): `POST /documents` recibe `patient_id`, `file_name`, `kind`, `mime_type`, `size_bytes` y un `record_id` opcional, con topes de longitud, y rechaza los campos desconocidos (422 `request_invalid`, así que un cliente que aún envíe `storage_key` falla). El servidor genera la clave como `{tenant_id}/{patient_id}/{document_id}`; es única en la base (`uq_medical_documents_storage_key`) y nunca se devuelve: `DocumentResponse` y `GET /patients/{id}/documents` la omiten. Solo se guardan metadatos; todavía no hay subida de archivos. Las sesiones de soporte no pueden registrar documentos (`support.clinical_forbidden`). El `record_id` debe ser del mismo paciente; si el expediente tiene enmiendas, el documento queda ligado a su versión vigente. `AttachDocument`, el caso de uso sin endpoint, se retiró.
- **Notificaciones in-app** (`application/common/notifications.py`): los casos de uso las
  emiten dentro de su propia transacción —se guardan junto con la acción o no se guardan—,
  nunca al propio autor. Eventos: cita creada/reprogramada/cancelada/no-show (al médico de la
  cita), documento subido (al médico asignado del
  paciente o, si no tiene, al de su última cita completada) y usuario creado/cambio de rol (a los admins activos), y acciones de soporte sobre usuarios de la clínica (a los admins activos y al usuario afectado; la entrada de impersonación, solo a los admins). Se guarda `type` + `data` (ids y etiquetas, nunca contenido clínico ni
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
  `subject` legible en su metadata para una columna de detalle útil. Eventos de consulta: `consultation.viewed` (alcance `full` o `vitals`), `consultation.note_updated`, `consultation.vitals_updated` (metadata `keys`), `consultation.template_changed` (`from`/`to`) y `consultation.draft_changed` (`section`/`op`), solo con nombres, nunca texto clínico. Las lecturas y las ediciones de nota y vitales de un mismo actor se agregan en ventanas de 10 minutos por clave (`append_coalesced`), para que el autoguardado y el sondeo no llenen la bitácora.
- **Consola de plataforma** (superadmin): alta/gestión de clínicas, estadísticas globales,
  auditoría consolidada y **sesiones de soporte** (impersonación con TTL corto, motivo obligatorio de 5–500 caracteres y traza en la auditoría de la clínica). Las acciones de soporte sobre usuarios de una clínica (restablecer contraseña con motivo, editar, cambiar rol, suspender, reactivar) quedan en la auditoría de esa clínica como «Soporte de la plataforma», con IP y navegador pero sin la identidad del superadmin, y no se duplican en la auditoría global.

## Configuración

Copia `.env.example` a `.env` y ajusta los valores:

| Variable | Descripción | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | `development` o `production`. En producción se activan validaciones estrictas. | `development` |
| `DATABASE_URL` | Cadena de conexión PostgreSQL (psycopg3) | `postgresql+psycopg://localhost/medicore` |
| `JWT_SECRET` | Secreto para firmar tokens. **Obligatorio en producción, de al menos 32 bytes** (`openssl rand -hex 32`). | `change-me` (solo dev) |
| `JWT_ALGORITHM` | Algoritmo JWT: solo `HS256`, `HS384` o `HS512` | `HS256` |
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
> siendo el default inseguro o tiene menos de 32 bytes, o si `CORS_ORIGINS` es `*`, `COOKIE_SECURE` es `false` o `MFA_ENCRYPTION_KEY` está vacía. Además los docs
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

# 4) Datos de demo: 3 clínicas con ~8 semanas de historia y 4 de agenda, generadas ejecutando
#    los casos de uso reales con un reloj simulado (incluye auditoría y notificaciones)
.venv/bin/python scripts/seed_demo.py            # idempotente
.venv/bin/python scripts/seed_demo.py --reset    # borra los tenants demo y los recrea

# 5) (opcional) Alta de un superadmin de plataforma
.venv/bin/python scripts/create_platform_admin.py

# Superadmin que perdió la app autenticadora y los códigos de recuperación: desactiva su MFA y revoca sus sesiones
.venv/bin/python scripts/reset_platform_mfa.py <correo>

# Tarea programada diaria en todos los entornos: borra sesiones caducadas o revocadas (queda registrada como el job session_purge)
.venv/bin/python scripts/purge_expired_sessions.py

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
- Los errores de validación (422) ya no incluyen el valor enviado (`input`) en su detalle.
- Firmar una consulta dos veces, o editar una ya firmada (autoguardado, diagnósticos, borradores),
  responde 409 `consultation.already_signed`. `consultation.incomplete` sigue siendo un 422.
- Leer contenido clínico sin `records.read_clinical` responde 403 `permission.missing`; un listado de expedientes con `date_from` posterior a `date_to` responde 400 `records.invalid_range`.
- El acceso a la consulta responde 403 `consultation.not_own` (consulta de otro médico), `permission.missing` (otros roles) o `support.clinical_forbidden` (suplantación de soporte); los vitales de una cita sin consulta responden 404 `consultation.not_started`.
- Las enmiendas de expedientes responden 403 `record.not_own` (no es el autor) o `support.clinical_forbidden`, 409 `record.superseded` (`params.current_id`), 422 `record.amend_reason_invalid` (`params.min`, `params.max`) y 422 `record.amend_empty`.
- Cerrar una receta responde 403 `prescription.not_own` (no es quien la emitió), 422 `prescription.cancel_reason_invalid` (`params.min`, `params.max`) si el motivo está fuera de rango, y 422 `invalid_transition` si ya estaba cerrada.
- Subir un documento responde 403 `support.clinical_forbidden` (sesiones de soporte) o `permission.missing` (roles sin `records.upload`), 422 `document.record_mismatch` (el expediente es de otro paciente), 404 `not_found` (paciente inexistente, o expediente inexistente o de otra clínica), 400 `document.unsupported_type`, `document.too_large` o `document.invalid_name`, y 422 `request_invalid` para campos desconocidos como `storage_key`.

## Pruebas y linting

Suite de **1657 tests** (331 dominio · 742 aplicación · 390 presentación · 190 infraestructura · 4 scripts), casi
toda independiente de la base de datos gracias a adaptadores en memoria que ejercen el mismo
contrato multi-tenant que los repos SQLAlchemy.

Los tests de integración contra PostgreSQL real (`tests/infrastructure/test_audit_repository_sql.py`,
`test_diagnosis_catalog_sql.py` — ranking y búsqueda por trigram del autocomplete de diagnósticos —
`test_login_throttle_sql.py` — UPSERT atómico del lockout de login —
`test_consultation_sign_sql.py` — firmas y ediciones concurrentes de una consulta — y
`test_notification_repository_sql.py` — JSONB y UPDATE/DELETE masivos de la bandeja —
`test_record_summaries_sql.py` — listado de expedientes (resúmenes, filtros y paginación) — `test_record_amend_sql.py` — la cadena de enmiendas (lock de fila, índice único, CHECK del motivo) — `test_patient_search_sql.py` — búsqueda sin acentos, dígitos del teléfono, últimas visitas — `test_prescription_sql.py` — los campos de cierre, el CHECK del motivo de cancelación y el lock de fila, y `test_document_repository_sql.py` — el recorrido de ida y vuelta de los documentos y la clave única de almacenamiento) usan `TEST_DATABASE_URL`
(o `DATABASE_URL` de la configuración),
corren dentro de una transacción que siempre se revierte —no dejan rastro en la BD de desarrollo—
y se **saltan automáticamente** si no hay PostgreSQL accesible.

```bash
.venv/bin/pytest
.venv/bin/ruff check src tests
```

El test de integración del seed hace commits y prueba el reset nocturno. Se omite salvo que
`DEMO_TEST_DATABASE_URL` apunte expresamente a una **BD desechable vacía, con migraciones**;
nunca usa la BD de trabajo por defecto. Tras crear esa BD desechable, ejecuta:

```bash
DATABASE_URL="$DEMO_TEST_DATABASE_URL" .venv/bin/alembic upgrade head
.venv/bin/pytest tests/scripts -q
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
- `JWT_SECRET` fuerte de al menos 32 bytes (`openssl rand -hex 32`) — la app no arranca si es inseguro o más corto.
- `MFA_ENCRYPTION_KEY` definida (32 bytes en base64url) — la app no arranca sin ella.
- `DATABASE_URL` apuntando a la base de datos real.
- `CORS_ORIGINS` con los orígenes del frontend (no `*`).
- `TRUSTED_PROXIES` con la IP del reverse-proxy (p. ej. `127.0.0.1` si nginx corre en el
  mismo host) para que la auditoría registre la IP real del cliente.
- Opcional: `ENABLE_DOCS=false` para ocultar Swagger/OpenAPI.
- Una tarea programada diaria que ejecute `python scripts/purge_expired_sessions.py` (ver **Puesta en marcha**).

> **Nota de actualización:** tras aplicar la migración `d0e1f2a3b4c6` (límites de la sesión de consola), los usuarios de clínica y los superadmins deben volver a iniciar sesión una vez.

> **Antes de desplegar esta versión:** define `MFA_ENCRYPTION_KEY` (32 bytes en base64url). La migración `e1f2a3b4c5d7` añade las columnas de MFA a `platform_admins` y la tabla `platform_admin_recovery_codes`.

> **Antes de desplegar esta versión:** todos los usuarios, incluidos los superadmins, vuelven a iniciar sesión una vez (los tokens anteriores no tienen audiencia).
>
> **Migración `f2a3b4c5d6e8`:** añade `last_success_at` a `login_attempts` (lockout de login). No requiere variables de entorno nuevas.
>
> **Migración `a3b4c5d6e7f9`:** añade un índice único parcial para que una consulta tenga como máximo un expediente original. **Antes de desplegar, ejecuta la consulta de detección de [Expedientes duplicados por doble firma](#expedientes-duplicados-por-doble-firma)**: la migración se niega a correr mientras existan duplicados (lista solo sus ids) y nunca los resuelve por sí misma. Crear el índice bloquea escrituras en `medical_records` un instante. El entrypoint de Docker ejecuta `alembic upgrade head`, así que la migración se aplica al desplegar.
>
> **Migración `c4d5e6f7a8b0`:** añade el índice `ix_records_tenant_encounter` sobre `medical_records(tenant_id, encounter_at)` para el listado de expedientes, y otorga `records.read_clinical` al rol médico de las clínicas que lo habían personalizado. Crear el índice bloquea escrituras en `medical_records` un instante. Su downgrade quita el permiso de las personalizaciones del médico y elimina el índice.

> **Migración `e6f7a8b9c0d2`** (enmiendas de expedientes): añade `amendment_reason` (obligatorio en toda enmienda, por un CHECK), rellena las enmiendas existentes con el motivo provisional "Enmienda previa a la exigencia de motivo", reasigna el `author_id` de las enmiendas hechas por otro médico al autor original de la cadena (quien firmó cada versión queda en `signed_by_id` y en la auditoría), y crea el índice único `uq_medical_records_amends`. **Antes de desplegar, ejecuta las consultas de [Cadenas de enmiendas ramificadas](#cadenas-de-enmiendas-ramificadas)**: la migración se niega a correr mientras algún expediente tenga más de una enmienda, y lista solo sus ids. Su downgrade quita la columna, el CHECK y el índice, pero no restaura los autores reasignados. **Despliega backend y frontend juntos**: el frontend anterior no envía el motivo.
>
> **Migración `d5e6f7a8b9c1`** (autoría de la consulta): devuelve `consultations.edit` a los roles médicos personalizados y elimina las revocaciones de `edit` a médicos; en roles y usuarios de enfermería y recepción, `consultations.edit` pasa a `consultations.vitals` (si quedan a la vez concedido y revocado, gana la revocación; admin no se toca). **Antes de desplegar, respalda `role_permission_overrides` y la tabla `users` (columna `permission_adjustments`).** Su downgrade convierte `vitals` de nuevo en `edit`, pero no restaura las revocaciones de los médicos.
>
> **Migración `f7a8b9c0d1e3`** (cierre de recetas): añade `closed_at`, `closed_by_id` y `cancel_reason`, con un CHECK según el cual toda receta cancelada tiene motivo; las canceladas anteriores a él reciben el motivo de relleno "Cancelación previa a la exigencia de motivo". `prescriptions.manage` pasa a ser solo de médicos: las personalizaciones y los ajustes por usuario de enfermería y recepción lo pierden, y los médicos lo recuperan. **Antes de desplegar, ejecuta las consultas de [Recetas cerradas por otra persona](#recetas-cerradas-por-otra-persona)**, y despliega backend y frontend juntos: el endpoint de cancelar exige ahora un cuerpo con `reason`. Su downgrade elimina las columnas y el CHECK, pero no restaura los permisos.

> **Migración `f8a9b0c1d2e4`** (claves de almacenamiento de documentos): desliga (`record_id = NULL`) los documentos cuyo expediente es de otro paciente o no existe (el archivo sigue en la ficha de su paciente), reescribe cada `storage_key` a `{tenant_id}/{patient_id}/{id}` (todavía no se almacena ningún archivo, así que no se mueve nada) y crea el índice único `uq_medical_documents_storage_key`. **Antes de desplegar, ejecuta las consultas de [Claves de almacenamiento de documentos](#claves-de-almacenamiento-de-documentos)**, y despliega backend y frontend juntos: `POST /documents` ya no acepta `storage_key`. Su downgrade solo quita el índice; los expedientes desligados y las claves anteriores no se recuperan.

> Para varios workers basta con `WEB_CONCURRENCY=N` (uvicorn la lee; el `docker-compose.yml` usa 2). Cada
> worker tiene su propio pool de hasta 15 conexiones: mantén `N × 15` por debajo de `max_connections` de Postgres.
> La app se sirve detrás de un reverse-proxy que termina TLS y reenvía `X-Forwarded-For`.
> La cabecera **solo se honra** si la conexión viene de un proxy listado en
> `TRUSTED_PROXIES` (recorriendo la cadena de derecha a izquierda y descartando los hops
> confiables); en cualquier otro caso se registra la IP del socket. La imagen arranca
> uvicorn con `--no-proxy-headers` para que la app sea la única que interprete la
> cabecera — mantenlo así si sobreescribes el `CMD`.

## Expedientes duplicados por doble firma

Antes de la migración `a3b4c5d6e7f9`, una consulta firmada dos veces a la vez (doble clic, reintento, dos pestañas) podía acabar con dos expedientes originales. Ahora la firma bloquea la consulta, y la migración añade un índice único parcial sobre `medical_records(consultation_id)` para los expedientes originales (las enmiendas repiten `consultation_id` y quedan fuera), así que la base de datos rechaza un segundo original. La migración nunca deduplica: cada duplicado es un documento clínico, y decidir cuál queda es una decisión clínica. Por eso se niega a correr mientras existan duplicados y solo lista sus ids.

Ejecuta esta consulta sobre la base de datos de producción antes de desplegar:

```sql
SELECT r.tenant_id, r.consultation_id, r.id AS record_id, r.code, r.signed_at,
       (SELECT count(*) FROM prescriptions p WHERE p.record_id = r.id) AS prescriptions,
       (SELECT count(*) FROM application_orders a WHERE a.consultation_id = r.consultation_id) AS application_orders,
       (SELECT count(*) FROM procedures pr WHERE pr.consultation_id = r.consultation_id) AS procedures
FROM medical_records r
WHERE r.amends_record_id IS NULL AND r.consultation_id IN (
  SELECT consultation_id FROM medical_records
  WHERE consultation_id IS NOT NULL AND amends_record_id IS NULL
  GROUP BY consultation_id HAVING count(*) > 1)
ORDER BY r.consultation_id, r.signed_at;
```

- **Sin filas**: no hay duplicados, y la migración se aplica al desplegar.
- **Con filas**: resuelve a mano cada consulta antes de desplegar. Anula las recetas, órdenes de aplicación y procedimientos duplicados, y el expediente sobrante, conservando el que queda. Cada fila indica cuántas recetas tiene el expediente y cuántas órdenes de aplicación y procedimientos tiene la consulta. La migración no corre hasta que no queden duplicados.

## Cadenas de enmiendas ramificadas

Un expediente se enmienda como máximo una vez, así que sus versiones forman una línea. Antes de esta versión un expediente podía enmendarse más de una vez, y una enmienda podía estar firmada por un médico distinto al autor original. La migración `e6f7a8b9c0d2` hace cumplir la línea con un índice único sobre `amends_record_id`. Nunca vuelve a enlazar nada por sí misma: cuando un expediente tiene más de una enmienda, decidir a qué versión sigue la siguiente es una decisión clínica. Por eso la migración se niega a correr mientras existan esas ramas y solo lista sus ids.

Ejecuta estas consultas sobre la base de datos de producción antes de desplegar:

```sql
-- 1. Ramas (si hay filas, la migración falla)
SELECT tenant_id, amends_record_id, array_agg(id ORDER BY signed_at) ids, array_agg(signed_by_id ORDER BY signed_at) signers
FROM medical_records WHERE amends_record_id IS NOT NULL GROUP BY 1,2 HAVING count(*) > 1;
-- 2. Enmiendas hechas por otro médico (la migración las reasigna al autor original)
WITH RECURSIVE chain AS (SELECT id, id root_id, author_id root_author FROM medical_records WHERE amends_record_id IS NULL
  UNION ALL SELECT m.id, c.root_id, c.root_author FROM medical_records m JOIN chain c ON m.amends_record_id = c.id)
SELECT r.tenant_id, r.id, chain.root_id, chain.root_author, r.author_id, r.signed_by_id, r.signed_at
FROM medical_records r JOIN chain USING (id) WHERE r.amends_record_id IS NOT NULL AND r.author_id <> chain.root_author;
-- 3. Constancias emitidas por quien no es el autor original (siguen válidas; decidir si se anulan)
WITH RECURSIVE chain AS (SELECT id, author_id root_author FROM medical_records WHERE amends_record_id IS NULL
  UNION ALL SELECT m.id, c.root_author FROM medical_records m JOIN chain c ON m.amends_record_id = c.id)
SELECT c.tenant_id, c.id, c.code, c.doctor_id, chain.root_author, c.voided_at
FROM medical_certificates c JOIN chain ON chain.id = c.record_id WHERE c.doctor_id <> chain.root_author;
```

- **Filas de la consulta 1**: la migración se niega a correr. Resuelve cada rama a mano, con revisión clínica: vuelve a apuntar cada enmienda posterior a la punta de la anterior, ordenadas por `signed_at`, con un `UPDATE` de `amends_record_id`. Hazlo en una transacción y revisa el resultado; luego vuelve a ejecutar la consulta hasta que no devuelva filas.
- **Filas de la consulta 2**: no hay nada que hacer antes de desplegar. La migración reasigna su `author_id`, y quien firmó cada versión queda en `signed_by_id` y en la auditoría.
- **Filas de la consulta 3**: esas constancias siguen válidas y la migración no las toca. Decide con la clínica si las anulas.

## Recetas cerradas por otra persona

Hasta esta versión cualquier médico de la clínica podía completar o cancelar cualquier receta, y cancelar no pedía motivo. La migración `f7a8b9c0d1e3` hace que solo quien la emitió pueda cerrarla, y pasa `prescriptions.manage` a ser de médicos. Nunca reasigna ni reabre nada: los cierres que hizo otra persona se quedan como están. Ejecuta estas consultas sobre la base de datos de producción antes de desplegar:

```sql
-- 1. Recetas canceladas que recibirán el motivo de relleno
SELECT tenant_id, count(*) FROM prescriptions WHERE status='cancelled' GROUP BY 1;
-- 2. Personalizaciones de rol afectadas
SELECT tenant_id, role FROM role_permission_overrides WHERE role IN ('nurse','receptionist') AND permissions ? 'prescriptions.manage';
SELECT tenant_id, role FROM role_permission_overrides WHERE role='doctor' AND NOT permissions ? 'prescriptions.manage';
-- 3. Ajustes por usuario afectados
SELECT tenant_id, id, role FROM users WHERE (role IN ('nurse','receptionist') AND (permission_adjustments->'granted' ? 'prescriptions.manage' OR permission_adjustments->'revoked' ? 'prescriptions.manage')) OR (role='doctor' AND permission_adjustments->'revoked' ? 'prescriptions.manage');
-- 4. Recetas cerradas por alguien que no las emitió (revisión clínica)
SELECT p.tenant_id, p.id, a.action, a.actor_id, a."timestamp" FROM prescriptions p JOIN audit_logs a ON a.tenant_id=p.tenant_id AND a.entity_type='Prescription' AND a.entity_id=p.id::text AND a.action IN ('prescription.completed','prescription.cancelled') WHERE a.actor_id <> p.prescriber_id;
-- 5. Recetas activas que nadie podrá cerrar (médico inactivo o borrado)
SELECT p.tenant_id, count(*) FROM prescriptions p LEFT JOIN users u ON u.id=p.prescriber_id WHERE p.status='active' AND (u.id IS NULL OR u.status <> 'active') GROUP BY 1;
```

- **Consulta 1**: esas cancelaciones conservan el motivo de relleno "Cancelación previa a la exigencia de motivo" hasta que alguien escriba uno real; no hay nada más que hacer antes de desplegar.
- **Consultas 2 y 3**: la migración cambia estas filas. Las personalizaciones de enfermería y recepción pierden `prescriptions.manage`, sin sustituto, y los médicos lo recuperan (o pierden su revocación). Las filas de admin no se tocan.
- **Consulta 4**: la migración rellena `closed_by_id` con el primer cierre del registro de auditoría. Revisa estos casos con la clínica; la migración no los reabre.
- **Consulta 5**: tras desplegar, nadie puede completar ni cancelar estas recetas, y tampoco un administrador. Siguen activas hasta que la clínica decida cómo cerrarlas (ver el backlog).

## Claves de almacenamiento de documentos

Hasta esta versión el cliente elegía la `storage_key` de cada documento, y nada impedía que dos documentos compartieran una. La migración `f8a9b0c1d2e4` hace que la elija el servidor, añade el índice único y desliga los documentos que apuntan a un expediente de otro paciente. Todavía no se almacena ningún archivo, así que reescribir las claves no mueve nada. Ejecuta estas consultas contra la base de producción antes de desplegar:

```sql
-- Documentos ligados a un expediente ajeno o inexistente (la migración los desliga)
SELECT d.tenant_id, d.id, d.patient_id, d.record_id, r.patient_id AS record_patient_id
FROM medical_documents d LEFT JOIN medical_records r ON r.id = d.record_id AND r.tenant_id = d.tenant_id
WHERE d.record_id IS NOT NULL AND (r.id IS NULL OR r.patient_id <> d.patient_id);
-- Claves que se reescribirán
SELECT count(*) FROM medical_documents WHERE storage_key <> tenant_id::text||'/'||patient_id::text||'/'||id::text;
```

- **Filas de la consulta 1**: nada que hacer antes de desplegar. La migración los desliga, cada documento sigue en la ficha de su paciente, y el expediente al que apuntaban no se toca.
- **Consulta 2**: solo un conteo. La migración reescribe esas claves y nada más.
