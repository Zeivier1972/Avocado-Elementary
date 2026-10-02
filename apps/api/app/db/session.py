"""Database engine and session management (dialect-portable)."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

_connect_args = {}
if settings.sqlalchemy_url.startswith("sqlite"):
    # Needed for SQLite when used across FastAPI's threadpool.
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.sqlalchemy_url,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
