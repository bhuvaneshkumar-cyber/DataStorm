"""Scoring bands and weights for the transaction-driven credit metrics.

Ported from the AltCred credit engine's `config/metricDefinitions.js`. Every
threshold an underwriter might want to move lives here and nowhere else, which
is the property that made the original worth copying.

One structural change from the source. AltCred expressed each band as a
`{min, max}` pair:

    { min: 0,    max: 0.15, score: 100 },
    { min: 0.16, max: 0.30, score: 80  },

Those pairs leave gaps. A volatility of 0.155 matches no band, and the original
`getScoreFromBands` fallback then returns the *last* band - scoring an
excellent applicant as "Very High Volatility". Bands here are instead ordered
upper bounds, so the ranges are contiguous by construction and a gap cannot be
written into the table by accident.
"""

from __future__ import annotations

import math
from typing import Dict, List, NamedTuple, Tuple


class Band(NamedTuple):
    """Everything at or below `upper` (and above the previous band) scores this."""

    upper: float
    score: float
    status: str


class MetricSpec(NamedTuple):
    """One metric's contribution to its category, plus how its value is scored."""

    weight: float
    bands: Tuple[Band, ...]
    higher_is_better: bool
    description: str


INF = math.inf

# Category weights over the final composite. Must sum to 100.
CATEGORY_WEIGHTS: Dict[str, float] = {
    "income_quality": 35.0,
    "spending_behavior": 30.0,
    "liquidity": 20.0,
    "gig_stability": 15.0,
}

# Scores below this are a weakness worth acting on; at or above the other, a strength.
WEAKNESS_THRESHOLD = 50.0
STRENGTH_THRESHOLD = 70.0

# A month is assumed to hold this many working days when judging regularity.
EXPECTED_WORK_DAYS_PER_MONTH = 22

# Monthly expenses above this multiple of the average count as a shock.
EXPENSE_SHOCK_MULTIPLE = 1.5

# A category counts as a fixed obligation once it appears in this share of months.
RECURRING_MONTH_SHARE = 0.5

# Days below this share of the average balance count toward liquidity risk,
# floored so a low-income applicant is not judged against a trivially small bar.
LOW_BALANCE_SHARE = 0.10
LOW_BALANCE_FLOOR_INR = 1000.0


INCOME_METRICS: Dict[str, MetricSpec] = {
    "avg_monthly_income": MetricSpec(
        weight=20.0,
        higher_is_better=True,
        description="Average monthly credits. Raw earning capacity.",
        bands=(
            Band(10_000, 20, "Very Low Income"),
            Band(20_000, 40, "Low Income"),
            Band(35_000, 60, "Moderate Income"),
            Band(50_000, 80, "Good Income"),
            Band(INF, 100, "Excellent Income"),
        ),
    ),
    "income_volatility": MetricSpec(
        weight=15.0,
        higher_is_better=False,
        description="Coefficient of variation of monthly income. Lower is steadier.",
        bands=(
            Band(0.15, 100, "Very Stable"),
            Band(0.30, 80, "Stable"),
            Band(0.50, 60, "Moderate Volatility"),
            Band(0.75, 40, "High Volatility"),
            Band(INF, 20, "Very High Volatility"),
        ),
    ),
    "income_consistency": MetricSpec(
        weight=15.0,
        higher_is_better=True,
        description="Blend of months-with-income and working-days-per-month, as a percentage.",
        bands=(
            Band(40, 20, "Very Inconsistent"),
            Band(60, 40, "Inconsistent"),
            Band(75, 60, "Moderately Consistent"),
            Band(90, 80, "Consistent"),
            Band(INF, 100, "Highly Consistent"),
        ),
    ),
    "income_trend": MetricSpec(
        weight=15.0,
        higher_is_better=True,
        description="Average month-over-month growth in income, as a percentage.",
        bands=(
            Band(-10, 20, "Declining"),
            Band(-5, 40, "Slightly Declining"),
            Band(5, 60, "Stable"),
            Band(15, 80, "Growing"),
            Band(INF, 100, "Rapidly Growing"),
        ),
    ),
    "active_work_days": MetricSpec(
        weight=10.0,
        higher_is_better=True,
        description="Average distinct earning days per month.",
        bands=(
            Band(5, 20, "Very Low Activity"),
            Band(10, 40, "Low Activity"),
            Band(15, 60, "Moderate Activity"),
            Band(22, 80, "High Activity"),
            Band(INF, 100, "Very High Activity"),
        ),
    ),
    "income_diversification": MetricSpec(
        weight=15.0,
        higher_is_better=True,
        description="Distinct income sources. One platform deactivation should not end all income.",
        bands=(
            Band(1, 20, "Single Source"),
            Band(2, 50, "Two Sources"),
            Band(3, 75, "Multiple Sources"),
            Band(INF, 100, "Highly Diversified"),
        ),
    ),
    "work_stability": MetricSpec(
        weight=10.0,
        higher_is_better=False,
        description="Longest gap in days between earnings. Shorter is steadier.",
        bands=(
            Band(3, 100, "Excellent Stability"),
            Band(7, 80, "Good Stability"),
            Band(14, 60, "Moderate Gaps"),
            Band(30, 40, "Significant Gaps"),
            Band(INF, 20, "Extended Gaps"),
        ),
    ),
}


SPENDING_METRICS: Dict[str, MetricSpec] = {
    "net_cash_flow_ratio": MetricSpec(
        weight=30.0,
        higher_is_better=True,
        description="(income - expenses) / income, averaged across months.",
        bands=(
            Band(0.0, 0, "Negative Cash Flow"),
            Band(0.10, 30, "Minimal Savings"),
            Band(0.20, 60, "Moderate Savings"),
            Band(0.35, 80, "Good Savings"),
            Band(INF, 100, "Excellent Savings"),
        ),
    ),
    "savings_behavior": MetricSpec(
        weight=30.0,
        higher_is_better=True,
        description="Percentage of months that ended cash-flow positive.",
        bands=(
            Band(30, 20, "Rarely Saves"),
            Band(50, 40, "Occasionally Saves"),
            Band(70, 60, "Frequently Saves"),
            Band(85, 80, "Consistently Saves"),
            Band(INF, 100, "Always Saves"),
        ),
    ),
    "expense_shocks": MetricSpec(
        weight=20.0,
        higher_is_better=False,
        description="Count of months whose spending exceeded 150% of the average.",
        bands=(
            Band(0, 100, "No Shocks"),
            Band(1, 80, "Rare Shocks"),
            Band(2, 60, "Occasional Shocks"),
            Band(3, 40, "Frequent Shocks"),
            Band(INF, 20, "Very Frequent Shocks"),
        ),
    ),
    "fixed_obligation_ratio": MetricSpec(
        weight=20.0,
        higher_is_better=False,
        description="Recurring monthly commitments as a share of income.",
        bands=(
            Band(0.20, 100, "Very Low Obligations"),
            Band(0.35, 80, "Low Obligations"),
            Band(0.50, 60, "Moderate Obligations"),
            Band(0.70, 40, "High Obligations"),
            Band(INF, 20, "Very High Obligations"),
        ),
    ),
}


LIQUIDITY_METRICS: Dict[str, MetricSpec] = {
    "avg_daily_balance": MetricSpec(
        weight=60.0,
        higher_is_better=True,
        description="Average end-of-day balance across the statement period.",
        bands=(
            Band(-1, 0, "Negative Balance"),
            Band(1_000, 20, "Very Low Liquidity"),
            Band(3_000, 40, "Low Liquidity"),
            Band(7_000, 60, "Moderate Liquidity"),
            Band(15_000, 80, "Good Liquidity"),
            Band(INF, 100, "Excellent Liquidity"),
        ),
    ),
    "negative_balance_risk": MetricSpec(
        weight=40.0,
        higher_is_better=False,
        description="Percentage of days spent near or below an empty balance.",
        bands=(
            Band(5, 100, "No Risk"),
            Band(15, 80, "Low Risk"),
            Band(30, 60, "Moderate Risk"),
            Band(50, 40, "High Risk"),
            Band(INF, 20, "Very High Risk"),
        ),
    ),
}


GIG_METRICS: Dict[str, MetricSpec] = {
    "gig_stability": MetricSpec(
        weight=100.0,
        higher_is_better=True,
        description="Platform standing where known, otherwise length of earning history.",
        bands=(
            Band(40, 40, "Limited Earning History"),
            Band(55, 55, "Moderate Earning History"),
            Band(70, 70, "Long-term Earning History"),
            Band(INF, 90, "Excellent Platform Rating"),
        ),
    ),
}


# Every metric by name, for lookups that do not care about the category.
ALL_METRICS: Dict[str, MetricSpec] = {
    **INCOME_METRICS,
    **SPENDING_METRICS,
    **LIQUIDITY_METRICS,
    **GIG_METRICS,
}

CATEGORY_METRICS: Dict[str, Dict[str, MetricSpec]] = {
    "income_quality": INCOME_METRICS,
    "spending_behavior": SPENDING_METRICS,
    "liquidity": LIQUIDITY_METRICS,
    "gig_stability": GIG_METRICS,
}


def score_from_bands(value: float, bands: Tuple[Band, ...]) -> Tuple[float, str]:
    """First band whose upper bound the value does not exceed.

    Bands are contiguous and the last one is unbounded, so this always matches -
    there is no fallback branch to get wrong.
    """
    for band in bands:
        if value <= band.upper:
            return band.score, band.status
    last = bands[-1]
    return last.score, last.status


def validate_definitions() -> List[str]:
    """Structural problems in the tables above. Empty list means they are sound.

    Run by the test suite: a mistuned weight or an out-of-order band is invisible
    at runtime - it just quietly produces wrong scores.
    """
    problems: List[str] = []

    total = sum(CATEGORY_WEIGHTS.values())
    if abs(total - 100.0) > 1e-9:
        problems.append(f"CATEGORY_WEIGHTS sum to {total}, expected 100")

    for category, metrics in CATEGORY_METRICS.items():
        weight_total = sum(spec.weight for spec in metrics.values())
        if abs(weight_total - 100.0) > 1e-9:
            problems.append(f"{category} metric weights sum to {weight_total}, expected 100")

        for name, spec in metrics.items():
            if not spec.bands:
                problems.append(f"{name} has no bands")
                continue
            if spec.bands[-1].upper != INF:
                problems.append(f"{name} last band must be unbounded, got {spec.bands[-1].upper}")
            uppers = [band.upper for band in spec.bands]
            if uppers != sorted(uppers):
                problems.append(f"{name} bands are not in ascending order: {uppers}")

    return problems
