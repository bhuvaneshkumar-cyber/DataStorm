"""Idempotent schema sync, run once at application startup.

The Supabase database predates authentication, connected platforms and loans,
so `create_all` alone is not enough: it creates the *missing tables* but never
adds a column to a table that already exists. The handful of `ADD COLUMN IF NOT
EXISTS` statements below close that gap without pulling in a migration tool for
what is, so far, six columns.

Deliberately non-fatal. A service that refuses to boot because it could not
reach the database also cannot serve `/health`, which is precisely the endpoint
you need answering when the database is down.

ponytail: hand-rolled additive sync. Move to Alembic the first time a change
needs to drop or rewrite a column, which this cannot express.
"""

import logging
from typing import List, Tuple

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

import models  # noqa: F401  (imported for its side effect: registering the tables)
from database import Base, engine

logger = logging.getLogger(__name__)

# (table, column, DDL type) for columns added after the original schema shipped.
# Types are deliberately permissive: this file's job is to make old databases
# loadable, not to enforce constraints the ORM already states.
_ADDED_COLUMNS: Tuple[Tuple[str, str, str], ...] = (
    ("users", "password_hash", "VARCHAR"),
    ("users", "role", "VARCHAR NOT NULL DEFAULT 'worker'"),
    ("users", "language", "VARCHAR NOT NULL DEFAULT 'en'"),
    ("users", "employment_type", "VARCHAR"),
    ("users", "date_of_birth", "DATE"),
    ("transactions", "category", "VARCHAR"),
)


def sync_schema() -> dict:
    """Creates missing tables and columns. Returns what it did, never raises."""
    if engine is None:
        return {"status": "skipped", "reason": "DATABASE_URL is not configured."}

    created: List[str] = []
    altered: List[str] = []

    try:
        before = set(inspect(engine).get_table_names())
        Base.metadata.create_all(bind=engine)
        created = sorted(set(inspect(engine).get_table_names()) - before)

        # ADD COLUMN IF NOT EXISTS is Postgres syntax. On any other dialect the
        # tables create_all just made already carry every column, so there is
        # nothing to back-fill and skipping is correct rather than a limitation.
        if engine.dialect.name == "postgresql":
            with engine.begin() as connection:
                for table, column, ddl in _ADDED_COLUMNS:
                    result = connection.execute(
                        text(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{column}" {ddl}')
                    )
                    # rowcount is -1 for DDL; the useful signal is that it ran.
                    del result
                    altered.append(f"{table}.{column}")
    except SQLAlchemyError as exc:
        logger.exception("Schema sync failed; data routes will report the error per request.")
        return {"status": "error", "error": str(exc)}

    if created:
        logger.info("Schema sync created tables: %s", ", ".join(created))
    return {"status": "ok", "tables_created": created, "columns_ensured": altered}
