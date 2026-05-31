# Medicore

Sistema de gestión clínica **multi-tenant** construido con **Clean Architecture**.

Cubre el ciclo completo de atención: autenticación, dashboard, pacientes e historial
médico, agenda y citas, consulta en curso (bitácora SOAP), historiales clínicos firmados
(inmutables), archivos médicos, disponibilidad por doctor, gestión de usuarios y ajustes
de organización.

## Estructura del monorepo

```
medicore_v1/
├── backend/                  # API + lógica de negocio (Python · Clean Architecture)
│   └── src/medicore/
│       ├── domain/           # Entities, Value Objects, Enums, Services, Repos (puertos)
│       ├── application/       # Casos de uso (interactors), DTOs           [fase 2]
│       ├── infrastructure/    # ORM, auth, multi-tenant, storage           [fase 3]
│       └── presentation/      # API FastAPI / controllers                  [fase 4]
├── frontend/                 # SPA React + TS + Vite                       [fase 4]
└── design_handoff_medicore/  # Handoff de diseño + modelo de dominio + prototipo
```

## Fases de implementación

| Fase | Contenido | Estado |
|---|---|---|
| 1 | Dominio completo + tests | **en curso** |
| 2 | Casos de uso + tests con repos en memoria | pendiente |
| 3 | Infraestructura (DB, migraciones, auth, multi-tenant) | pendiente |
| 4 | UI pantalla por pantalla | pendiente |

## Backend — desarrollo

```bash
cd backend
.venv/bin/pip install -e ".[dev]"   # instalar en modo editable + dev deps
.venv/bin/pytest                    # ejecutar tests
.venv/bin/ruff check src            # lint
```

Ver `design_handoff_medicore/DOMAIN_MODEL.md` para la especificación del dominio y
`design_handoff_medicore/README.md` para el handoff de las pantallas.
