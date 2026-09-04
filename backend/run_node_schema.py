"""Apply the Node Supabase schema and list public tables."""

import os
import traceback
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

backend_dir = Path(__file__).resolve().parent
load_dotenv(backend_dir / ".env")
database_url = os.environ.get("DATABASE_URL")
schema_path = backend_dir / "node" / "supabase" / "001_node_savings_schema.sql"

if not database_url:
    raise RuntimeError("DATABASE_URL is not configured in backend/.env")

try:
    with psycopg2.connect(database_url, connect_timeout=15, sslmode="require") as connection:
        with connection.cursor() as cursor:
            cursor.execute(schema_path.read_text(encoding="utf-8"))
            cursor.execute(
                """
                select table_name
                from information_schema.tables
                where table_schema = 'public'
                  and table_type = 'BASE TABLE'
                order by table_name;
                """
            )
            tables = [row[0] for row in cursor.fetchall()]
        print("Schema migration completed successfully.")
        print("Public tables:")
        for table in tables:
            print(f"- {table}")
except Exception:
    print("Schema migration or table listing failed; full traceback:")
    traceback.print_exc()
    raise
