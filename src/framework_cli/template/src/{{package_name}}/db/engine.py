from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config.settings import get_settings


def build_engine(
    url: str, *, pool_size: int | None = None, max_overflow: int | None = None
) -> Engine:
    """Create a connection-pooled Engine for the given SQLAlchemy URL.

    pool_size / max_overflow are optional: when omitted the SQLAlchemy QueuePool defaults
    apply. Callers that plan against a fixed connection budget can pass explicit values so the
    engine's real pool matches their accounted footprint.
    """
    extra: dict[str, int] = {}
    if pool_size is not None:
        extra["pool_size"] = pool_size
    if max_overflow is not None:
        extra["max_overflow"] = max_overflow
    return create_engine(url, pool_pre_ping=True, future=True, **extra)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


engine: Engine = build_engine(get_settings().database_url)
SessionLocal: sessionmaker[Session] = build_session_factory(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: a session per request, always closed."""
    with SessionLocal() as session:
        yield session


def dispose_engine() -> None:
    """Dispose the engine's connection pool — called on graceful shutdown."""
    engine.dispose()
