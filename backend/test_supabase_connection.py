"""Probe the configured Supabase PostgreSQL connection."""

import os
import traceback
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

def main():
    load_dotenv(Path(__file__).resolve().parent / ".env")
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured in backend/.env")

    try:
        with psycopg2.connect(database_url, connect_timeout=10, sslmode="require") as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT NOW();")
                print(f"Connected successfully. SELECT NOW(): {cursor.fetchone()[0]}")
    except Exception:
        print("Supabase connection failed; full traceback:")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
