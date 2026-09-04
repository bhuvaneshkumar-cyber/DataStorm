import uuid
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
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

from database import get_db, check_db_connection
import db_service
import models  # noqa: F401  -- imported so SQLAlchemy registers the mapped tables
import webhooks

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


# Pydantic Schemas
class TransactionCreate(BaseModel):
    user_id: uuid.UUID
    amount: float = Field(..., gt=0, description="Transaction amount in rupees")
    transaction_type: str = Field(..., description="'debit' or 'payout'")
    merchant: Optional[str] = None
    threshold: Optional[float] = 100.0
    mandate_limit: Optional[float] = 1000.0


for router in ALL_ROUTERS:
    app.include_router(router)


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


@app.get("/health", tags=["meta"])
def health_check() -> JSONResponse:
    """Liveness, the live database probe, the schema state, and the scorer.

    The scoring service is reported but does not decide this service's health:
    most routes work without it, and marking the whole backend unhealthy because
    a dependency is down would take a working deployment out of a load balancer.
    """
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
    if payload.transaction_type not in webhooks.WEBHOOK_TYPE_TO_LEDGER:
        raise HTTPException(status_code=400, detail="transaction_type must be 'debit' or 'payout'")

    result = db_service.add_transaction(
        db=db,
        user_id=payload.user_id,
        amount=payload.amount,
        transaction_type=webhooks.WEBHOOK_TYPE_TO_LEDGER[payload.transaction_type],
        merchant=payload.merchant,
        threshold=payload.threshold,
        mandate_limit=payload.mandate_limit,
    )


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
