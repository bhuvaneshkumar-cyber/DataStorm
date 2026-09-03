"""Alternative credit score for the signed-in worker.

The score is always derived here from the worker's own recorded evidence and
scored by the scoring service. Nothing about it is accepted from the browser,
which is what lets a loan application carry a score a lender can trust.

Statement upload stays on the scoring service and is called from the browser
directly: the file never needs to touch this process, and routing it through
here would mean holding personal financial documents in a second place.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import analytics
import db_service
import income_profile
import scoring_client
from database import get_db
from deps import current_worker
from models import User
from routers.platforms import build_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/credit", tags=["credit"])

_LEDGER_FETCH_LIMIT = 500


def scored_profile(db: Session, user: User) -> dict:
    """Profile plus its score, the pair every credit-aware route needs.

    A scoring outage is a 503 rather than a fabricated score: an approximate
    number here would end up written onto a loan application as though it were
    an assessment.
    """
    profile = build_profile(db, user)
    try:
        score = scoring_client.score_applicant(income_profile.scoring_payload(profile))
    except scoring_client.ScoringUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return {"profile": profile, "score": score}


@router.get("/score")
def read_score(user: User = Depends(current_worker), db: Session = Depends(get_db)) -> dict:
    """The caller's current score, with the profile and assumptions behind it."""
    return scored_profile(db, user)


@router.get("/metrics")
def read_metrics(user: User = Depends(current_worker), db: Session = Depends(get_db)) -> dict:
    """Per-metric breakdown of the caller's own logged ledger.

    Answers "why is my score what it is" from the transactions they have already
    entered, so a worker gets the same explanation an uploaded statement would
    give without having to find a statement first.
    """
    rows = db_service.get_transactions(db, user_id=user.id, limit=_LEDGER_FETCH_LIMIT)
    ledger = analytics.to_ledger(rows)

    if not ledger:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "There are no dated transactions to analyse yet. Log a few payouts and "
                "expenses, or upload a statement on the Credit page."
            ),
        )

    profile = build_profile(db, user)
    stats = db_service.get_user_dashboard_stats(db, user_id=user.id)

    try:
        return scoring_client.analyze_transactions(
            ledger,
            platform_rating=profile["platform_customer_rating"],
            opening_balance=stats["total_stash_balance"],
        )
    except scoring_client.ScoringUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
