"""Application ports — infrastructure interfaces the use cases depend on (fase 2)."""

from medicore.application.ports.clock import Clock
from medicore.application.ports.code_generator import CodeGenerator
from medicore.application.ports.password_hasher import PasswordHasher
from medicore.application.ports.token_issuer import SessionClaims, TokenIssuer
from medicore.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory

__all__ = [
    "Clock",
    "CodeGenerator",
    "PasswordHasher",
    "SessionClaims",
    "TokenIssuer",
    "UnitOfWork",
    "UnitOfWorkFactory",
]
