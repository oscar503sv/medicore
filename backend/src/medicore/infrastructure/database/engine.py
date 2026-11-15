"""SQLAlchemy engine and session factory."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from medicore.infrastructure.config import get_settings

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_settings().database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


def get_session() -> Session:
    """Open a session (caller is responsible for closing it)."""
    return get_session_factory()()


@contextmanager
def owner_session() -> Iterator[Session]:
    """Session as the schema owner, for the few operations the API role cannot do (the demo
    purge). Its own short-lived engine: the owner never joins the serving pool."""
    engine = create_engine(get_settings().owner_database_url, poolclass=NullPool)
    try:
        with Session(engine, expire_on_commit=False) as session:
            yield session
    finally:
        engine.dispose()
