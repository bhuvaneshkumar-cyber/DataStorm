"""Turns a credit score into an underwriting decision, a price, and warnings.

Ported from the IntelliCredit scoring engine's recommendation layer. What is
kept is the structure that makes a decision defensible: a discrete risk grade, a
lend/refer/decline call, risk-based pricing in basis points, an exposure cap,
covenants, and Early Warning Signals.

What is dropped is everything that assumed a company behind the applicant - the
Five Cs weighting over Character/Capital/Collateral/Conditions needs promoter
media sentiment, litigation history and a balance sheet. A gig worker has none
of those. The score already produced by scoring_rules + model_pipeline is the
capacity assessment; this module prices it.

Pure functions over plain data: no I/O, no model, no request objects.
"""

from __future__ import annotations

from typing import Any, Dict, List

import config
from schemas import CreditScoreRequest

# Grade bands over the 0-800 scale, worst-first so the first match wins.
# Mirrors IntelliCredit's IC-1..IC-8 ladder rescaled from its 0-100 range.
_GRADE_BANDS = (
    (640.0, "GS-1", "Minimal Risk"),
    (560.0, "GS-2", "Low Risk"),
    (480.0, "GS-3", "Moderate Risk"),
    (400.0, "GS-4", "Acceptable Risk"),
    (320.0, "GS-5", "Watch"),
    (240.0, "GS-6", "Substandard"),
    (160.0, "GS-7", "Doubtful"),
)
_LOWEST_GRADE = ("GS-8", "Loss")

# Thresholds that trip an Early Warning Signal.
_STASH_RUNWAY_WEEKS_CRITICAL = 1.0
_VOLATILITY_CRITICAL = 0.50
_RATING_DEACTIVATION_RISK = 3.5
_BURNOUT_HOURS_PER_WEEK = 70
_THIN_FILE_AGE = 21
_THIN_FILE_GIGS_PER_WEEK = 10


def risk_grade(score: float) -> Dict[str, str]:
    """Maps a 0-800 score onto a discrete grade an underwriter can file against."""
    for floor, code, label in _GRADE_BANDS:
        if score >= floor:
            return {"code": code, "label": label}
    code, label = _LOWEST_GRADE
    return {"code": code, "label": label}


def risk_tier(score: float) -> str:
    """Pricing tier. Boundaries are the public score bands, so a Good applicant
    can never be priced as VERY_HIGH risk or declined."""
    if score >= config.SCORE_EXCELLENT:
        return "LOW"
    if score >= config.SCORE_GOOD:
        return "MODERATE"
    if score >= config.SCORE_STANDARD:
        return "HIGH"
    return "VERY_HIGH"


def _decision(tier: str) -> str:
    if tier in ("LOW", "MODERATE"):
        return "APPROVE"
    return "REFER" if tier == "HIGH" else "DECLINE"


def _credit_limit(tier: str, average_weekly_payout: float) -> float:
    """Exposure cap as a multiple of monthly payout.

    A gig worker is underwritten on income, not net worth, so the multiplier
    applies to earnings rather than to a balance-sheet figure.
    """
    monthly_income = max(average_weekly_payout, 0.0) * config.WEEKS_PER_MONTH
    return round(monthly_income * config.LOAN_MULTIPLIER[tier], 2)


def _covenants(score: float, applicant: CreditScoreRequest) -> List[str]:
    """Monitoring conditions, tightening as the score falls."""
    conditions: List[str] = []

    if score < config.SCORE_EXCELLENT:
        conditions.append("Quarterly re-verification of platform payout statements")
    if score < config.SCORE_GOOD:
        conditions.append("Active UPI AutoPay mandate required for repayment")
        conditions.append("Maintain a Resilience Stash of at least two weeks of payout")
    if score < config.SCORE_STANDARD:
        conditions.append("Co-applicant or guarantor required")
        conditions.append("Disbursal staged against sustained payout history")

    if applicant.payout_volatility_index > _VOLATILITY_CRITICAL:
        conditions.append("Repayment schedule aligned to payout dates, not calendar dates")
    if applicant.platform_customer_rating < _RATING_DEACTIVATION_RISK:
        conditions.append("Monthly confirmation of continued platform activation")

    return conditions


def early_warning_signals(
    applicant: CreditScoreRequest, ml_available: bool = True
) -> List[Dict[str, str]]:
    """Flags the specific fragilities behind a score, not just its level.

    Two applicants can share a score for opposite reasons; these say which.
    """
    signals: List[Dict[str, str]] = []

    runway_weeks = applicant.resilience_stash_balance / max(applicant.average_weekly_payout, 1.0)
    if runway_weeks < _STASH_RUNWAY_WEEKS_CRITICAL:
        signals.append(
            {
                "code": "THIN_BUFFER",
                "title": f"Savings runway under one week ({runway_weeks:.2f} weeks)",
                "detail": (
                    "A single lean week or vehicle repair forces a missed repayment. "
                    "The Resilience Stash is the strongest predictor of surviving an income gap."
                ),
            }
        )

    if applicant.payout_volatility_index > _VOLATILITY_CRITICAL:
        signals.append(
            {
                "code": "INCOME_INSTABILITY",
                "title": f"Erratic payouts (volatility {applicant.payout_volatility_index:.2f})",
                "detail": (
                    "Week-to-week income swings widely, so a fixed EMI date will "
                    "sometimes land in a low-earning week."
                ),
            }
        )

    if applicant.platform_customer_rating < _RATING_DEACTIVATION_RISK:
        signals.append(
            {
                "code": "PLATFORM_STANDING",
                "title": f"Low platform rating ({applicant.platform_customer_rating:.1f})",
                "detail": (
                    "Ratings at this level risk reduced order allocation or deactivation, "
                    "which would remove the income being lent against."
                ),
            }
        )

    if applicant.active_platform_hours_per_week > _BURNOUT_HOURS_PER_WEEK:
        signals.append(
            {
                "code": "UNSUSTAINABLE_HOURS",
                "title": f"{applicant.active_platform_hours_per_week} active hours per week",
                "detail": (
                    "Current earnings depend on a workload that cannot be sustained "
                    "across the loan tenor."
                ),
            }
        )

    if (
        applicant.age < _THIN_FILE_AGE
        and applicant.completed_gigs_per_week < _THIN_FILE_GIGS_PER_WEEK
    ):
        signals.append(
            {
                "code": "THIN_FILE",
                "title": "Young applicant with limited gig history",
                "detail": "Too little activity to establish an earning pattern.",
            }
        )

    if not ml_available:
        signals.append(
            {
                "code": "MODEL_DEGRADED",
                "title": "Score is rule-based only",
                "detail": (
                    "The ML component was unavailable, so this score carries the "
                    "rule engine's confidence alone. Treat it as indicative."
                ),
            }
        )

    return signals


def assess(
    final_score: float, applicant: CreditScoreRequest, ml_available: bool = True
) -> Dict[str, Any]:
    """Full underwriting view of one scored applicant."""
    tier = risk_tier(final_score)
    premium_bps = config.RISK_PREMIUM_BPS[tier]

    return {
        "risk_grade": risk_grade(final_score),
        "risk_tier": tier,
        "decision": _decision(tier),
        "indicative_interest_rate_pct": round(
            config.BASE_INTEREST_RATE_PCT + premium_bps / 100.0, 2
        ),
        "risk_premium_bps": premium_bps,
        "max_credit_limit_inr": _credit_limit(tier, applicant.average_weekly_payout),
        "recommended_tenor_months": config.TENOR_MONTHS[tier],
        "conditions": _covenants(final_score, applicant),
        "early_warning_signals": early_warning_signals(applicant, ml_available),
    }
