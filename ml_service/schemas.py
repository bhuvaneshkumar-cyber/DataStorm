"""Request/response contracts for the gig-worker credit scoring service."""

from typing import Literal

from pydantic import BaseModel, Field

GigPlatform = Literal["Ride-Hailing", "Food Delivery", "Freelance", "Other"]
ScoreCategory = Literal["Poor", "Standard", "Good"]


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


class CreditScoreResponse(BaseModel):
    final_score: float = Field(..., description="Hybrid score, 0-800.")
    category: ScoreCategory
    confidence: float = Field(..., ge=0.0, le=1.0)
    rule_score: float
    ml_score: float | None = Field(None, description="None when the ML path degraded to rules only.")
    ml_available: bool
    explanation: list[ShapFactor] = Field(default_factory=list, description="Top 3 drivers.")
    latency_ms: float
