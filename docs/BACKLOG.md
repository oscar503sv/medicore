# Backlog — trabajo diferido y hallazgos pendientes

Inventario de funcionalidad a medio implementar y de hallazgos de seguridad que se decidió
**documentar pero no abordar todavía** (auditoría de junio 2026). Cuando se retome alguno,
conviene revisar que las referencias sigan vigentes.

## Funcionalidad incompleta (backend tiene más de lo que se usa)

### Sistema de notificaciones
La pieza más grande. Existe la base pero nada la usa:
- Entidad `Notification` con `mark_read()` — `backend/src/medicore/domain/entities/notification.py`
- Repositorio (puerto + implementación) y tabla `notifications` en la BD.
- **Falta**: casos de uso, router/endpoints, emisión de notificaciones desde los flujos
  (cita creada/cancelada, resultado subido…) y UI (campana en el Topbar).

### Otros cabos sueltos
- Caso de uso `AttachDocument` (`application/use_cases/consultations.py`) sin endpoint:
  adjuntar documentos a una consulta en curso no es alcanzable vía API.
- Value object `Money` (`domain/value_objects/money.py`) sin uso — presumiblemente
  reservado para facturación.
- Rutas del frontend `/applications`, `/procedures`, `/vaccination` apuntan a
  `ComingSoonPage` de forma intencional (badge "Próximamente" en el sidebar).
- El almacenamiento de documentos médicos guarda **solo metadata** (nombre, mime, tamaño,
  `storage_key`); no hay backend de archivos (S3/disco). La UI lo comunica explícitamente.

## Seguridad — diferido conscientemente

Quick wins ya aplicados (jun 2026): login en tiempo constante, validación de CORS/docs en
producción, security headers, validación de metadata de uploads, auditoría de lectura de
expediente (`patient.chart_viewed`) y `startswith` en el filtro de auditoría. Además, el
token de sesión ya no se guarda en localStorage: vive en una cookie httpOnly
(SameSite=Lax, Secure en producción) con CSRF double-submit (`mc_csrf` +
`X-CSRF-Token`); el header `Authorization: Bearer` sigue aceptándose para clientes API.

Pendiente, en orden de valor aproximado:

1. **Lockout / rate limiting en login** — no hay límite de intentos fallidos ni rate
   limiting por IP en `/auth/login` y `/platform/login`. Mitigación parcial: bcrypt
   encarece cada intento. Opciones: contador de fallos en BD (lockout temporal) o
   middleware tipo `slowapi` con Redis.
2. **Revocación de sesiones / refresh tokens** — el access token dura 24 h
   (`JWT_EXPIRE_MINUTES=1440`); aunque el logout ya borra la cookie de sesión, un token
   robado vale hasta expirar. Opciones: TTL corto + refresh token rotatorio, o blacklist
   server-side (invalidación al cambiar contraseña / logout forzado).
3. **`X-Forwarded-For` confiable** — `_client_ip()` en `presentation/dependencies.py` toma
   la cabecera sin validar que venga de un proxy de confianza; la IP registrada en
   auditoría es spoofeable si la app se expone sin reverse-proxy. Solución: lista de
   proxies de confianza configurable.
4. **Política de contraseñas** — mínimo actual de 8 caracteres sin más requisitos
   (`use_cases/auth.py`). NIST sugiere ≥12 o chequeo de entropía (zxcvbn).
5. **Enumeración de organizaciones en login** — el formulario de login revela si un slug
   de organización existe (mensaje distinto). Riesgo bajo: los slugs son semi-públicos.
6. **Cobertura de tests de infraestructura** — los filtros SQL del repositorio de
   auditoría (categoría, actor, fechas) solo están cubiertos por los repos en memoria;
   añadir tests contra el repositorio SQLAlchemy real.
7. **Contraseña demo del seed** — `scripts/seed_demo.py` usa `demo1234` fija. Es un script
   explícitamente de desarrollo, pero podría generar una contraseña aleatoria e imprimirla.
8. **CSP estricta en el host del frontend** — con el token fuera de localStorage el impacto
   de un XSS baja, pero una Content-Security-Policy en el servidor que sirve la SPA sigue
   siendo la defensa principal contra inyección de scripts.
