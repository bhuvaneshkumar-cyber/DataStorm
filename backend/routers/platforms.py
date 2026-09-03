"""Connected gig platforms, and the income profile they add up to.

Connecting a platform is how a worker turns "I drive for Uber" into evidence a
lender can price. The profile route is the payoff: it collapses every connection
plus the logged ledger into the eight features the scoring service asks for, and
names every value that had to fall back to a default.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import db_service
import income_profile
from database import get_db
from deps import current_worker
from models import PlatformAccount, User
from schemas import IncomeProfile, PlatformAccountCreate, PlatformAccountOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/platforms", tags=["platforms"])

# The profile is built from the ledger, so it needs the same reach as the
# expense summary rather than the shorter list a table would show.
_LEDGER_FETCH_LIMIT = 500


def _rows_for(db: Session, user: User) -> list[dict]:
    """Platform accounts as plain dicts, the shape income_profile consumes."""
    accounts = (
        db.query(PlatformAccount)
        .filter(PlatformAccount.user_id == user.id)
        .order_by(PlatformAccount.connected_at.desc())
        .all()
    )
    return [
        {
            "id": account.id,
            "platform": account.platform,
            "account_handle": account.account_handle,
            "customer_rating": float(account.customer_rating) if account.customer_rating else None,
            "weekly_payout": float(account.weekly_payout) if account.weekly_payout else None,
            "gigs_per_week": float(account.gigs_per_week) if account.gigs_per_week else None,
            "hours_per_week": float(account.hours_per_week) if account.hours_per_week else None,
            "verified": account.verified,
            "connected_at": account.connected_at,
        }
        for account in accounts
    ]


@router.get("", response_model=list[PlatformAccountOut])
def list_platforms(
    user: User = Depends(current_worker), db: Session = Depends(get_db)
) -> list[dict]:
    """Every platform this worker has connected, most recent first."""
    return _rows_for(db, user)


@router.post("", response_model=PlatformAccountOut, status_code=status.HTTP_201_CREATED)
def connect_platform(
    payload: PlatformAccountCreate,
    user: User = Depends(current_worker),
    db: Session = Depends(get_db),
) -> PlatformAccount:
    """Connects a platform account as a source of income proof.

    Starts unverified: the figures are a declaration until a logged payout
    corroborates them, and the score reports them as such.
    """
    name = payload.platform.strip()
    existing = (
        db.query(PlatformAccount)
        .filter(PlatformAccount.user_id == user.id, PlatformAccount.platform.ilike(name))
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{name} is already connected. Update or disconnect it instead.",
        )

    account = PlatformAccount(
        user_id=user.id,
        platform=name,
        account_handle=payload.account_handle,
        customer_rating=payload.customer_rating,
        weekly_payout=payload.weekly_payout,
        gigs_per_week=payload.gigs_per_week,
        hours_per_week=payload.hours_per_week,
        verified=False,
    )

    try:
        db.add(account)
        db.commit()
        db.refresh(account)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to connect platform for user %s", user.id)
        raise

    return account


def _owned_account(db: Session, user: User, account_id: uuid.UUID) -> PlatformAccount:
    """Loads an account, refusing anything that is not the caller's.

    404 rather than 403 for someone else's row: confirming that an id exists is
    itself a leak when the ids are guessable.
    """
    account = (
        db.query(PlatformAccount)
        .filter(PlatformAccount.id == account_id, PlatformAccount.user_id == user.id)
        .first()
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such connected platform."
        )
    return account


@router.patch("/{account_id}", response_model=PlatformAccountOut)
def update_platform(
    account_id: uuid.UUID,
    payload: PlatformAccountCreate,
    user: User = Depends(current_worker),
    db: Session = Depends(get_db),
) -> PlatformAccount:
    """Revises the figures on a connection."""
    account = _owned_account(db, user, account_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, field, value.strip() if isinstance(value, str) else value)

    try:
        db.commit()
        db.refresh(account)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to update platform %s", account_id)
        raise

    return account


# A 204 must not carry a body, so the response model and class are both pinned
# explicitly. Leaving them to inference is not safe here: under
# `from __future__ import annotations` the `-> None` return annotation resolves
# to NoneType, which FastAPI reads as a real response model and then rejects
# against the 204 status.
@router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
)
def disconnect_platform(
    account_id: uuid.UUID,
    user: User = Depends(current_worker),
    db: Session = Depends(get_db),
) -> None:
    """Disconnects a platform. The score recomputes without it on the next read."""
    account = _owned_account(db, user, account_id)
    try:
        db.delete(account)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to disconnect platform %s", account_id)
        raise


@router.get("/income-profile", response_model=IncomeProfile)
def read_income_profile(
    user: User = Depends(current_worker), db: Session = Depends(get_db)
) -> dict:
    """The eight scoring features, derived from connections plus the ledger."""
    return build_profile(db, user)


def build_profile(db: Session, user: User) -> dict:
    """Shared derivation, so the credit and loan routes score the same person.

    Lives here rather than in the router body because three routes need it and
    duplicating it is how the score on the dashboard drifts from the score a
    loan was granted against.
    """
    stats = db_service.get_user_dashboard_stats(db, user_id=user.id)
    return income_profile.build(
        date_of_birth=user.date_of_birth,
        platform_accounts=_rows_for(db, user),
        transactions=db_service.get_transactions(db, user_id=user.id, limit=_LEDGER_FETCH_LIMIT),
        stash_balance=stats["total_stash_balance"],
    )
