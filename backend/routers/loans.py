"""Emergency loans: a worker's applications, and a lender's queue.

The two halves live in one module because they are two views of one table and
splitting them is how the fields a lender sees drift from the fields a worker
submitted. They are separated by dependency, not by file: worker routes require
a worker token, lender routes a lender token, and neither can reach the other's.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import loan_policy
from database import get_db
from deps import current_lender, current_worker
from models import LOAN_PENDING, LoanApplication, User, utcnow
from routers.credit import scored_profile
from schemas import LoanApplicationCreate, LoanApplicationOut, LoanDecision, LoanEligibility

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/loans", tags=["loans"])


def _to_out(application: LoanApplication, include_applicant: bool = False) -> dict:
    """One serialization shape, so the two audiences cannot see different fields."""
    payload = {
        "id": application.id,
        "user_id": application.user_id,
        "amount": float(application.amount),
        "tenor_months": int(application.tenor_months),
        "purpose": application.purpose,
        "credit_score": float(application.credit_score),
        "risk_grade": application.risk_grade,
        "risk_tier": application.risk_tier,
        "indicative_interest_rate_pct": (
            float(application.indicative_interest_rate_pct)
            if application.indicative_interest_rate_pct is not None
            else None
        ),
        "max_credit_limit_inr": (
            float(application.max_credit_limit_inr)
            if application.max_credit_limit_inr is not None
            else None
        ),
        "engine_decision": application.engine_decision,
        "status": application.status,
        "lender_note": application.lender_note,
        "created_at": application.created_at,
        "decided_at": application.decided_at,
    }
    if include_applicant and application.applicant is not None:
        payload["applicant_name"] = application.applicant.name
        payload["applicant_email"] = application.applicant.email
    return payload


# --------------------------------------------------------------------------- #
# Worker
# --------------------------------------------------------------------------- #


@router.get("/eligibility", response_model=LoanEligibility)
def check_eligibility(
    user: User = Depends(current_worker), db: Session = Depends(get_db)
) -> dict:
    """What this worker could ask for, before they fill in a form.

    Answering before the form exists is the point: an application refused at
    submission is a rejection on the record, and this avoids creating one.
    """
    scored = scored_profile(db, user)
    return loan_policy.evaluate(
        scored["score"]["final_score"], scored["score"].get("risk_assessment")
    )


@router.get("", response_model=list[LoanApplicationOut])
def my_applications(
    user: User = Depends(current_worker), db: Session = Depends(get_db)
) -> list[dict]:
    """This worker's own applications, newest first."""
    applications = (
        db.query(LoanApplication)
        .filter(LoanApplication.user_id == user.id)
        .order_by(LoanApplication.created_at.desc())
        .all()
    )
    return [_to_out(application) for application in applications]


@router.post("", response_model=LoanApplicationOut, status_code=status.HTTP_201_CREATED)
def apply(
    payload: LoanApplicationCreate,
    user: User = Depends(current_worker),
    db: Session = Depends(get_db),
) -> dict:
    """Applies for an emergency loan, gated on a freshly derived score.

    The score is computed here and frozen onto the row. Re-deriving it rather
    than accepting it from the request is what makes the gate real; freezing it
    is what stops a later drift from rewriting what a lender decided on.
    """
    open_application = (
        db.query(LoanApplication)
        .filter(LoanApplication.user_id == user.id, LoanApplication.status == LOAN_PENDING)
        .first()
    )
    if open_application:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have an application awaiting a decision.",
        )

    scored = scored_profile(db, user)
    score = scored["score"]
    assessment = score.get("risk_assessment") or {}

    verdict = loan_policy.evaluate(
        score["final_score"],
        assessment,
        requested_amount=payload.amount,
        requested_tenor=payload.tenor_months,
    )
    if not verdict["eligible"]:
        # 422 rather than 403: the request is well-formed and the caller is
        # permitted here, the terms asked for are simply not available to them.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=verdict["reason"]
        )

    application = LoanApplication(
        user_id=user.id,
        amount=payload.amount,
        tenor_months=payload.tenor_months,
        purpose=payload.purpose,
        credit_score=score["final_score"],
        risk_grade=(assessment.get("risk_grade") or {}).get("code"),
        risk_tier=assessment.get("risk_tier"),
        indicative_interest_rate_pct=assessment.get("indicative_interest_rate_pct"),
        max_credit_limit_inr=assessment.get("max_credit_limit_inr"),
        engine_decision=assessment.get("decision"),
        status=LOAN_PENDING,
    )

    try:
        db.add(application)
        db.commit()
        db.refresh(application)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to record loan application for user %s", user.id)
        raise

    return _to_out(application)


# --------------------------------------------------------------------------- #
# Lender
# --------------------------------------------------------------------------- #


# The lender guard is declared as a route dependency rather than a parameter:
# this route authorizes on the role but never needs the lender row itself.
@router.get(
    "/queue",
    response_model=list[LoanApplicationOut],
    dependencies=[Depends(current_lender)],
)
def lender_queue(
    status_filter: str | None = Query(
        None, alias="status", description="pending, approved or rejected. Omit for all."
    ),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Every application a lender can act on, oldest first.

    Oldest first because this is a work queue: newest-first would leave the
    applications that have waited longest permanently at the bottom.
    """
    query = db.query(LoanApplication)
    if status_filter:
        query = query.filter(LoanApplication.status == status_filter)

    applications = query.order_by(LoanApplication.created_at.asc()).all()
    return [_to_out(application, include_applicant=True) for application in applications]


@router.patch("/{application_id}", response_model=LoanApplicationOut)
def decide(
    application_id: uuid.UUID,
    payload: LoanDecision,
    lender: User = Depends(current_lender),
    db: Session = Depends(get_db),
) -> dict:
    """Approves or rejects one application."""
    application = (
        db.query(LoanApplication).filter(LoanApplication.id == application_id).first()
    )
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such loan application."
        )
    if application.status != LOAN_PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This application was already {application.status}.",
        )

    application.status = payload.status
    application.lender_note = payload.lender_note
    application.lender_id = lender.id
    application.decided_at = utcnow()

    try:
        db.commit()
        db.refresh(application)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to record decision on application %s", application_id)
        raise

    return _to_out(application, include_applicant=True)
