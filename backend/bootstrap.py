"""Idempotent schema sync, run once at application startup.

The Supabase database predates authentication, connected platforms and loans,
so `create_all` alone is not enough: it creates the *missing tables* but never
adds a column to a table that already exists. This closes that gap by diffing
each mapped table's live columns (via `inspect`) against what the ORM
declares, and adding whatever is missing.

An earlier version of this file kept a hand-written list of "columns added
after the original schema shipped" instead of diffing. That list has to be
remembered and updated by hand every time a column is added to an existing
table -- miss one and a live Supabase database silently keeps missing a
column the ORM (and every route built on it) assumes exists, while a fresh
local database created via `create_all` never shows the gap. Deriving the
list from the models instead means it can no longer drift out of sync.

Deliberately non-fatal. A service that refuses to boot because it could not
reach the database also cannot serve `/health`, which is precisely the
endpoint you need answering when the database is down.

ponytail: hand-rolled additive sync, still. Move to Alembic the first time a
change needs to drop or rewrite a column, which this cannot express.
"""

import logging
from typing import List

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.schema import Column

import models  # noqa: F401  (imported for its side effect: registering the tables)
from database import Base, engine

logger = logging.getLogger(__name__)


def _add_column_ddl(table_name: str, column: Column) -> str:
    """DDL to add one missing column, backfilling existing rows when possible.

    A NOT NULL column with no server-side default cannot be added to a table
    that may already hold rows, so one is added nullable instead -- with a
    loud warning -- rather than letting the ALTER TABLE fail outright.
    """
    ddl_type = column.type.compile(dialect=engine.dialect)
    base = f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{column.name}" {ddl_type}'

    if column.nullable or column.server_default is None:
        if not column.nullable:
            logger.warning(
                "%s.%s is NOT NULL with no server_default; adding it nullable so "
                "existing rows are not broken. Give the column a server_default "
                "in models.py to close this gap.",
                table_name,
                column.name,
            )
        return base

    default_clause = column.server_default.arg  # a TextClause from server_default=text(...)
    default_sql = getattr(default_clause, "text", default_clause)
    return f"{base} NOT NULL DEFAULT {default_sql}"


def sync_schema() -> dict:
    """Creates missing tables and columns. Returns what it did, never raises."""
    if engine is None:
        return {"status": "skipped", "reason": "DATABASE_URL is not configured."}

    created: List[str] = []
    altered: List[str] = []

    try:
        inspector = inspect(engine)
        before = set(inspector.get_table_names())
        Base.metadata.create_all(bind=engine)
        inspector = inspect(engine)  # re-inspect: create_all just changed the schema
        created = sorted(set(inspector.get_table_names()) - before)

        # ADD COLUMN IF NOT EXISTS is Postgres syntax. On any other dialect the
        # tables create_all just made already carry every column, so there is
        # nothing to back-fill and skipping is correct rather than a limitation.
        if engine.dialect.name == "postgresql":
            with engine.begin() as connection:
                for table in Base.metadata.sorted_tables:
                    if table.name in created:
                        continue  # brand new table: create_all already has every column
                    live_columns = {col["name"] for col in inspector.get_columns(table.name)}
                    for column in table.columns:
                        if column.name in live_columns:
                            continue
                        connection.execute(text(_add_column_ddl(table.name, column)))
                        altered.append(f"{table.name}.{column.name}")
    except SQLAlchemyError as exc:
        logger.exception("Schema sync failed; data routes will report the error per request.")
        return {"status": "error", "error": str(exc)}

    if created:
        logger.info("Schema sync created tables: %s", ", ".join(created))
    if altered:
        logger.info("Schema sync added columns: %s", ", ".join(altered))
    return {"status": "ok", "tables_created": created, "columns_ensured": altered}
