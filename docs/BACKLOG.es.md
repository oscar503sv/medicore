# Backlog — trabajo diferido y hallazgos pendientes

[English](BACKLOG.md) · **Español**

Inventario de funcionalidad a medio implementar y de hallazgos de seguridad que se decidió
**documentar pero no abordar todavía** (auditoría de junio 2026). Cuando se retome alguno,
conviene revisar que las referencias sigan vigentes.

## Funcionalidad incompleta (backend tiene más de lo que se usa)

### Sistema de notificaciones
Notificaciones in-app completas: emisión desde citas, enmiendas, documentos y gestión de
usuarios; router `/notifications`; campana del Topbar con contador (sondeo cada 60 s) y
desplegable con enlaces directos (`/appointments?date=`, `/patients/:id?tab=…&record=…`);
buzón completo en `/notifications` (filtros por estado y categoría, agrupado por día).
Canales externos y recordatorios quedan planificados como evolución futura (ver
[A futuro](#a-futuro)).

### Otros cabos sueltos
- Caso de uso `AttachDocument` (`application/use_cases/consultations.py`) sin endpoint:
  adjuntar documentos a una consulta en curso no es alcanzable vía API.
- Value object `Money` (`domain/value_objects/money.py`) sin uso — presumiblemente
  reservado para facturación.
- Rutas del frontend `/applications`, `/procedures`, `/vaccination` apuntan a
  `ComingSoonPage` de forma intencional (badge "Próximamente" en el sidebar).
- El almacenamiento de documentos médicos guarda **solo metadata** (nombre, mime, tamaño,
  `storage_key`); no hay backend de archivos (S3/disco). La UI lo comunica explícitamente.

## A futuro

Funcionalidad planificada para una siguiente etapa del producto, sin fecha.

### Notificaciones por canales externos
Avisar también fuera de la app (hoy solo existen la campana y el buzón in-app). Base ya presente: las
preferencias por usuario y tema (`appointments`, `reminders`, `lab_results`,
`internal_messages`, `weekly_reports`) con canal `email | push | sms | none` se guardan
(`domain/value_objects/user_preferences.py`), pero nada las lee: no hay endpoint, ni
pantalla de preferencias, ni proveedor de envío.

Requiere: puerto + adaptador de envío (SMTP o un servicio tipo SendGrid/Twilio), respetar
las preferencias al emitir cada notificación, pantalla de preferencias en el perfil y
envío en segundo plano para no bloquear la petición.

### Recordatorios de citas
Avisos disparados por tiempo: recordatorio al paciente (p. ej. 24 h antes) para reducir
inasistencias y, opcionalmente, resumen diario de agenda para el médico. Requiere un
proceso programado (cron/worker) idempotente que busque citas próximas y no repita
envíos; usa los datos de contacto de la ficha del paciente. Depende de los canales
externos: el paciente no usa la app.

Orden sugerido: (1) email, el canal más simple y barato; (2) recordatorios de cita a
pacientes por email; (3) SMS/WhatsApp, con coste por mensaje y proveedor externo.

## Seguridad — diferido conscientemente

Quick wins ya aplicados (jun 2026): login en tiempo constante, validación de CORS/docs en
producción, security headers, validación de metadata de uploads, auditoría de lectura de
expediente (`patient.chart_viewed`) y `startswith` en el filtro de auditoría. Además, el
token de sesión ya no se guarda en localStorage: vive en una cookie httpOnly
(SameSite=Lax, Secure en producción) con CSRF double-submit (`mc_csrf` +
`X-CSRF-Token`); el header `Authorization: Bearer` sigue aceptándose para clientes API.
También: tests de integración del repo SQL de auditoría contra PostgreSQL real
(`tests/infrastructure/test_audit_repository_sql.py` — destaparon y corrigieron un escape
de comodines LIKE faltante en los filtros de categoría) y CSP estricta inyectada en el
build de la SPA (meta en `dist/index.html` vía plugin de Vite; el header completo con
`frame-ancestors` queda documentado para el reverse-proxy en el README del frontend).

Resueltos en jun 2026 (sin Redis — el contador y las sesiones viven en PostgreSQL, que
ya se consulta en cada request autenticado):

- **Lockout en login**: contador de fallos en BD por `(slug, email)` con lockout temporal
  y backoff exponencial (5 fallos → 1 min, duplicando hasta 15); responde 429 con
  `Retry-After`, cuenta también cuentas inexistentes (anti-enumeración) y audita
  `auth.login_locked`.
- **Revocación de sesiones**: tabla `sessions` + claim `sid` en el JWT validada en cada
  request; logout real, cambio de contraseña revoca las demás sesiones, suspensión/reset
  revoca todas, y las sesiones de soporte (impersonación) también son revocables.
- **`X-Forwarded-For` confiable**: la cabecera solo se honra desde proxies listados en
  `TRUSTED_PROXIES` (IPs/CIDRs; cadena recorrida de derecha a izquierda descartando hops
  confiables); vacío → se registra la IP del socket. La imagen Docker arranca uvicorn con
  `--no-proxy-headers` para que la app sea la única que interprete la cabecera.
- **Enumeración de organizaciones en login**: un slug inexistente o inválido responde
  igual que una contraseña incorrecta (`invalid credentials`) y ejecuta el verify contra
  el hash dummy, así que ni el mensaje ni el tiempo revelan qué slugs existen. El estado
  de la clínica (`this organization is not active`) solo se informa tras credenciales
  válidas, igual que el de la cuenta.

Pendiente, en orden de valor aproximado:

1. **Política de contraseñas** — mínimo actual de 8 caracteres sin más requisitos
   (`use_cases/auth.py`). NIST sugiere ≥12 o chequeo de entropía (zxcvbn).
2. **Contraseña demo del seed** — `scripts/seed_demo.py` usa `demo1234` fija. Es un script
   explícitamente de desarrollo, pero podría generar una contraseña aleatoria e imprimirla.
