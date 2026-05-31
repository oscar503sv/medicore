# Medicore — Backend

API y lógica de negocio de Medicore, organizada en **Clean Architecture**.

## Capas

```
src/medicore/
├── domain/          # Núcleo del negocio. Sin dependencias de framework.
│   ├── enums.py
│   ├── shared/      # errores de dominio + identificadores (UUID + code)
│   ├── value_objects/
│   ├── entities/
│   ├── services/    # domain services (lógica que no pertenece a una sola entidad)
│   └── repositories/ # interfaces (puertos); las implementaciones viven en infrastructure
├── application/     # casos de uso (interactors), DTOs, puertos de infra   [fase 2]
├── infrastructure/  # SQLAlchemy, auth JWT, filtro multi-tenant, storage   [fase 3]
└── presentation/    # API FastAPI / controllers                           [fase 4]
```

La **regla de dependencia** apunta hacia adentro: `domain` no importa de ninguna otra capa;
`application` solo de `domain`; `infrastructure`/`presentation` de las internas.

## Convenciones del dominio

- **Value Objects**: `@dataclass(frozen=True)`, validan invariantes en `__post_init__`.
- **Entidades / agregados**: `@dataclass` mutable; la mutación pasa por métodos que
  preservan invariantes (p. ej. la máquina de estados de `Appointment`).
- **Identidad**: UUID (`*Id`) como clave real; un `code` legible aparte para la UI
  (`P-00142`, `A-2401`, `REC-2026-0512-CR`).
- **Multi-tenant**: toda entidad de negocio lleva `tenant_id`; el filtrado por tenant es
  responsabilidad de los repositorios (fase 3), no del caller.

## Comandos

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/ruff check src
```
