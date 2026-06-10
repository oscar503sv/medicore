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

### Ciclo de vida de recetas
`Prescription.complete()` y `Prescription.cancel()` existen en el dominio
(`domain/entities/prescription.py`) pero no hay caso de uso ni endpoint que los invoque:
las recetas nacen `active` y nunca cambian de estado. La UI muestra "recetas activas"
calculadas, pero nadie puede completar/cancelar una.

### Reactivaciones
- `Patient.reactivate()` (`domain/entities/patient.py`) — se puede archivar desde la UI,
  pero no reactivar; un paciente archivado es hoy un estado terminal en la práctica.
- `Insurer.reactivate()` (`domain/entities/insurer.py`) — mismo caso para aseguradoras.

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
expediente (`patient.chart_viewed`) y `startswith` en el filtro de auditoría.

Pendiente, en orden de valor aproximado:

1. **Lockout / rate limiting en login** — no hay límite de intentos fallidos ni rate
   limiting por IP en `/auth/login` y `/platform/login`. Mitigación parcial: bcrypt
   encarece cada intento. Opciones: contador de fallos en BD (lockout temporal) o
   middleware tipo `slowapi` con Redis.
2. **Revocación de sesiones / refresh tokens** — el access token dura 24 h
   (`JWT_EXPIRE_MINUTES=1440`) y el logout es solo client-side; un token robado vale hasta
   expirar. Opciones: TTL corto + refresh token rotatorio, o blacklist server-side
   (invalidación al cambiar contraseña / logout forzado).
3. **`X-Forwarded-For` confiable** — `_client_ip()` en `presentation/dependencies.py` toma
   la cabecera sin validar que venga de un proxy de confianza; la IP registrada en
   auditoría es spoofeable si la app se expone sin reverse-proxy. Solución: lista de
   proxies de confianza configurable.
4. **Token en localStorage** — el frontend persiste la sesión en localStorage (riesgo si
   hubiera XSS). Alternativa: cookies httpOnly (requiere CSRF protection) o aceptar el
   trade-off con CSP estricta.
5. **Política de contraseñas** — mínimo actual de 8 caracteres sin más requisitos
   (`use_cases/auth.py`). NIST sugiere ≥12 o chequeo de entropía (zxcvbn).
6. **Enumeración de organizaciones en login** — el formulario de login revela si un slug
   de organización existe (mensaje distinto). Riesgo bajo: los slugs son semi-públicos.
7. **Cobertura de tests de infraestructura** — los filtros SQL del repositorio de
   auditoría (categoría, actor, fechas) solo están cubiertos por los repos en memoria;
   añadir tests contra el repositorio SQLAlchemy real.
8. **Contraseña demo del seed** — `scripts/seed_demo.py` usa `demo1234` fija. Es un script
   explícitamente de desarrollo, pero podría generar una contraseña aleatoria e imprimirla.
