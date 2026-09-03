"""Estimated tax liability from the income a worker has actually logged."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import analytics
import db_service
import tax_rules
from database import get_db
from deps import current_worker
from models import User
from schemas import TaxSummary

router = APIRouter(prefix="/api/tax", tags=["tax"])

# A tax year's worth of rows. Unlike the charts, this deliberately reaches back
# as far as the ledger goes: annualising from a short window when a long history
# exists would throw away the better evidence.
_LEDGER_FETCH_LIMIT = 500


@router.get("/summary", response_model=TaxSummary)
def tax_summary(
    deductions: float = Query(
        0.0,
        ge=0,
        description="Documented expenses to claim. Ignored under presumptive taxation.",
    ),
    presumptive: bool = Query(
        True, description="Use section 44AD presumptive taxation. Usually the lower liability."
    ),
    user: User = Depends(current_worker),
    db: Session = Depends(get_db),
) -> dict:
    """Annualises logged payouts and estimates the tax on them.

    Income comes from the same aggregation the expense tracker charts, so the
    figure a worker is told to set aside always reconciles with the income they
    can see.
    """
    rows = db_service.get_transactions(db, user_id=user.id, limit=_LEDGER_FETCH_LIMIT)

    payouts = [r for r in rows if r.get("transaction_type") == analytics.INCOME_TYPE]
    gross = sum(abs(float(r.get("amount") or 0.0)) for r in payouts)

    return tax_rules.estimate(
        gross_income_observed=gross,
        observed_days=analytics.observed_days(payouts),
        deductions=deductions,
        use_presumptive=presumptive,
    )
