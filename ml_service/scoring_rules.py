"""Deterministic rule engine: the fallback, and 40% of the hybrid score.

Transparent thresholds on purpose - an underwriter must be able to read this
file and explain any decision without a model.
"""

from schemas import CreditScoreRequest

BASE_SCORE = 300.0
MIN_SCORE, MAX_SCORE = 0.0, 800.0

# Platforms differ in payout reliability; small nudge, not a verdict.
PLATFORM_ADJUSTMENT = {
    "Ride-Hailing": 20.0,
    "Food Delivery": 10.0,
    "Freelance": 0.0,
    "Other": -10.0,
}


def calculate_rule_score(payload: CreditScoreRequest) -> float:
    """Return a 0-800 credit score from threshold rules."""
    score = BASE_SCORE

    # Reputation: a >4.5 rating is the strongest non-financial trust signal.
    if payload.platform_customer_rating >= 4.8:
        score += 120
    elif payload.platform_customer_rating >= 4.5:
        score += 90
    elif payload.platform_customer_rating >= 4.0:
        score += 45
    elif payload.platform_customer_rating < 3.5:
        score -= 60

    # Savings buffer: the single best predictor of surviving a lean week.
    stash_weeks = payload.resilience_stash_balance / max(payload.average_weekly_payout, 1.0)
    if stash_weeks >= 4:
        score += 150
    elif stash_weeks >= 2:
        score += 100
    elif stash_weeks >= 1:
        score += 55
    elif payload.resilience_stash_balance <= 0:
        score -= 40

    # Income stability beats income size for repayment capacity.
    if payload.payout_volatility_index <= 0.15:
        score += 110
    elif payload.payout_volatility_index <= 0.30:
        score += 70
    elif payload.payout_volatility_index <= 0.50:
        score += 25
    else:
        score -= 70

    # Earnings level.
    if payload.average_weekly_payout >= 12000:
        score += 90
    elif payload.average_weekly_payout >= 7000:
        score += 60
    elif payload.average_weekly_payout >= 3500:
        score += 30

    # Engagement: consistent supply of work.
    if payload.completed_gigs_per_week >= 50 and payload.active_platform_hours_per_week >= 35:
        score += 60
    elif payload.completed_gigs_per_week >= 25:
        score += 30
    elif payload.completed_gigs_per_week < 10:
        score -= 30

    # Burnout / churn risk: >70h a week is not sustainable earning capacity.
    if payload.active_platform_hours_per_week > 70:
        score -= 25

    # Thin-file young applicants carry more uncertainty.
    if payload.age < 21:
        score -= 25
    elif 25 <= payload.age <= 55:
        score += 20

    score += PLATFORM_ADJUSTMENT.get(payload.primary_gig_platform, 0.0)

    return round(min(max(score, MIN_SCORE), MAX_SCORE), 2)


def categorize(score: float) -> str:
    """Map a 0-800 score onto the product's three bands."""
    if score >= 600:
        return "Good"
    if score >= 400:
        return "Standard"
    return "Poor"
