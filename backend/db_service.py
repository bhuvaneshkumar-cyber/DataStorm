import uuid
from typing import List, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from models import User, TransactionRecord, SavingsSweepRecord
from savings import SavingsEngine, Transaction, moving_average


def get_user_income_history(db: Session, user_id: Union[str, uuid.UUID], limit: int = 30) -> List[float]:
    """Retrieves recent platform payout amounts for a user to calculate baseline income."""
    records = (
        db.query(TransactionRecord.amount)
        .filter(TransactionRecord.user_id == user_id, TransactionRecord.transaction_type == "platform_payout")
        .order_by(desc(TransactionRecord.timestamp))
        .limit(limit)
        .all()
    )
    return [float(r[0]) for r in reversed(records)]


def add_transaction(
    db: Session,
    user_id: Union[str, uuid.UUID],
    amount: float,
    transaction_type: str,
    merchant: Optional[str] = None,
    threshold: float = 100.0,
    mandate_limit: float = 1000.0,
) -> dict:
    """
    Inserts a transaction into the ledger, evaluates SavingsEngine,
    and returns the decision.
    """
    record = TransactionRecord(
        user_id=user_id,
        amount=amount,
        transaction_type=transaction_type,
        merchant=merchant,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    history = get_user_income_history(db, user_id)
    engine = SavingsEngine(history, threshold=threshold, mandate_limit=mandate_limit)
    decision = engine.process(Transaction(amount=amount, kind=transaction_type))

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


def execute_sweep(
    db: Session,
    user_id: Union[str, uuid.UUID],
    sweep_amount: float,
    transaction_id: Optional[Union[str, uuid.UUID]] = None,
    reason: str = "UPI AutoPay sweep authorized",
) -> SavingsSweepRecord:
    """Records an authorized savings sweep in the savings_sweeps table."""
    sweep = SavingsSweepRecord(
        user_id=user_id,
        transaction_id=transaction_id,
        sweep_amount=sweep_amount,
        reason=reason,
    )
    db.add(sweep)
    db.commit()
    db.refresh(sweep)
    return sweep


def get_transactions(db: Session, user_id: Optional[Union[str, uuid.UUID]] = None, limit: int = 50) -> List[dict]:
    """Retrieves list of transactions."""
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


def get_sweeps(db: Session, user_id: Optional[Union[str, uuid.UUID]] = None, limit: int = 50) -> List[dict]:
    """Retrieves list of savings sweeps."""
    query = db.query(SavingsSweepRecord)
    if user_id:
        query = query.filter(SavingsSweepRecord.user_id == user_id)
    records = query.order_by(desc(SavingsSweepRecord.created_at)).limit(limit).all()
    return [
        {
            "id": str(s.id),
            "user_id": str(s.user_id) if s.user_id else None,
            "transaction_id": str(s.transaction_id) if s.transaction_id else None,
            "sweep_amount": float(s.sweep_amount),
            "reason": s.reason,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in records
    ]


def process_transaction_event(
    db: Session,
    user_id: Union[str, uuid.UUID],
    amount: float,
    transaction_type: str,
    merchant: Optional[str] = None,
    threshold: float = 10.0,
    mandate_limit: float = 1000.0,
) -> dict:
    """
    End-to-end transactional pipeline:
    1. Records transaction.
    2. Runs SavingsEngine calculation on history + new event.
    3. If eligible and not already swept (idempotent), records savings_sweep with user_id and transaction_id.
    """
    try:
        # Step 1: Ingest transaction
        tx = TransactionRecord(
            user_id=user_id,
            amount=amount,
            transaction_type=transaction_type,
            merchant=merchant,
        )
        db.add(tx)
        db.flush()  # Generates tx.id without committing outer transaction

        # Step 2: Fetch history and process through SavingsEngine
        history = get_user_income_history(db, user_id)
        engine = SavingsEngine(history, threshold=threshold, mandate_limit=mandate_limit)
        decision = engine.process(Transaction(amount=amount, kind=transaction_type))

        sweep_record = None
        if decision.eligible:
            # Step 3: Idempotency check - ensure no existing sweep for this transaction_id
            existing_sweep = db.query(SavingsSweepRecord).filter(
                SavingsSweepRecord.transaction_id == tx.id
            ).first()

            if not existing_sweep:
                sweep_record = SavingsSweepRecord(
                    user_id=user_id,
                    transaction_id=tx.id,
                    sweep_amount=decision.amount,
                    reason=decision.reason,
                )
                db.add(sweep_record)

        db.commit()
        db.refresh(tx)
        if sweep_record:
            db.refresh(sweep_record)

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
            "sweep": {
                "id": str(sweep_record.id),
                "sweep_amount": float(sweep_record.sweep_amount),
                "reason": sweep_record.reason,
                "transaction_id": str(sweep_record.transaction_id),
                "user_id": str(sweep_record.user_id),
            } if sweep_record else None,
        }
    except Exception as e:
        db.rollback()
        raise e


def get_user_dashboard_stats(db: Session, user_id: Union[str, uuid.UUID]) -> dict:
    """Aggregates total saved in stash, sweep history, and moving average baseline."""
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

    history = get_user_income_history(db, user_id, limit=30)
    baseline_income = moving_average(history, 30)

    return {
        "user_id": str(user_id),
        "total_stash_balance": round(float(total_saved), 2),
        "income_30d_baseline": round(baseline_income, 2),
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


