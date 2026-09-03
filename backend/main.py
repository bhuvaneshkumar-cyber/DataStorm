"""FastAPI application assembly.

Deliberately thin. Every route lives in `routers/`, every calculation in a pure
module beside it, so this file stays readable as what it is: the list of things
the service is made of, plus the two cross-cutting concerns (CORS and the
database-fault handler) that cannot live in any one router.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

import bootstrap
import scoring_client
from database import check_db_connection
from routers import ALL_ROUTERS

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger(__name__)

# Wide open by default so the dashboard can call from any dev host. Set
# CORS_ORIGINS to a comma-separated allowlist before this faces the internet:
# with credentials enabled, "*" is exactly what you do not want in production.
_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

# Recorded at startup and reported through /health, so a deployment that came up
# against a stale schema says so instead of failing one route at a time.
_schema_state: dict = {"status": "pending"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Syncs the schema on the way up, releases the scorer's pool on the way down."""
    global _schema_state
    _schema_state = bootstrap.sync_schema()
    yield
    scoring_client.close_client()


app = FastAPI(
    title="DataStrom Financial Engine API",
    description=(
        "Gig-worker financial resilience: expense tracking, platform-backed income "
        "proof, alternative credit scoring, emergency loans, tax estimates and the "
        "credit-policy bot. Backed by Supabase PostgreSQL."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(SQLAlchemyError)
async def handle_database_error(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Database faults are an availability problem, not a client error.

    Without this, a dropped Supabase connection surfaces as an opaque 500 with a
    driver stack trace in the body. 503 tells callers the request is retryable.
    """
    logger.exception("Database error while serving request")
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Database unavailable.", "error": type(exc).__name__},
    )


for router in ALL_ROUTERS:
    app.include_router(router)


@app.get("/", tags=["meta"])
def read_root() -> dict:
    return {
        "service": "DataStrom Financial Engine API",
        "status": "online",
        "docs_url": "/docs",
    }


@app.get("/health", tags=["meta"])
def health_check() -> JSONResponse:
    """Liveness, the live database probe, the schema state, and the scorer.

    The scoring service is reported but does not decide this service's health:
    most routes work without it, and marking the whole backend unhealthy because
    a dependency is down would take a working deployment out of a load balancer.
    """
    db_status = check_db_connection()
    healthy = db_status.get("status") == "connected"
    return JSONResponse(
        status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "service_status": "healthy" if healthy else "degraded",
            "database": db_status,
            "schema_sync": _schema_state,
            "scoring_service": scoring_client.health(),
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
