"""Pydantic request and response contracts for the financial engine API.

Kept in one file so the HTTP surface can be read end to end without opening
five routers, and so the dashboard's TypeScript types have a single thing to
mirror.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field

from models import ROLE_WORKER

Role = Literal["worker", "lender"]
TransactionType = Literal["debit", "platform_payout"]
LoanStatus = Literal["pending", "approved", "rejected"]

# Mirrors the languages the dashboard actually ships strings for. Rejecting an
# unknown code here beats storing "fr" and silently rendering English forever.
SUPPORTED_LANGUAGES = ("en", "hi", "ta")
Language = Literal["en", "hi", "ta"]

MIN_PASSWORD_LENGTH = 8


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #


class RegisterRequest(BaseModel):
    """Registration is the same route for both audiences; `role` picks which."""

    name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=128)
    phone: Optional[str] = Field(None, max_length=20)
    role: Role = ROLE_WORKER
    language: Language = "en"
    employment_type: Optional[str] = Field(None, max_length=60)
    # Optional at sign-up so registration stays two fields and a password, but
    # the credit score needs an age, and without this it falls back to a default
    # the profile then reports as an assumption.
    date_of_birth: Optional[date] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)
    # The lender portal is a separate front door onto the same credential store.
    # Stating the expected role means a worker signing in at the lender door is
    # refused outright rather than landing in a portal with nothing to show.
    expected_role: Optional[Role] = None


class UserProfile(BaseModel):
    id: uuid.UUID
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Role
    language: Language
    employment_type: Optional[str] = None
    date_of_birth: Optional[date] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in_hours: int
    user: UserProfile


class ProfileUpdate(BaseModel):
    """Every field optional: this is a patch, and an omitted field means leave it."""

    name: Optional[str] = Field(None, min_length=1, max_length=120)
    phone: Optional[str] = Field(None, max_length=20)
    language: Optional[Language] = None
    employment_type: Optional[str] = Field(None, max_length=60)
    date_of_birth: Optional[date] = None


# --------------------------------------------------------------------------- #
# Transactions and sweeps
# --------------------------------------------------------------------------- #


class TransactionCreate(BaseModel):
    """A logged expense or earning. The owner comes from the token, not the body."""

    amount: float = Field(..., gt=0, description="Transaction amount in rupees.")
    transaction_type: TransactionType
    merchant: Optional[str] = Field(None, max_length=120)
    category: Optional[str] = Field(None, max_length=60)
    threshold: float = Field(100.0, gt=0, description="Minimum sweep size.")
    mandate_limit: float = Field(1000.0, gt=0, description="UPI AutoPay cap per sweep.")


class SweepDecisionOut(BaseModel):
    amount: float
    eligible: bool
    reason: str


class TransactionCreated(BaseModel):
    transaction_id: str
    amount: float
    transaction_type: str
    sweep_decision: SweepDecisionOut


class TransactionOut(BaseModel):
    id: str
    user_id: Optional[str] = None
    amount: float
    transaction_type: str
    merchant: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    timestamp: Optional[str] = None


class SweepCreate(BaseModel):
    sweep_amount: float = Field(..., gt=0)
    transaction_id: Optional[uuid.UUID] = None
    reason: str = "UPI AutoPay sweep authorized"


class SweepOut(BaseModel):
    id: str
    sweep_amount: float
    reason: Optional[str] = None
    transaction_id: Optional[str] = None
    created_at: Optional[str] = None
    user_id: Optional[str] = None


class CashflowPoint(BaseModel):
    """One bucket of the cash-flow chart: what came in, what went out."""

    period: str = Field(..., description="ISO date for a day, or YYYY-MM for a month.")
    income: float
    expense: float
    net: float


class CategoryTotal(BaseModel):
    category: str
    total: float
    share_pct: float


class ExpenseSummary(BaseModel):
    """Everything the expense tracker charts, computed server-side.

    Aggregating here rather than shipping every row to the browser keeps the
    numbers identical to the ones the tax and credit paths use.
    """

    window_days: int
    total_income: float
    total_expense: float
    net: float
    daily: list[CashflowPoint]
    monthly: list[CashflowPoint]
    expense_categories: list[CategoryTotal]
    income_sources: list[CategoryTotal]
    transaction_count: int


class DashboardStats(BaseModel):
    user_id: str
    total_stash_balance: float
    income_30d_baseline: float
    pending_contributions: float
    recent_sweeps: list[SweepOut]


# --------------------------------------------------------------------------- #
# Platform accounts
# --------------------------------------------------------------------------- #


class PlatformAccountCreate(BaseModel):
    platform: str = Field(..., min_length=1, max_length=60)
    account_handle: Optional[str] = Field(None, max_length=120)
    customer_rating: Optional[float] = Field(None, ge=1.0, le=5.0)
    weekly_payout: Optional[float] = Field(None, ge=0.0)
    gigs_per_week: Optional[float] = Field(None, ge=0.0, le=500.0)
    hours_per_week: Optional[float] = Field(None, ge=0.0, le=120.0)


class PlatformAccountUpdate(BaseModel):
    """Every field optional: this is a patch, and an omitted field means leave it."""

    platform: Optional[str] = Field(None, min_length=1, max_length=60)
    account_handle: Optional[str] = Field(None, max_length=120)
    customer_rating: Optional[float] = Field(None, ge=1.0, le=5.0)
    weekly_payout: Optional[float] = Field(None, ge=0.0)
    gigs_per_week: Optional[float] = Field(None, ge=0.0, le=500.0)
    hours_per_week: Optional[float] = Field(None, ge=0.0, le=120.0)


class PlatformAccountOut(PlatformAccountCreate):
    id: uuid.UUID
    verified: bool
    connected_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class IncomeProfile(BaseModel):
    """Connected platforms collapsed into the eight features the scorer wants.

    This is the bridge between "which accounts has this worker linked" and "what
    do we score them on", and it exists so the dashboard never has to invent
    those features itself.
    """

    primary_gig_platform: Literal["Ride-Hailing", "Food Delivery", "Freelance", "Other"]
    platform_customer_rating: float
    average_weekly_payout: float
    completed_gigs_per_week: int
    active_platform_hours_per_week: int
    payout_volatility_index: float
    resilience_stash_balance: float
    age: int
    connected_platforms: int
    verified_platforms: int
    # Names the fields that fell back to a default, so the UI can ask for them
    # rather than presenting a guess as evidence.
    assumptions: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Loans
# --------------------------------------------------------------------------- #


class LoanApplicationCreate(BaseModel):
    """What the applicant asks for. The score is derived server-side, never sent.

    A body that could name its own credit score could name 800, so the only
    things accepted here are the terms being requested.
    """

    amount: float = Field(..., gt=0, le=1_000_000)
    tenor_months: int = Field(..., ge=1, le=36)
    purpose: Optional[str] = Field(None, max_length=200)


class LoanApplicationOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    amount: float
    tenor_months: int
    purpose: Optional[str] = None
    credit_score: float
    risk_grade: Optional[str] = None
    risk_tier: Optional[str] = None
    indicative_interest_rate_pct: Optional[float] = None
    max_credit_limit_inr: Optional[float] = None
    engine_decision: Optional[str] = None
    status: LoanStatus
    lender_note: Optional[str] = None
    created_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None
    # Populated only on the lender's view; a worker sees their own name nowhere
    # because they already know it, and it keeps the two payloads distinguishable.
    applicant_name: Optional[str] = None
    applicant_email: Optional[str] = None


class LoanDecision(BaseModel):
    status: Literal["approved", "rejected"]
    lender_note: Optional[str] = Field(None, max_length=500)


class LoanEligibility(BaseModel):
    """Whether this worker may apply at all, and on what terms."""

    eligible: bool
    credit_score: float
    threshold: float
    reason: str
    max_amount_inr: float
    max_tenor_months: int
    indicative_interest_rate_pct: Optional[float] = None
    risk_grade: Optional[str] = None


# --------------------------------------------------------------------------- #
# Tax
# --------------------------------------------------------------------------- #


class TaxSlab(BaseModel):
    band: str
    rate_pct: float
    taxable_in_band: float
    tax: float


class TaxSummary(BaseModel):
    """An estimate, explicitly labelled as one. Not filed, not advice."""

    financial_year: str
    regime: str
    observed_days: int
    gross_income_observed: float
    annualised_gross_income: float
    presumptive_deduction: float
    deductions_claimed: float
    taxable_income: float
    slabs: list[TaxSlab]
    tax_before_rebate: float
    rebate: float
    surcharge: float
    cess: float
    total_tax: float
    effective_rate_pct: float
    monthly_set_aside: float
    gst_registration_required: bool
    notes: list[str]


# --------------------------------------------------------------------------- #
# Policy bot
# --------------------------------------------------------------------------- #


class BotQuery(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)
    language: Language = "en"


class BotSource(BaseModel):
    topic: str
    score: float


class BotAnswer(BaseModel):
    answer: str
    confident: bool = Field(
        ..., description="False when nothing matched well; the answer is then a fallback."
    )
    sources: list[BotSource] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
