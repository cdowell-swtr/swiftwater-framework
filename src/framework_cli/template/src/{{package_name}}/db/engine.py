from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config.settings import get_settings


def build_engine(url: str) -> Engine:
    """Create a connection-pooled Engine for the given SQLAlchemy URL."""
    return create_engine(url, pool_pre_ping=True, future=True)


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
