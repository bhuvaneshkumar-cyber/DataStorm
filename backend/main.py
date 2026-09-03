import uuid
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional

from database import get_db, check_db_connection
import db_service
import models  # noqa: F401  -- imported so SQLAlchemy registers the mapped tables
import webhooks

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


class SweepAuthorizeRequest(BaseModel):
    """Body of POST /webhooks/sweep - sweep whatever has accumulated so far."""

    user_id: uuid.UUID
    threshold: float = Field(100.0, gt=0)
    mandate_limit: float = Field(1000.0, gt=0)


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


# ---------------------------------------------------------------------------
# Webhook ingestion (ported from the retired Node/Express service)
# ---------------------------------------------------------------------------


async def authenticated_body(
    request: Request,
    x_webhook_signature: Optional[str] = Header(default=None),
    x_webhook_secret: Optional[str] = Header(default=None),
):
    """Authenticates the caller against the *raw* body, then parses it.

    The HMAC must be computed over the exact bytes on the wire, so the body is
    read here rather than through a Pydantic model - re-serialising it first
    would change the bytes and break every signature.
    """
    raw_body = await request.body()
    try:
        webhooks.authenticate(raw_body, x_webhook_signature, x_webhook_secret)
    except webhooks.WebhookAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    try:
        return await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON.") from exc


@app.post("/webhooks/transaction")
def ingest_transaction_webhook(payload: dict = Depends(authenticated_body), db: Session = Depends(get_db)):
    """Bank debit / platform payout events: round up, smooth income, sweep."""
    try:
        event = webhooks.parse_event(payload)
    except webhooks.WebhookValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return db_service.process_webhook_event(db, event)


@app.post("/webhooks/sweep")
def authorize_pending_sweep(payload: dict = Depends(authenticated_body), db: Session = Depends(get_db)):
    """Manually authorises a sweep of the caller's accumulated contributions."""
    try:
        body = SweepAuthorizeRequest(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid sweep request: {exc}") from exc
    return db_service.authorize_manual_sweep(
        db, body.user_id, threshold=body.threshold, mandate_limit=body.mandate_limit
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
