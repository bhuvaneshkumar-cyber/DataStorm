import uuid
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional

from database import get_db, check_db_connection
import db_service
import models

app = FastAPI(
    title="DataStrom Financial Engine API",
    description="Backend service for Gig worker micro-savings sweeps connected to Supabase PostgreSQL",
    version="1.0.0",
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic Schemas
class TransactionCreate(BaseModel):
    user_id: uuid.UUID
    amount: float = Field(..., gt=0, description="Transaction amount in rupees")
    transaction_type: str = Field(..., description="'debit' or 'platform_payout'")
    merchant: Optional[str] = None
    threshold: Optional[float] = 100.0
    mandate_limit: Optional[float] = 1000.0


class SweepCreate(BaseModel):
    user_id: uuid.UUID
    sweep_amount: float = Field(..., gt=0)
    transaction_id: Optional[uuid.UUID] = None
    reason: Optional[str] = "UPI AutoPay sweep authorized"


@app.get("/")
def read_root():
    return {
        "service": "DataStrom Financial Engine API",
        "status": "online",
        "docs_url": "/docs",
    }


@app.get("/health")
def health_check():
    """Health check endpoint that validates Supabase PostgreSQL connection status."""
    db_status = check_db_connection()
    status_code = status.HTTP_200_OK if db_status.get("status") == "connected" else status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "service_status": "healthy",
        "database": db_status,
    }


@app.get("/api/transactions")
def list_transactions(user_id: Optional[uuid.UUID] = None, limit: int = 50, db: Session = Depends(get_db)):
    """Fetches transaction records from Supabase."""
    return db_service.get_transactions(db, user_id=user_id, limit=limit)


@app.post("/api/transactions", status_code=status.HTTP_201_CREATED)
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_db)):
    """Ingests bank debits / platform payouts and evaluates savings sweep eligibility."""
    if payload.transaction_type not in ("debit", "platform_payout"):
        raise HTTPException(status_code=400, detail="transaction_type must be 'debit' or 'platform_payout'")

    result = db_service.add_transaction(
        db=db,
        user_id=payload.user_id,
        amount=payload.amount,
        transaction_type=payload.transaction_type,
        merchant=payload.merchant,
        threshold=payload.threshold,
        mandate_limit=payload.mandate_limit,
    )
    return result


@app.get("/api/sweeps")
def list_sweeps(user_id: Optional[uuid.UUID] = None, limit: int = 50, db: Session = Depends(get_db)):
    """Fetches savings sweep records from Supabase."""
    return db_service.get_sweeps(db, user_id=user_id, limit=limit)


@app.post("/api/sweeps", status_code=status.HTTP_201_CREATED)
def authorize_sweep(payload: SweepCreate, db: Session = Depends(get_db)):
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
def get_dashboard(user_id: uuid.UUID, db: Session = Depends(get_db)):
    """Returns total savings stash, 30-day baseline income, and recent sweep records."""
    return db_service.get_user_dashboard_stats(db, user_id=user_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
