"""Transaction-driven credit metrics: a ledger in, an explained score out.

Ported from the AltCred credit engine (`services/creditEngine/`). It answers a
different question from `scoring_rules.py`, which is why both belong here:

  scoring_rules.py  scores 8 pre-summarised features and says how creditworthy.
  credit_metrics.py scores a raw transaction ledger and says *why*, metric by
                    metric, with a status label and a coaching action for each.

The engine is source-agnostic by design. Anything that can be expressed as
`Transaction` records - a parsed bank statement, a platform payout feed, manual
entries - can be scored, with no knowledge of where the rows came from.

Composite output is on the same 0-800 scale as the rest of this service, so
`risk_policy.risk_grade` applies unchanged. Pricing deliberately stays in
risk_policy: it needs applicant facts a ledger does not contain.

Pure functions throughout - no I/O, no models, no request objects.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

import config
import metric_definitions as md
from metric_definitions import MetricSpec, score_from_bands

# Coaching copy per metric, surfaced when that metric scores as a weakness.
# Phrased as something a gig worker can actually do this month.
_ACTIONS: Dict[str, str] = {
    "avg_monthly_income": "Increase weekly earning hours or add a second platform.",
    "income_volatility": "Even out weekly hours so income lands in a predictable range.",
    "income_consistency": "Work a similar number of days each month, rather than in bursts.",
    "income_trend": "Earnings are trending down - check platform incentives or add a source.",
    "active_work_days": "Spread work across more days in the month.",
    "income_diversification": "Add a second platform so one deactivation cannot end all income.",
    "work_stability": "Avoid long stretches with no earnings; short regular gigs beat rare large ones.",
    "net_cash_flow_ratio": "Aim to keep at least 10% of what you earn.",
    "savings_behavior": "Set an automatic sweep so saving does not depend on remembering.",
    "expense_shocks": "Build a buffer for irregular costs such as repairs and insurance.",
    "fixed_obligation_ratio": "Recurring commitments take a large share of income - reduce or refinance one.",
    "avg_daily_balance": "Keep a working balance in the account rather than withdrawing in full.",
    "negative_balance_risk": "Hold a small floor in the account to avoid running empty.",
    "gig_stability": "Keep earning steadily; a longer track record raises this on its own.",
}

_CATEGORY_LABELS: Dict[str, str] = {
    "income_quality": "Income quality",
    "spending_behavior": "Spending behaviour",
    "liquidity": "Liquidity",
    "gig_stability": "Gig stability",
}

# Returned when a metric cannot be computed. A neutral 50 keeps a thin file from
# being scored as though it had failed, while the status says so plainly.
_NEUTRAL_SCORE = 50.0


class InsufficientDataError(Exception):
    """Too few transactions to compute anything meaningful."""


@dataclass(frozen=True)
class Transaction:
    """One standardized ledger row, whatever the source."""

    date: date
    type: str  # "credit" | "debit"
    amount: float
    category: Optional[str] = None
    source: Optional[str] = None
    description: Optional[str] = None

    @property
    def month(self) -> str:
        return self.date.strftime("%Y-%m")


@dataclass(frozen=True)
class MetricResult:
    """One metric's value, its 0-100 score, and a human-readable status."""

    name: str
    value: float
    score: float
    status: str
    description: str

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "score": self.score,
            "status": self.status,
            "description": self.description,
        }


def _result(name: str, spec: MetricSpec, value: float) -> MetricResult:
    score, status = score_from_bands(value, spec.bands)
    return MetricResult(name, round(value, 4), score, status, spec.description)


def _unavailable(name: str, spec: MetricSpec, status: str) -> MetricResult:
    """A metric that could not be computed, held at neutral rather than zero."""
    return MetricResult(name, 0.0, _NEUTRAL_SCORE, status, spec.description)


# --------------------------------------------------------------------------- #
# Monthly grouping
# --------------------------------------------------------------------------- #


@dataclass
class MonthBucket:
    credits: float = 0.0
    debits: float = 0.0
    credit_days: set = None  # type: ignore[assignment]
    debit_categories: Dict[str, List[float]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.credit_days is None:
            self.credit_days = set()
        if self.debit_categories is None:
            self.debit_categories = defaultdict(list)


def _group_by_month(transactions: Sequence[Transaction]) -> Dict[str, MonthBucket]:
    """Buckets a ledger into calendar months, keyed YYYY-MM."""
    months: Dict[str, MonthBucket] = defaultdict(MonthBucket)
    for tx in transactions:
        bucket = months[tx.month]
        if tx.type == "credit":
            bucket.credits += tx.amount
            bucket.credit_days.add(tx.date)
        else:
            bucket.debits += tx.amount
            bucket.debit_categories[tx.category or tx.description or "uncategorised"].append(
                tx.amount
            )
    return dict(months)


def _calendar_months_spanned(transactions: Sequence[Transaction]) -> int:
    """Calendar months between first and last row, inclusive.

    Counted from the calendar, not from months that happen to contain income:
    otherwise a worker who earned in January and June looks perfectly consistent
    because both of their two active months had income.
    """
    dates = [tx.date for tx in transactions]
    first, last = min(dates), max(dates)
    return (last.year - first.year) * 12 + (last.month - first.month) + 1


# --------------------------------------------------------------------------- #
# Income quality
# --------------------------------------------------------------------------- #


def income_metrics(transactions: Sequence[Transaction]) -> Dict[str, MetricResult]:
    """Earning capacity, stability, consistency, trend, activity, diversification."""
    specs = md.INCOME_METRICS
    months = _group_by_month(transactions)
    monthly_income = [b.credits for b in months.values() if b.credits > 0]
    credits = [tx for tx in transactions if tx.type == "credit"]

    results: Dict[str, MetricResult] = {}

    # --- level ---
    if monthly_income:
        results["avg_monthly_income"] = _result(
            "avg_monthly_income", specs["avg_monthly_income"], statistics.fmean(monthly_income)
        )
    else:
        results["avg_monthly_income"] = MetricResult(
            "avg_monthly_income", 0.0, 0.0, "No Income Data", specs["avg_monthly_income"].description
        )

    # --- volatility ---
    if len(monthly_income) >= 2:
        mean = statistics.fmean(monthly_income)
        # Population stdev, matching the source engine: this is the whole
        # observed history, not a sample drawn from a larger one.
        spread = statistics.pstdev(monthly_income)
        results["income_volatility"] = _result(
            "income_volatility", specs["income_volatility"], spread / mean if mean > 0 else 0.0
        )
    else:
        results["income_volatility"] = _unavailable(
            "income_volatility", specs["income_volatility"], "Insufficient Data"
        )

    # --- consistency: months with income AND days worked within them ---
    if credits:
        calendar_months = _calendar_months_spanned(transactions)
        months_with_income = len(monthly_income)
        monthly_presence = min(1.0, months_with_income / max(calendar_months, 1))

        work_days = [len(b.credit_days) for b in months.values() if b.credit_days]
        avg_work_days = statistics.fmean(work_days) if work_days else 0.0
        daily_regularity = min(1.0, avg_work_days / md.EXPECTED_WORK_DAYS_PER_MONTH)

        # Geometric mean: strong on one axis cannot mask a collapse on the other.
        consistency = (monthly_presence * daily_regularity) ** 0.5 * 100
        results["income_consistency"] = _result(
            "income_consistency", specs["income_consistency"], consistency
        )

        results["active_work_days"] = _result(
            "active_work_days", specs["active_work_days"], avg_work_days
        )
    else:
        results["income_consistency"] = MetricResult(
            "income_consistency", 0.0, 0.0, "No Income Data", specs["income_consistency"].description
        )
        results["active_work_days"] = MetricResult(
            "active_work_days", 0.0, 0.0, "No Income Data", specs["active_work_days"].description
        )

    # --- trend: needs at least three months to distinguish trend from noise ---
    ordered = sorted(m for m, b in months.items() if b.credits > 0)
    if len(ordered) >= 3:
        growths = [
            (months[curr].credits - months[prev].credits) / months[prev].credits * 100
            for prev, curr in zip(ordered, ordered[1:])
            if months[prev].credits > 0
        ]
        results["income_trend"] = _result(
            "income_trend", specs["income_trend"], statistics.fmean(growths) if growths else 0.0
        )
    else:
        # Two months of data can only show noise. Held mid-band rather than
        # penalised: a short history is not evidence of decline.
        results["income_trend"] = MetricResult(
            "income_trend", 0.0, 60.0, "Insufficient History", specs["income_trend"].description
        )

    # --- diversification ---
    if credits:
        sources = {tx.category or tx.source or "unknown" for tx in credits}
        results["income_diversification"] = _result(
            "income_diversification", specs["income_diversification"], len(sources)
        )
    else:
        results["income_diversification"] = MetricResult(
            "income_diversification",
            0.0,
            0.0,
            "No Income Data",
            specs["income_diversification"].description,
        )

    # --- work stability: the longest drought ---
    if len(credits) >= 2:
        earning_days = sorted({tx.date for tx in credits})
        max_gap = max((b - a).days for a, b in zip(earning_days, earning_days[1:])) if len(earning_days) >= 2 else 0
        results["work_stability"] = _result("work_stability", specs["work_stability"], max_gap)
    else:
        results["work_stability"] = _unavailable(
            "work_stability", specs["work_stability"], "Insufficient Data"
        )

    return results


# --------------------------------------------------------------------------- #
# Spending behaviour
# --------------------------------------------------------------------------- #


def spending_metrics(transactions: Sequence[Transaction]) -> Dict[str, MetricResult]:
    """Savings rate, savings habit, expense shocks, fixed commitments."""
    specs = md.SPENDING_METRICS
    months = _group_by_month(transactions)
    buckets = list(months.values())
    results: Dict[str, MetricResult] = {}

    if not buckets:
        return {
            name: _unavailable(name, spec, "No Transaction Data")
            for name, spec in specs.items()
        }

    earning_months = [b for b in buckets if b.credits > 0]

    # --- net cash flow ratio ---
    if earning_months:
        ratios = [(b.credits - b.debits) / b.credits for b in earning_months]
        results["net_cash_flow_ratio"] = _result(
            "net_cash_flow_ratio", specs["net_cash_flow_ratio"], statistics.fmean(ratios)
        )
    else:
        results["net_cash_flow_ratio"] = _unavailable(
            "net_cash_flow_ratio", specs["net_cash_flow_ratio"], "No Income Data"
        )

    # --- savings behaviour ---
    saving_months = sum(1 for b in buckets if b.credits > b.debits)
    results["savings_behavior"] = _result(
        "savings_behavior", specs["savings_behavior"], saving_months / len(buckets) * 100
    )

    # --- expense shocks ---
    if len(buckets) >= 2:
        avg_expenses = statistics.fmean([b.debits for b in buckets])
        threshold = avg_expenses * md.EXPENSE_SHOCK_MULTIPLE
        shocks = sum(1 for b in buckets if b.debits > threshold)
        results["expense_shocks"] = _result("expense_shocks", specs["expense_shocks"], shocks)
    else:
        results["expense_shocks"] = MetricResult(
            "expense_shocks", 0.0, 100.0, "Insufficient Data", specs["expense_shocks"].description
        )

    # --- fixed obligations ---
    results["fixed_obligation_ratio"] = _fixed_obligations(months, specs["fixed_obligation_ratio"])
    return results


def _fixed_obligations(months: Dict[str, MonthBucket], spec: MetricSpec) -> MetricResult:
    """Share of income committed to expenses that recur month after month.

    Recurrence is counted in *months*, not in transactions. Counting transactions
    (as the source engine did) lets twenty coffees in a single month register as
    a fixed monthly commitment.
    """
    if len(months) < 2:
        return MetricResult(
            "fixed_obligation_ratio", 0.0, 100.0, "Insufficient Data", spec.description
        )

    months_per_category: Dict[str, List[float]] = defaultdict(list)
    for bucket in months.values():
        for category, amounts in bucket.debit_categories.items():
            months_per_category[category].append(sum(amounts))

    required_months = max(2, round(len(months) * md.RECURRING_MONTH_SHARE))
    recurring_total = sum(
        statistics.median(monthly_totals)
        for monthly_totals in months_per_category.values()
        if len(monthly_totals) >= required_months
    )

    incomes = [b.credits for b in months.values() if b.credits > 0]
    avg_income = statistics.fmean(incomes) if incomes else 0.0
    ratio = recurring_total / avg_income if avg_income > 0 else 0.0

    return _result("fixed_obligation_ratio", spec, ratio)


# --------------------------------------------------------------------------- #
# Liquidity
# --------------------------------------------------------------------------- #


def daily_balances(
    transactions: Sequence[Transaction], opening_balance: float = 0.0
) -> List[float]:
    """End-of-day balance for every day in the period, gaps carried forward.

    `opening_balance` matters: with the default 0 this is really cumulative net
    cash flow rather than a bank balance, which understates liquidity for anyone
    who started the period with money. Callers that parsed a real balance column
    should pass it.
    """
    if not transactions:
        return []

    ordered = sorted(transactions, key=lambda t: t.date)
    movement: Dict[date, float] = defaultdict(float)
    for tx in ordered:
        movement[tx.date] += tx.amount if tx.type == "credit" else -tx.amount

    balances: List[float] = []
    running = opening_balance
    current, last_day = ordered[0].date, ordered[-1].date
    while current <= last_day:
        running += movement.get(current, 0.0)
        balances.append(running)
        current = date.fromordinal(current.toordinal() + 1)
    return balances


def liquidity_metrics(
    transactions: Sequence[Transaction], opening_balance: float = 0.0
) -> Dict[str, MetricResult]:
    """Cash cushion strength and how often it runs near empty."""
    specs = md.LIQUIDITY_METRICS
    balances = daily_balances(transactions, opening_balance)

    if not balances:
        return {
            name: _unavailable(name, spec, "No Transaction Data")
            for name, spec in specs.items()
        }

    average = statistics.fmean(balances)
    threshold = max(average * md.LOW_BALANCE_SHARE, md.LOW_BALANCE_FLOOR_INR)
    low_days = sum(1 for balance in balances if balance < threshold)

    return {
        "avg_daily_balance": _result("avg_daily_balance", specs["avg_daily_balance"], average),
        "negative_balance_risk": _result(
            "negative_balance_risk",
            specs["negative_balance_risk"],
            low_days / len(balances) * 100,
        ),
    }


# --------------------------------------------------------------------------- #
# Gig stability
# --------------------------------------------------------------------------- #


def gig_metrics(
    transactions: Sequence[Transaction], platform_rating: Optional[float] = None
) -> Dict[str, MetricResult]:
    """Platform standing where known, otherwise length of earning history."""
    spec = md.GIG_METRICS["gig_stability"]

    if platform_rating is not None:
        if platform_rating >= 4.5:
            value, status = 90.0, "Excellent Platform Rating"
        elif platform_rating >= 4.0:
            value, status = 70.0, "Good Platform Rating"
        elif platform_rating >= 3.5:
            value, status = 55.0, "Average Platform Rating"
        else:
            value, status = 40.0, "Below Average Rating"
        return {"gig_stability": MetricResult("gig_stability", value, value, status, spec.description)}

    earning_months = len({tx.month for tx in transactions if tx.type == "credit"})
    if earning_months >= 6:
        value, status = 70.0, "Long-term Earning History"
    elif earning_months >= 3:
        value, status = 55.0, "Moderate Earning History"
    elif earning_months >= 1:
        value, status = 40.0, "Limited Earning History"
    else:
        value, status = _NEUTRAL_SCORE, "No Gig Data Available"

    return {"gig_stability": MetricResult("gig_stability", value, value, status, spec.description)}


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #


def _category_score(results: Dict[str, MetricResult], specs: Dict[str, MetricSpec]) -> float:
    """Weighted mean of a category's metric scores."""
    weighted = sum(results[name].score * spec.weight for name, spec in specs.items() if name in results)
    total_weight = sum(spec.weight for name, spec in specs.items() if name in results)
    return round(weighted / total_weight, 2) if total_weight else _NEUTRAL_SCORE


def _coaching(
    category_scores: Dict[str, float], metrics: Dict[str, MetricResult]
) -> Tuple[List[str], List[str], List[str]]:
    """Strengths, weaknesses, and the actions that would move the weakest metrics.

    Actions are driven by individual metric scores rather than category averages,
    so the advice names the thing actually dragging the score down.
    """
    strengths = [
        f"{_CATEGORY_LABELS[name]} is strong ({score:.0f}/100)"
        for name, score in category_scores.items()
        if score >= md.STRENGTH_THRESHOLD
    ]
    weaknesses = [
        f"{_CATEGORY_LABELS[name]} is weak ({score:.0f}/100)"
        for name, score in category_scores.items()
        if score < md.WEAKNESS_THRESHOLD
    ]

    # Worst metrics first, so the highest-leverage action leads.
    failing = sorted(
        (m for m in metrics.values() if m.score < md.WEAKNESS_THRESHOLD and m.name in _ACTIONS),
        key=lambda m: m.score,
    )
    actions = [_ACTIONS[m.name] for m in failing][:5]

    if not strengths:
        strengths.append("Building a credit profile - keep the ledger growing.")
    return strengths, weaknesses, actions


def analyze(
    transactions: Sequence[Transaction],
    platform_rating: Optional[float] = None,
    opening_balance: float = 0.0,
) -> dict:
    """Scores a ledger and explains the result.

    Returns the composite score on this service's 0-800 scale, the four category
    scores, every metric with its status, and coaching derived from the weakest
    metrics.
    """
    if not transactions:
        raise InsufficientDataError("At least one transaction is required.")

    by_category = {
        "income_quality": income_metrics(transactions),
        "spending_behavior": spending_metrics(transactions),
        "liquidity": liquidity_metrics(transactions, opening_balance),
        "gig_stability": gig_metrics(transactions, platform_rating),
    }

    category_scores = {
        name: _category_score(results, md.CATEGORY_METRICS[name])
        for name, results in by_category.items()
    }

    composite = sum(
        category_scores[name] * weight for name, weight in md.CATEGORY_WEIGHTS.items()
    ) / 100.0

    # Rescale 0-100 onto this service's 0-800 range so risk_policy applies as-is.
    credit_score = round(
        min(max(composite / 100.0 * config.MAX_SCORE, config.MIN_SCORE), config.MAX_SCORE), 2
    )

    flat = {name: result for results in by_category.values() for name, result in results.items()}
    strengths, weaknesses, actions = _coaching(category_scores, flat)

    dates = sorted(tx.date for tx in transactions)
    return {
        "credit_score": credit_score,
        "composite_score": round(composite, 2),
        "category_scores": category_scores,
        "category_weights": dict(md.CATEGORY_WEIGHTS),
        "metrics": {name: result.as_dict() for name, result in flat.items()},
        "strengths": strengths,
        "weaknesses": weaknesses,
        "recommended_actions": actions,
        "coverage": {
            "transactions": len(transactions),
            "credits": sum(1 for tx in transactions if tx.type == "credit"),
            "debits": sum(1 for tx in transactions if tx.type == "debit"),
            "months_observed": len({tx.month for tx in transactions}),
            "period_start": dates[0].isoformat(),
            "period_end": dates[-1].isoformat(),
        },
    }


def from_records(records: Sequence[dict]) -> List[Transaction]:
    """Validates and parses standardized ledger dicts into Transaction records.

    The single entry point for untrusted input, so every caller - HTTP body,
    parsed statement, future platform feed - gets the same validation. Raises
    InsufficientDataError with the offending row index, because a ledger that
    silently drops rows produces a confidently wrong score.
    """
    if not records:
        raise InsufficientDataError("At least one transaction is required.")

    parsed: List[Transaction] = []
    for index, row in enumerate(records):
        if not isinstance(row, dict):
            raise InsufficientDataError(f"Transaction {index} is not an object.")

        raw_date = row.get("date")
        try:
            when = raw_date if isinstance(raw_date, date) else date.fromisoformat(str(raw_date)[:10])
        except (TypeError, ValueError) as exc:
            raise InsufficientDataError(
                f"Transaction {index}: {raw_date!r} is not an ISO date (YYYY-MM-DD)."
            ) from exc

        kind = str(row.get("type", "")).lower()
        if kind not in ("credit", "debit"):
            raise InsufficientDataError(
                f"Transaction {index}: type must be 'credit' or 'debit', got {row.get('type')!r}."
            )

        try:
            amount = float(row.get("amount"))
        except (TypeError, ValueError) as exc:
            raise InsufficientDataError(
                f"Transaction {index}: amount {row.get('amount')!r} is not a number."
            ) from exc
        if amount < 0:
            raise InsufficientDataError(f"Transaction {index}: amount must be non-negative.")

        parsed.append(
            Transaction(
                date=when,
                type=kind,
                amount=amount,
                category=row.get("category"),
                source=row.get("source"),
                description=row.get("description"),
            )
        )
    return parsed
