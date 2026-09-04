"""Persistence layer: transaction ingestion, sweep ledger, and dashboard reads.

Every write goes through `_ingest_and_evaluate`, so the insert-then-score
sequence exists once and both public entry points stay consistent with it.
"""

import logging
import uuid
from typing import List, Optional, Tuple, Union
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from models import TransactionRecord, SavingsSweepRecord
from savings import (
    SweepDecision,
    income_surplus,
    moving_average,
    round_up,
    sweep_decision,
)
from webhooks import WebhookEvent

# A transaction's contribution is counted toward the next sweep until a sweep
# claims it, at which point its status flips. This is the SQL equivalent of the
# `pendingContributions` counter the retired Node/Mongo stash document held.
STATUS_PENDING = "completed"
STATUS_SWEPT = "swept"

# How many recent transactions to replay when deriving pending contributions.
# Comfortably larger than any realistic unswept backlog or 30-payout window.
REPLAY_LIMIT = 500


def get_user_income_history(db: Session, user_id: UserId, limit: int = INCOME_WINDOW) -> List[float]:
    """Recent platform payouts, oldest first, for the rolling income baseline."""
    records = (
        db.query(TransactionRecord.amount)
        .filter(
            TransactionRecord.user_id == user_id,
            TransactionRecord.transaction_type == "platform_payout",
        )
        .order_by(desc(TransactionRecord.timestamp))
        .limit(limit)
        .all()
    )
    return [float(row[0]) for row in reversed(records)]


def get_pending_contributions(
    db: Session,
    user_id: Union[str, uuid.UUID],
    surplus_percentage: float = 0.10,
) -> Tuple[float, float, List[TransactionRecord]]:
    """Replays the unswept tail of a user's ledger into pending contributions.

    Returns ``(pending_roundups, pending_surplus, pending_records)``.

    Mongo kept a running ``pendingContributions`` counter on the stash document;
    Postgres derives the same number from the ledger instead, so the value can
    always be re-audited from the rows themselves and can never drift out of sync
    with them. Debits contribute their round-up; payouts contribute a share of
    however much they beat the 30-payout moving average *at the time they landed*,
    which is why the whole tail is replayed in chronological order.
    """
    recent = (
        db.query(TransactionRecord)
        .filter(TransactionRecord.user_id == user_id)
        .order_by(desc(TransactionRecord.timestamp), desc(TransactionRecord.id))
        .limit(REPLAY_LIMIT)
        .all()
    )
    ordered = list(reversed(recent))

    income_history: List[float] = []
    pending_roundups = 0.0
    pending_surplus = 0.0
    pending_records: List[TransactionRecord] = []

    for record in ordered:
        amount = float(record.amount)
        is_pending = record.status != STATUS_SWEPT
        if record.transaction_type == "debit":
            if is_pending:
                pending_roundups += round_up(amount)
        elif record.transaction_type == "platform_payout":
            if is_pending:
                pending_surplus += income_surplus(amount, income_history, surplus_percentage)
            income_history.append(amount)
        if is_pending:
            pending_records.append(record)

    return round(pending_roundups, 2), round(pending_surplus, 2), pending_records


def _stash_balance(db: Session, user_id: Union[str, uuid.UUID]) -> float:
    """Total value already swept into the user's resilience stash."""
    total = (
        db.query(func.coalesce(func.sum(SavingsSweepRecord.sweep_amount), 0.0))
        .filter(SavingsSweepRecord.user_id == user_id)
        .scalar()
    )
    return round(float(total), 2)


def _commit_sweep(
    db: Session,
    user_id: Union[str, uuid.UUID],
    decision: SweepDecision,
    pending_records: List[TransactionRecord],
    triggering_transaction_id: Optional[Union[str, uuid.UUID]] = None,
) -> SavingsSweepRecord:
    """Writes the sweep row and marks the contributions it consumed as swept."""
    sweep = SavingsSweepRecord(
        user_id=user_id,
        transaction_id=triggering_transaction_id,
        sweep_amount=decision.amount,
        reason=decision.reason,
    )
    db.add(sweep)
    for record in pending_records:
        record.status = STATUS_SWEPT
    return sweep


def add_transaction(
    db: Session,
    user_id: UserId,
    amount: float,
    transaction_type: str,
    merchant: Optional[str] = None,
    threshold: float = 100.0,
    mandate_limit: float = 1000.0,
) -> dict:
    """Inserts a transaction into the ledger and reports the resulting decision.

    Read-only with respect to the stash: it reports whether the accumulated
    pending total is now sweepable but does not execute the sweep. Callers that
    want ingestion and sweeping in one atomic step use process_webhook_event.
    """
    record = TransactionRecord(
        user_id=user_id,
        amount=amount,
        transaction_type=transaction_type,
        merchant=merchant,
        status=STATUS_PENDING,
    )
    db.add(record)
    db.flush()

    roundups, surplus, _ = get_pending_contributions(db, user_id)
    decision = sweep_decision(roundups, surplus, threshold, mandate_limit)

    return {
        "transaction_id": str(record.id),
        "amount": float(record.amount),
        "transaction_type": record.transaction_type,
        "pending_roundups": roundups,
        "pending_surplus": surplus,
        "sweep_decision": {
            "amount": decision.amount,
            "eligible": decision.eligible,
            "reason": decision.reason,
        },
    }


def execute_sweep(
    db: Session,
    user_id: UserId,
    sweep_amount: float,
    transaction_id: Optional[UserId] = None,
    reason: str = "UPI AutoPay sweep authorized",
) -> SavingsSweepRecord:
    """Records an authorized savings sweep in the savings_sweeps table."""
    sweep = SavingsSweepRecord(
        user_id=user_id,
        transaction_id=transaction_id,
        sweep_amount=sweep_amount,
        reason=reason,
    )
    try:
        db.add(sweep)
        db.commit()
        db.refresh(sweep)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to record sweep for user %s", user_id)
        raise
    return sweep


def get_transactions(db: Session, user_id: Optional[UserId] = None, limit: int = 50) -> List[dict]:
    """Most recent transactions, newest first."""
    query = db.query(TransactionRecord)
    if user_id:
        query = query.filter(TransactionRecord.user_id == user_id)
    records = query.order_by(desc(TransactionRecord.timestamp)).limit(limit).all()
    return [
        {
            "id": str(r.id),
            "user_id": str(r.user_id) if r.user_id else None,
            "amount": float(r.amount),
            "transaction_type": r.transaction_type,
            "merchant": r.merchant,
            "category": r.category,
            "status": r.status,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        }
        for r in records
    ]


def sweep_to_dict(sweep: SavingsSweepRecord, include_user: bool = False) -> dict:
    """Single serialization shape for a sweep row."""
    payload = {
        "id": str(sweep.id),
        "sweep_amount": float(sweep.sweep_amount),
        "reason": sweep.reason,
        "transaction_id": str(sweep.transaction_id) if sweep.transaction_id else None,
        "created_at": sweep.created_at.isoformat() if sweep.created_at else None,
    }
    if include_user:
        payload["user_id"] = str(sweep.user_id) if sweep.user_id else None
    return payload


def get_sweeps(db: Session, user_id: Optional[UserId] = None, limit: int = 50) -> List[dict]:
    """Most recent savings sweeps, newest first."""
    query = db.query(SavingsSweepRecord)
    if user_id:
        query = query.filter(SavingsSweepRecord.user_id == user_id)
    records = query.order_by(desc(SavingsSweepRecord.created_at)).limit(limit).all()
    return [sweep_to_dict(s, include_user=True) for s in records]


def process_webhook_event(
    db: Session,
    event: WebhookEvent,
    threshold: float = 100.0,
    mandate_limit: float = 1000.0,
    surplus_percentage: float = 0.10,
) -> dict:
    """End-to-end webhook pipeline: ingest, accumulate, sweep when authorised.

    Replaces the Node ``processContribution`` + ``handleTransactionPayload`` pair.
    The whole thing is one transaction, so a mid-flight failure leaves neither a
    stray ledger row nor a half-applied sweep.

    Idempotency comes from the transaction id: webhooks.parse_event derives a
    deterministic UUID from the payload, so a replayed delivery collides with the
    row it already wrote and returns the no-op result instead of double-counting.
    """
    existing = db.get(TransactionRecord, event.transaction_id)
    if existing is not None:
        return {
            "status": "already_processed",
            "transaction_id": str(event.transaction_id),
            "swept": False,
            "swept_amount": 0.0,
            "new_balance": _stash_balance(db, event.user_id),
            "reason": "Transaction already processed - skipped (idempotent).",
        }

    try:
        tx = TransactionRecord(
            id=event.transaction_id,
            user_id=event.user_id,
            amount=event.amount,
            transaction_type=event.transaction_type,
            merchant=event.source,
            status=STATUS_PENDING,
            timestamp=event.timestamp,
        )
        db.add(tx)
        db.flush()

        roundups, surplus, pending_records = get_pending_contributions(
            db, event.user_id, surplus_percentage
        )
        decision = sweep_decision(roundups, surplus, threshold, mandate_limit)

        sweep = None
        if decision.eligible:
            sweep = _commit_sweep(db, event.user_id, decision, pending_records, tx.id)

        db.commit()

        balance = _stash_balance(db, event.user_id)
        return {
            "status": "success",
            "transaction_id": str(event.transaction_id),
            "user_id": str(event.user_id),
            "amount": event.amount,
            "transaction_type": event.transaction_type,
            "swept": sweep is not None,
            "swept_amount": decision.amount if sweep else 0.0,
            "pending_after": 0.0 if sweep else decision.amount,
            "new_balance": balance,
            "was_capped": decision.amount > mandate_limit,
            "reason": decision.reason,
        }
    except Exception:
        db.rollback()
        raise


def authorize_manual_sweep(
    db: Session,
    user_id: Union[str, uuid.UUID],
    threshold: float = 100.0,
    mandate_limit: float = 1000.0,
) -> dict:
    """Sweeps whatever has accumulated so far, if the mandate allows it.

    Ports the Node ``/webhooks/sweep`` route: unlike the transaction webhook it
    ingests nothing, it only decides on the pending balance that is already there.
    """
    roundups, surplus, pending_records = get_pending_contributions(db, user_id)
    decision = sweep_decision(roundups, surplus, threshold, mandate_limit)

    if not decision.eligible:
        return {
            "status": "not_eligible",
            "swept": False,
            "swept_amount": 0.0,
            "pending_after": decision.amount,
            "new_balance": _stash_balance(db, user_id),
            "was_capped": decision.amount > mandate_limit,
            "reason": decision.reason,
        }

    try:
        triggering_id = pending_records[-1].id if pending_records else None
        sweep = _commit_sweep(db, user_id, decision, pending_records, triggering_id)
        db.commit()
        db.refresh(sweep)
    except Exception:
        db.rollback()
        raise

    return {
        "status": "success",
        "sweep_id": str(sweep.id),
        "swept": True,
        "swept_amount": decision.amount,
        "pending_after": 0.0,
        "new_balance": _stash_balance(db, user_id),
        "was_capped": False,
        "reason": decision.reason,
    }


def get_user_dashboard_stats(db: Session, user_id: Union[str, uuid.UUID]) -> dict:
    """Aggregates total saved in stash, sweep history, and moving average baseline."""
    total_saved = _stash_balance(db, user_id)

    sweeps = (
        db.query(SavingsSweepRecord)
        .filter(SavingsSweepRecord.user_id == user_id)
        .order_by(desc(SavingsSweepRecord.created_at))
        .limit(10)
        .all()
    )

    history = get_user_income_history(db, user_id, limit=30)
    baseline_income = moving_average(history, 30)
    roundups, surplus, _ = get_pending_contributions(db, user_id)

    return {
        "user_id": str(user_id),
        "total_stash_balance": total_saved,
        "income_30d_baseline": round(baseline_income, 2),
        "pending_contributions": round(roundups + surplus, 2),
        "recent_sweeps": [
            {
                "id": str(s.id),
                "sweep_amount": float(s.sweep_amount),
                "reason": s.reason,
                "transaction_id": str(s.transaction_id) if s.transaction_id else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in sweeps
        ],
    }
