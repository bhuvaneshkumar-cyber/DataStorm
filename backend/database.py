"""SQLAlchemy engine, session factory, and connection health probe.

A missing or unreachable DATABASE_URL is reported through /health and a 503 on
data routes rather than raised at import time — an unimportable module takes the
health endpoint down with it, which is exactly when you most need it to answer.
"""

import logging
import os
from pathlib import Path
from typing import Iterator, Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, declarative_base, sessionmaker

logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent

Base = declarative_base()


class DatabaseUnavailable(SQLAlchemyError):
    """Raised when no engine could be built. Subclasses SQLAlchemyError so the
    app's existing database-error handler turns it into a 503 automatically."""


def _load_environment() -> None:
    """Loads the first .env found in backend/ then the project root."""
    for env_path in (CURRENT_DIR / ".env", ROOT_DIR / ".env", ROOT_DIR / ".env.txt"):
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
            return
    load_dotenv()


def _normalize_url(url: str) -> str:
    """SQLAlchemy 2.0 dropped the legacy `postgres://` scheme."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def _build_engine(url: Optional[str]) -> Optional[Engine]:
    """Builds a pooled engine, or None if the URL is missing/invalid."""
    if not url:
        logger.error("DATABASE_URL is not set. Database routes will return 503.")
        return None

    normalized = _normalize_url(url)

    # Pool sizing and connect_timeout are psycopg2/queue-pool options. SQLite
    # uses a SingletonThreadPool and its own DBAPI, and passing them there is a
    # hard TypeError -- which is how a perfectly reasonable "point it at SQLite
    # for local dev" ends up looking like a broken application instead.
    options: dict = {"pool_pre_ping": True}
    if not normalized.startswith("sqlite"):
        options.update(
            pool_recycle=300,  # Supabase's pooler closes idle connections
            pool_size=10,
            max_overflow=20,
            connect_args={"connect_timeout": 10},
        )

    try:
        return create_engine(normalized, **options)
    except Exception:
        # Broad on purpose. create_engine imports the DBAPI driver eagerly, so a
        # missing psycopg2 raises ModuleNotFoundError -- not a SQLAlchemyError --
        # and letting that escape would kill this module at import time, taking
        # /health down with it. Degrading to "no engine" is the whole point of
        # this function, and every caller already handles engine being None.
        logger.exception("Failed to create the SQLAlchemy engine")
        return None


_load_environment()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = _build_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is always closed."""
    if SessionLocal is None:
        raise DatabaseUnavailable("DATABASE_URL is not configured.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> dict:
    """Probes the live connection. Never raises — this backs /health."""
    if engine is None:
        return {
            "status": "error",
            "error": "DATABASE_URL is not configured.",
            "database_url_configured": False,
        }
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1;")).scalar()
        return {"status": "connected", "result": result, "database_url_configured": True}
    except SQLAlchemyError as exc:
        logger.warning("Database health probe failed: %s", exc)
        return {"status": "error", "error": str(exc), "database_url_configured": True}
