"""FastAPI app: transaction ingestion, sweep ledger, and dashboard aggregates.

Thin HTTP layer only — all persistence and calculation lives in db_service.py
and savings.py, so this module stays readable as the API contract itself.
"""

import logging
import uuid
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import db_service
from database import check_db_connection, get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

VALID_TRANSACTION_TYPES = ("debit", "platform_payout")

app = FastAPI(
    title="DataStrom Financial Engine API",
    description="Backend service for Gig worker micro-savings sweeps connected to Supabase PostgreSQL",
    version="1.0.0",
)

# Hackathon MVP: wide open so the dashboard and mobile clients can call directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


# Pydantic Schemas
class TransactionCreate(BaseModel):
    user_id: uuid.UUID
    amount: float = Field(..., gt=0, description="Transaction amount in rupees")
    transaction_type: str = Field(..., description="'debit' or 'platform_payout'")
    merchant: Optional[str] = None
    threshold: Optional[float] = Field(100.0, gt=0)
    mandate_limit: Optional[float] = Field(1000.0, gt=0)


class SweepCreate(BaseModel):
    user_id: uuid.UUID
    sweep_amount: float = Field(..., gt=0)
    transaction_id: Optional[uuid.UUID] = None
    reason: Optional[str] = "UPI AutoPay sweep authorized"


@app.get("/")
def read_root() -> dict:
    return {
        "service": "DataStrom Financial Engine API",
        "status": "online",
        "docs_url": "/docs",
    }


@app.get("/health")
def health_check() -> JSONResponse:
    """Liveness plus a live Supabase PostgreSQL connection probe."""
    db_status = check_db_connection()
    healthy = db_status.get("status") == "connected"
    return JSONResponse(
        status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "service_status": "healthy" if healthy else "degraded",
            "database": db_status,
        },
    )


@app.get("/api/transactions")
def list_transactions(
    user_id: Optional[uuid.UUID] = None,
    limit: int = Query(50, gt=0, le=500, description="Max records to return."),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Fetches transaction records from Supabase."""
    return db_service.get_transactions(db, user_id=user_id, limit=limit)


@app.post("/api/transactions", status_code=status.HTTP_201_CREATED)
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_db)) -> dict:
    """Ingests bank debits / platform payouts and evaluates savings sweep eligibility."""
    if payload.transaction_type not in VALID_TRANSACTION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"transaction_type must be one of: {', '.join(VALID_TRANSACTION_TYPES)}",
        )

    return db_service.add_transaction(
        db=db,
        user_id=payload.user_id,
        amount=payload.amount,
        transaction_type=payload.transaction_type,
        merchant=payload.merchant,
        threshold=payload.threshold,
        mandate_limit=payload.mandate_limit,
    )


@app.get("/api/sweeps")
def list_sweeps(
    user_id: Optional[uuid.UUID] = None,
    limit: int = Query(50, gt=0, le=500, description="Max records to return."),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Fetches savings sweep records from Supabase."""
    return db_service.get_sweeps(db, user_id=user_id, limit=limit)


@app.post("/api/sweeps", status_code=status.HTTP_201_CREATED)
def authorize_sweep(payload: SweepCreate, db: Session = Depends(get_db)) -> dict:
    """Records an authorized savings sweep into the savings_sweeps ledger."""
    sweep = db_service.execute_sweep(
        db=db,
        user_id=payload.user_id,
        sweep_amount=payload.sweep_amount,
        transaction_id=payload.transaction_id,
        reason=payload.reason,
    )
    return {
        "sweep_id": str(sweep.id),
        "user_id": str(sweep.user_id),
        "sweep_amount": float(sweep.sweep_amount),
        "reason": sweep.reason,
        "created_at": sweep.created_at,
    }


@app.get("/api/users/{user_id}/dashboard")
def get_dashboard(user_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Returns total savings stash, 30-day baseline income, and recent sweep records."""
    return db_service.get_user_dashboard_stats(db, user_id=user_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
