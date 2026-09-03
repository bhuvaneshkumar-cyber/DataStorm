"""SQLAlchemy ORM models.

Five tables, one per thing the product actually persists: who a person is, what
money moved, what was swept into the stash, which earning platforms they have
connected, and what credit they have applied for.

Every table's `id` is a UUID generated client-side by SQLAlchemy rather than by
a database default, so a row has its identity before it is flushed and the
service is not tied to a Postgres-specific `gen_random_uuid()`.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database import Base

# Two audiences share one users table, separated by role. A lender must never be
# able to open a worker's routes and vice versa; the role claim in the JWT is
# what enforces that, and this is the vocabulary it uses.
ROLE_WORKER = "worker"
ROLE_LENDER = "lender"
VALID_ROLES = (ROLE_WORKER, ROLE_LENDER)

# Loan lifecycle. `pending` is the only state a worker can create.
LOAN_PENDING = "pending"
LOAN_APPROVED = "approved"
LOAN_REJECTED = "rejected"
LOAN_DECIDED_STATES = (LOAN_APPROVED, LOAN_REJECTED)


def utcnow() -> datetime:
    """Naive UTC timestamp.

    datetime.utcnow() is deprecated from Python 3.12; this returns the identical
    value while staying supported. tzinfo is stripped because the columns are
    TIMESTAMP WITHOUT TIME ZONE and would otherwise silently drop the offset.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    """A worker or a lender. `role` decides which half of the product they see."""

    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=True)
    email = Column(String, unique=True, index=True, nullable=True)
    phone = Column(String, nullable=True)
    # Nullable so rows seeded before authentication existed still load; a null
    # hash cannot satisfy verify_password, so those accounts simply cannot log in.
    password_hash = Column(String, nullable=True)
    role = Column(String, nullable=False, default=ROLE_WORKER)
    # Preferred UI language (BCP-47 primary subtag). Stored server-side so the
    # choice follows the account to a new device instead of living in one browser.
    language = Column(String, nullable=False, default="en")
    # Free text, not an enum: employment type drives insurance advice, and the
    # gig economy invents new categories faster than a migration can keep up.
    employment_type = Column(String, nullable=True)
    # Date of birth rather than age: an age column is correct on the day it is
    # written and silently wrong every day after. Nullable, and a missing value
    # is reported as an assumption rather than quietly scored as average.
    date_of_birth = Column(Date, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    transactions = relationship(
        "TransactionRecord", back_populates="user", cascade="all, delete-orphan"
    )
    sweeps = relationship(
        "SavingsSweepRecord", back_populates="user", cascade="all, delete-orphan"
    )
    platform_accounts = relationship(
        "PlatformAccount", back_populates="user", cascade="all, delete-orphan"
    )
    loan_applications = relationship(
        "LoanApplication",
        back_populates="applicant",
        cascade="all, delete-orphan",
        foreign_keys="LoanApplication.user_id",
    )


class TransactionRecord(Base):
    """One money movement: a spend (`debit`) or an earning (`platform_payout`)."""

    __tablename__ = "transactions"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    amount = Column(Numeric, nullable=False)
    transaction_type = Column(String, nullable=False)  # "debit" or "platform_payout"
    merchant = Column(String, nullable=True)
    # Spend category for debits, earning platform for payouts. Optional, and only
    # used to break the expense tracker down, never to change a sweep decision.
    category = Column(String, nullable=True)
    status = Column(String, default="completed")
    timestamp = Column(DateTime, default=utcnow)

    user = relationship("User", back_populates="transactions")


class SavingsSweepRecord(Base):
    """One authorized transfer into the Resilience Stash."""

    __tablename__ = "savings_sweeps"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    transaction_id = Column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True, index=True
    )
    sweep_amount = Column(Numeric, nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    user = relationship("User", back_populates="sweeps")


class PlatformAccount(Base):
    """A connected gig platform, held as income proof.

    The figures are what the connection reports, not what a worker types into a
    credit form: they are the evidence the alternative score is built on, so
    `verified` records whether a real payout has since corroborated them or
    whether they were entered by hand and are still unconfirmed.
    """

    __tablename__ = "platform_accounts"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    # Free text so a new platform needs no migration; the credit request maps it
    # onto one of the scoring service's four categories at call time.
    platform = Column(String, nullable=False)
    account_handle = Column(String, nullable=True)
    customer_rating = Column(Numeric, nullable=True)
    weekly_payout = Column(Numeric, nullable=True)
    gigs_per_week = Column(Numeric, nullable=True)
    hours_per_week = Column(Numeric, nullable=True)
    verified = Column(Boolean, nullable=False, default=False)
    connected_at = Column(DateTime, default=utcnow)

    user = relationship("User", back_populates="platform_accounts")


class LoanApplication(Base):
    """An emergency loan request and the underwriting snapshot behind it.

    The score, grade and decision are copied onto the row rather than recomputed
    when a lender opens it. An application must be judged on the evidence that
    existed when it was made; a score that drifts afterwards would silently
    rewrite the basis of a decision already taken.
    """

    __tablename__ = "loan_applications"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Numeric, nullable=False)
    tenor_months = Column(Numeric, nullable=False)
    purpose = Column(String, nullable=True)

    credit_score = Column(Numeric, nullable=False)
    risk_grade = Column(String, nullable=True)
    risk_tier = Column(String, nullable=True)
    indicative_interest_rate_pct = Column(Numeric, nullable=True)
    max_credit_limit_inr = Column(Numeric, nullable=True)
    engine_decision = Column(String, nullable=True)  # APPROVE / REFER / DECLINE

    status = Column(String, nullable=False, default=LOAN_PENDING)
    lender_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    lender_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    decided_at = Column(DateTime, nullable=True)

    applicant = relationship("User", back_populates="loan_applications", foreign_keys=[user_id])
    lender = relationship("User", foreign_keys=[lender_id])
