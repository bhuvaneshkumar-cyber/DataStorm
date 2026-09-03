"""Expense tracker, sweep ledger, and the dashboard aggregate.

Every route here is scoped to the caller's own token. The old
`/api/users/{user_id}/dashboard` shape is gone on purpose: a user id in the path
is an invitation to read someone else's finances by editing the URL.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

import analytics
import db_service
from database import get_db
from deps import current_worker
from models import User
from schemas import (
    DashboardStats,
    ExpenseSummary,
    SweepCreate,
    SweepOut,
    TransactionCreate,
    TransactionCreated,
    TransactionOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["money"])

# Enough rows to cover a quarter of daily logging without pulling a whole
# history into memory for a chart that only draws 90 buckets.
_LEDGER_FETCH_LIMIT = 500


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    limit: int = Query(50, gt=0, le=500, description="Max records to return."),
    user: User = Depends(current_worker),
    db: Session = Depends(get_db),
) -> list[dict]:
    """The caller's transactions, newest first."""
    return db_service.get_transactions(db, user_id=user.id, limit=limit)


@router.post(
    "/transactions", response_model=TransactionCreated, status_code=status.HTTP_201_CREATED
)
def create_transaction(
    payload: TransactionCreate,
    user: User = Depends(current_worker),
    db: Session = Depends(get_db),
) -> dict:
    """Logs an expense or an earning and reports the sweep it would trigger.

    The sweep is advised, not executed: authorizing it is a separate, explicit
    act on POST /api/sweeps, because money leaving an account should never be a
    side effect of recording that it arrived.
    """
    return db_service.add_transaction(
        db=db,
        user_id=user.id,
        amount=payload.amount,
        transaction_type=payload.transaction_type,
        merchant=payload.merchant,
        category=payload.category,
        threshold=payload.threshold,
        mandate_limit=payload.mandate_limit,
    )


@router.get("/expenses/summary", response_model=ExpenseSummary)
def expense_summary(
    window_days: int = Query(90, ge=7, le=730, description="Days of history to summarise."),
    user: User = Depends(current_worker),
    db: Session = Depends(get_db),
) -> dict:
    """Cash-flow totals, daily and monthly series, and the category splits."""
    rows = db_service.get_transactions(db, user_id=user.id, limit=_LEDGER_FETCH_LIMIT)
    return analytics.summarise(rows, window_days=window_days)


@router.get("/sweeps", response_model=list[SweepOut])
def list_sweeps(
    limit: int = Query(50, gt=0, le=500, description="Max records to return."),
    user: User = Depends(current_worker),
    db: Session = Depends(get_db),
) -> list[dict]:
    """The caller's savings sweeps, newest first."""
    return db_service.get_sweeps(db, user_id=user.id, limit=limit)


@router.post("/sweeps", response_model=SweepOut, status_code=status.HTTP_201_CREATED)
def authorize_sweep(
    payload: SweepCreate,
    user: User = Depends(current_worker),
    db: Session = Depends(get_db),
) -> dict:
    """Records an authorized sweep into the Resilience Stash."""
    sweep = db_service.execute_sweep(
        db=db,
        user_id=user.id,
        sweep_amount=payload.sweep_amount,
        transaction_id=payload.transaction_id,
        reason=payload.reason,
    )
    return db_service.sweep_to_dict(sweep, include_user=True)


@router.get("/dashboard", response_model=DashboardStats)
def dashboard(
    user: User = Depends(current_worker), db: Session = Depends(get_db)
) -> dict:
    """Stash balance, the rolling income baseline, and the latest sweeps."""
    return db_service.get_user_dashboard_stats(db, user_id=user.id)
