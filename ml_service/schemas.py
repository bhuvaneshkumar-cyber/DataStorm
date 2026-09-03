"""Request/response contracts for the gig-worker credit scoring service."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

GigPlatform = Literal["Ride-Hailing", "Food Delivery", "Freelance", "Other"]
ScoreCategory = Literal["Poor", "Standard", "Good"]
RiskTier = Literal["LOW", "MODERATE", "HIGH", "VERY_HIGH"]
Decision = Literal["APPROVE", "REFER", "DECLINE"]


class CreditScoreRequest(BaseModel):
    """The 8 gig-economy signals we score on."""

    age: int = Field(..., ge=18, le=75, description="Applicant age in years.")
    primary_gig_platform: GigPlatform = Field(..., description="Main earning platform.")
    platform_customer_rating: float = Field(..., ge=1.0, le=5.0, description="Platform star rating.")
    completed_gigs_per_week: int = Field(..., ge=0, le=200)
    average_weekly_payout: float = Field(..., ge=0.0, description="Mean weekly earnings.")
    payout_volatility_index: float = Field(
        ..., ge=0.0, le=1.0, description="0 = perfectly stable income, 1 = wildly erratic."
    )
    active_platform_hours_per_week: int = Field(..., ge=0, le=120)
    resilience_stash_balance: float = Field(..., ge=0.0, description="Savings buffer balance.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "age": 29,
                "primary_gig_platform": "Ride-Hailing",
                "platform_customer_rating": 4.7,
                "completed_gigs_per_week": 62,
                "average_weekly_payout": 9200.0,
                "payout_volatility_index": 0.18,
                "active_platform_hours_per_week": 44,
                "resilience_stash_balance": 15000.0,
            }
        }
    }


class ShapFactor(BaseModel):
    """One feature's contribution to the ML component of the score."""

    feature: str
    impact: float = Field(..., description="Signed SHAP value; positive pushes the score up.")
    direction: Literal["positive", "negative"]


class RiskGrade(BaseModel):
    """Discrete underwriting grade, GS-1 (best) through GS-8 (loss)."""

    code: str
    label: str


class EarlyWarningSignal(BaseModel):
    """A specific fragility behind a score, not just its level."""

    code: str
    title: str
    detail: str


class RiskAssessment(BaseModel):
    """Underwriting view: grade, decision, price, exposure, and covenants."""

    risk_grade: RiskGrade
    risk_tier: RiskTier
    decision: Decision
    indicative_interest_rate_pct: float
    risk_premium_bps: int
    max_credit_limit_inr: float
    recommended_tenor_months: int
    conditions: list[str] = Field(default_factory=list)
    early_warning_signals: list[EarlyWarningSignal] = Field(default_factory=list)


class CreditScoreResponse(BaseModel):
    final_score: float = Field(..., description="Hybrid score, 0-800.")
    category: ScoreCategory
    confidence: float = Field(..., ge=0.0, le=1.0)
    rule_score: float
    ml_score: float | None = Field(None, description="None when the ML path degraded to rules only.")
    ml_available: bool
    explanation: list[ShapFactor] = Field(default_factory=list, description="Top 3 drivers.")
    risk_assessment: RiskAssessment | None = Field(
        None, description="Underwriting decision and pricing derived from the score."
    )
    latency_ms: float


class LedgerTransaction(BaseModel):
    """One standardized ledger row. Any source that can produce these can be scored."""

    date: str = Field(..., description="ISO date, YYYY-MM-DD.")
    type: Literal["credit", "debit"]
    amount: float = Field(..., ge=0.0)
    category: Optional[str] = Field(None, description="Platform for credits, spend category for debits.")
    source: Optional[str] = Field(None, description="bank | platform | manual")
    description: Optional[str] = None


class MetricDetail(BaseModel):
    """One metric's measured value, its 0-100 score, and what that means."""

    name: str
    value: float
    score: float
    status: str
    description: str


class MetricCoverage(BaseModel):
    """How much evidence the metrics rest on."""

    transactions: int
    credits: int
    debits: int
    months_observed: int
    period_start: str
    period_end: str


class MetricAnalysis(BaseModel):
    """Transaction-driven score with a per-metric explanation and coaching."""

    credit_score: float = Field(..., description="Composite rescaled to 0-800.")
    composite_score: float = Field(..., description="Weighted category mean, 0-100.")
    category_scores: dict[str, float]
    category_weights: dict[str, float]
    metrics: dict[str, MetricDetail]
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    coverage: MetricCoverage
    risk_grade: RiskGrade


class TransactionAnalysisRequest(BaseModel):
    """Score a ledger directly, without uploading a document."""

    transactions: list[LedgerTransaction] = Field(..., min_length=1)
    platform_rating: Optional[float] = Field(
        None, ge=1.0, le=5.0, description="Platform star rating, if known."
    )
    opening_balance: float = Field(
        0.0, ge=0.0, description="Balance before the first row; improves liquidity accuracy."
    )


class StatementAnalysis(BaseModel):
    """Provenance for a scored statement: what was read, and what was assumed."""

    source_format: str
    extraction_method: Optional[str] = Field(
        None, description="Parser that produced the text: pdfplumber, pymupdf, ocr, ..."
    )
    derived_features: dict[str, Any] = Field(
        default_factory=dict, description="Features evidenced by the statement itself."
    )
    supplied_features: dict[str, Any] = Field(
        default_factory=dict,
        description="Features taken from the caller or from a documented default.",
    )
    unresolved_features: list[str] = Field(
        default_factory=list, description="Features the statement could not evidence."
    )
    evidence: dict[str, Any] = Field(
        default_factory=dict, description="Columns detected, period covered, row counts."
    )
    warnings: list[str] = Field(default_factory=list)


class StatementScoreResponse(BaseModel):
    """A credit score plus the statement provenance behind its inputs."""

    statement_analysis: StatementAnalysis
    features_used: CreditScoreRequest
    score: CreditScoreResponse
    metric_analysis: Optional[MetricAnalysis] = Field(
        None,
        description="Per-metric breakdown from the statement ledger. Null when the "
        "statement had no usable date column and no ledger could be built.",
    )


# --------------------------------------------------------------------------- #
# Micro-insurance advice
# --------------------------------------------------------------------------- #


class InsuranceRequest(BaseModel):
    """One worker's risk picture. Everything but the score has a safe default."""

    credit_score: float = Field(..., ge=0.0, le=800.0)
    employment_type: Optional[str] = Field(
        None, description="Free text; matched against exposure profiles by keyword."
    )
    risk_tier: Optional[RiskTier] = Field(
        None, description="Overrides the tier derived from the score, if already known."
    )
    average_weekly_payout: float = Field(0.0, ge=0.0)
    resilience_stash_balance: float = Field(0.0, ge=0.0)
    active_platform_hours_per_week: int = Field(40, ge=0, le=120)
    payout_volatility_index: float = Field(0.5, ge=0.0, le=1.0)
    age: int = Field(30, ge=18, le=75)


class InsuranceOption(BaseModel):
    """One kind of cover, why it ranked where it did, and what it costs."""

    code: str
    title: str
    description: str
    priority: float = Field(..., ge=0.0, le=1.0)
    urgency: Literal["essential", "recommended", "optional"]
    reasons: list[str]
    indicative_monthly_premium_inr: Optional[list[float]] = Field(
        None, description="Low and high rupee estimate. Null when no income is known."
    )
    premium_pct_of_weekly_payout: list[float]


class InsuranceRecommendation(BaseModel):
    employment_type: Optional[str] = None
    matched_exposure_profile: str
    risk_tier: RiskTier
    credit_score: float
    savings_runway_weeks: float
    recommendations: list[InsuranceOption]
    notes: list[str]


# --------------------------------------------------------------------------- #
# Corporate financial statements
# --------------------------------------------------------------------------- #

MetricSource = Literal["reported", "derived", "estimated", "unavailable"]


class FinancialMetric(BaseModel):
    """One figure, and an audit trail for how it was arrived at."""

    name: str
    value: Optional[float] = Field(None, description="Null means unknown, never zero.")
    source: MetricSource
    basis: str


class FinancialAnalysisResponse(BaseModel):
    """Headline figures and ratios from a set of accounts, or an estimate of them."""

    source_format: Optional[str] = None
    extraction_method: Optional[str] = None
    reporting_scale: str = Field(..., description="rupees, thousand, lakh, million or crore.")
    scale_multiplier: float
    metrics: dict[str, FinancialMetric]
    ratios: dict[str, FinancialMetric]
    unresolved: list[str] = Field(
        default_factory=list, description="Figures the document could not support."
    )
    evidence: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class BankRow(BaseModel):
    """One bank line, in estimation mode. Narration is what classifies it."""

    type: Literal["credit", "debit"]
    amount: float = Field(..., ge=0.0)
    description: Optional[str] = None
    category: Optional[str] = None


class FinancialEstimateRequest(BaseModel):
    """Estimate accounts from GSTR-3B turnover and bank flows, with no report."""

    gst_taxable_turnover: Optional[float] = Field(
        None, ge=0.0, description="Outward taxable turnover for the period, from GSTR-3B."
    )
    bank_rows: list[BankRow] = Field(default_factory=list)
    period_months: float = Field(
        ..., gt=0, le=60, description="Months the supplied data covers, for annualisation."
    )
