"""Micro-insurance recommendations for the signed-in worker.

A thin composition layer, and deliberately so: the ranking logic lives in the
scoring service beside the risk model it depends on, and the profile it needs
lives here beside the database. This route joins the two so the browser does not
have to, and so a recommendation can never be produced from a risk score the
browser chose for itself.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import scoring_client
from database import get_db
from deps import current_worker
from models import User
from routers.credit import scored_profile

router = APIRouter(prefix="/api/insurance", tags=["insurance"])


@router.get("/recommendations")
def recommendations(
    user: User = Depends(current_worker), db: Session = Depends(get_db)
) -> dict:
    """Ranked cover types for this worker's risk profile and employment type."""
    scored = scored_profile(db, user)
    score = scored["score"]
    profile = scored["profile"]

    try:
        result = scoring_client.recommend_insurance(
            {
                "credit_score": score["final_score"],
                "risk_tier": (score.get("risk_assessment") or {}).get("risk_tier"),
                # Falls back to the derived platform category when a worker has
                # not said what they do, which is true often enough that failing
                # the request instead would be the wrong trade.
                "employment_type": user.employment_type or profile["primary_gig_platform"],
                "average_weekly_payout": profile["average_weekly_payout"],
                "resilience_stash_balance": profile["resilience_stash_balance"],
                "active_platform_hours_per_week": profile["active_platform_hours_per_week"],
                "payout_volatility_index": profile["payout_volatility_index"],
                "age": profile["age"],
            }
        )
    except scoring_client.ScoringUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    return {"profile": profile, "score": score, "recommendation": result}
