"""Persistence layer: transaction ingestion, sweep ledger, and dashboard reads.

Every write goes through `_ingest_and_evaluate`, so the insert-then-score
sequence exists once and both public entry points stay consistent with it.
"""

import logging
import uuid
from typing import List, Optional, Tuple, Union

from sqlalchemy import desc, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models import SavingsSweepRecord, TransactionRecord
from savings import SavingsEngine, SweepDecision, Transaction, moving_average

logger = logging.getLogger(__name__)

UserId = Union[str, uuid.UUID]

DEFAULT_THRESHOLD = 100.0
DEFAULT_MANDATE_LIMIT = 1000.0
INCOME_WINDOW = 30


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


def _ingest_and_evaluate(
    db: Session,
    user_id: UserId,
    amount: float,
    transaction_type: str,
    merchant: Optional[str],
    threshold: float,
    mandate_limit: float,
) -> Tuple[TransactionRecord, SweepDecision]:
    """Stages the transaction and scores it. Does NOT commit; callers decide.

    Flushing rather than committing assigns the primary key while leaving the
    caller free to roll the whole unit of work back if a later step fails.
    """
    record = TransactionRecord(
        user_id=user_id,
        amount=amount,
        transaction_type=transaction_type,
        merchant=merchant,
    )
    db.add(record)
    db.flush()

    history = get_user_income_history(db, user_id)
    engine = SavingsEngine(history, threshold=threshold, mandate_limit=mandate_limit)
    decision = engine.process(Transaction(amount=amount, kind=transaction_type))
    return record, decision


def add_transaction(
    db: Session,
    user_id: UserId,
    amount: float,
    transaction_type: str,
    merchant: Optional[str] = None,
    threshold: float = DEFAULT_THRESHOLD,
    mandate_limit: float = DEFAULT_MANDATE_LIMIT,
) -> dict:
    """Records a transaction and returns the sweep decision without acting on it.

    The sweep itself is authorized separately via POST /api/sweeps, so this
    stays a pure ingest-and-advise step.
    """
    try:
        record, decision = _ingest_and_evaluate(
            db, user_id, amount, transaction_type, merchant, threshold, mandate_limit
        )
        db.commit()
        db.refresh(record)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to record transaction for user %s", user_id)
        raise

    return {
        "transaction_id": str(record.id),
        "amount": float(record.amount),
        "transaction_type": record.transaction_type,
        "sweep_decision": {
            "amount": decision.amount,
            "eligible": decision.eligible,
            "reason": decision.reason,
        },
    }


def process_transaction_event(
    db: Session,
    user_id: UserId,
    amount: float,
    transaction_type: str,
    merchant: Optional[str] = None,
    threshold: float = 10.0,
    mandate_limit: float = DEFAULT_MANDATE_LIMIT,
) -> dict:
    """Ingests, scores, and if eligible writes the sweep in one transaction.

    Idempotent on transaction_id: a replayed event never produces a second sweep.
    """
    try:
        tx, decision = _ingest_and_evaluate(
            db, user_id, amount, transaction_type, merchant, threshold, mandate_limit
        )

        sweep_record = None
        if decision.eligible:
            already_swept = (
                db.query(SavingsSweepRecord)
                .filter(SavingsSweepRecord.transaction_id == tx.id)
                .first()
            )
            if not already_swept:
                sweep_record = SavingsSweepRecord(
                    user_id=user_id,
                    transaction_id=tx.id,
                    sweep_amount=decision.amount,
                    reason=decision.reason,
                )
                db.add(sweep_record)

        db.commit()
        db.refresh(tx)
        if sweep_record is not None:
            db.refresh(sweep_record)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to process transaction event for user %s", user_id)
        raise

    return {
        "status": "success",
        "transaction_id": str(tx.id),
        "user_id": str(tx.user_id),
        "amount": float(tx.amount),
        "transaction_type": tx.transaction_type,
        "decision": {
            "amount": decision.amount,
            "eligible": decision.eligible,
            "reason": decision.reason,
        },
        "sweep": None
        if sweep_record is None
        else {
            "id": str(sweep_record.id),
            "sweep_amount": float(sweep_record.sweep_amount),
            "reason": sweep_record.reason,
            "transaction_id": str(sweep_record.transaction_id),
            "user_id": str(sweep_record.user_id),
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
            "status": r.status,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        }
        for r in records
    ]


def _sweep_to_dict(sweep: SavingsSweepRecord, include_user: bool = False) -> dict:
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
    return [_sweep_to_dict(s, include_user=True) for s in records]


def get_user_dashboard_stats(db: Session, user_id: UserId) -> dict:
    """Stash balance, rolling income baseline, and the last 10 sweeps."""
    total_saved = (
        db.query(func.coalesce(func.sum(SavingsSweepRecord.sweep_amount), 0.0))
        .filter(SavingsSweepRecord.user_id == user_id)
        .scalar()
    )

    sweeps = (
        db.query(SavingsSweepRecord)
        .filter(SavingsSweepRecord.user_id == user_id)
        .order_by(desc(SavingsSweepRecord.created_at))
        .limit(10)
        .all()
    )

    history = get_user_income_history(db, user_id, limit=INCOME_WINDOW)

    return {
        "user_id": str(user_id),
        "total_stash_balance": round(float(total_saved or 0.0), 2),
        "income_30d_baseline": round(moving_average(history, INCOME_WINDOW), 2),
        "recent_sweeps": [_sweep_to_dict(s) for s in sweeps],
    }
