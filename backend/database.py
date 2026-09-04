import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

# Load environment variables from .env in backend or project root
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent

for env_path in [current_dir / ".env", root_dir / ".env", root_dir / ".env.txt"]:
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        break
else:
    load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set. Check your .env configuration.")

# SQLAlchemy 2.0+ requires postgresql:// instead of postgres://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Configure SQLAlchemy Engine with pooling for Supabase connection pooler.
# Supabase requires TLS for database connections.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,       # Automatically checks if connection is alive before using
    pool_recycle=300,         # Recycle connections every 5 minutes
    pool_size=10,             # Keep 10 persistent connections in pool
    max_overflow=20,          # Allow up to 20 temporary overflow connections
    connect_args={"connect_timeout": 10, "sslmode": "require"},
)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI / context dependency generator for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> dict:
    """Tests the database connection against Supabase PostgreSQL."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1;")).scalar()
            return {"status": "connected", "result": result, "database_url_configured": True}
    except Exception as e:
        return {"status": "error", "error": str(e), "database_url_configured": True}
