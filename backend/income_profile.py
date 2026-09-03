"""Builds the eight scoring features from a worker's own recorded evidence.

This is the bridge between "which platforms has this person connected and what
have they actually logged" and "what do we score them on". It exists so that no
caller -- not the dashboard, not the loan route -- ever invents those features
itself, and so that every value carries a note when it came from a default
rather than from evidence.

Measured beats declared throughout: if the transaction ledger can support a
figure, it wins over the number typed into a platform connection form.

Pure functions over plain dicts, so the whole derivation is testable without a
database or a running scoring service.
"""

from __future__ import annotations

import statistics
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence

from analytics import INCOME_TYPE, parse_timestamp

# The scoring service knows four platform categories. Anything a worker types is
# mapped onto one of them here rather than being passed through and rejected.
_PLATFORM_KEYWORDS: Dict[str, tuple[str, ...]] = {
    "Ride-Hailing": ("uber", "ola", "rapido", "indrive", "lyft", "bolt", "namma yatri", "meru"),
    "Food Delivery": (
        "swiggy", "zomato", "zepto", "blinkit", "dunzo", "instamart", "bigbasket",
        "eatsure", "dominos", "delivery",
    ),
    "Freelance": (
        "upwork", "fiverr", "freelance", "toptal", "urban company", "urbanclap",
        "consult", "design", "writing",
    ),
}
_DEFAULT_PLATFORM = "Other"

# Documented defaults, used only when nothing evidences the feature. Deliberately
# unflattering-to-neutral: an unevidenced applicant must not be scored as though
# the missing facts were favourable. Every use is named in `assumptions`.
DEFAULT_AGE = 30
DEFAULT_RATING = 4.0
DEFAULT_HOURS_PER_WEEK = 40
DEFAULT_VOLATILITY = 0.5

_DAYS_PER_WEEK = 7
_MAX_HOURS_PER_WEEK = 120
_MAX_GIGS_PER_WEEK = 200
_MIN_WEEKS_FOR_VOLATILITY = 2


def classify_platform(name: Optional[str]) -> str:
    """Maps a free-text platform name onto a scoring category."""
    lowered = (name or "").strip().casefold()
    if not lowered:
        return _DEFAULT_PLATFORM
    for category, keywords in _PLATFORM_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    return _DEFAULT_PLATFORM


def age_from(date_of_birth: Optional[date], today: Optional[date] = None) -> Optional[int]:
    """Whole years, birthday-aware. None when there is no date to work from."""
    if date_of_birth is None:
        return None
    reference = today or date.today()
    years = reference.year - date_of_birth.year
    if (reference.month, reference.day) < (date_of_birth.month, date_of_birth.day):
        years -= 1
    return years


def _weekly_payout_totals(rows: Sequence[dict]) -> List[float]:
    """Payout totals per ISO week, oldest first.

    Weeks with no payout are included as zero: a worker who earned nothing in
    week two has volatile income, and dropping the gap would hide exactly that.
    """
    by_week: Dict[tuple, float] = {}
    stamps: List[datetime] = []

    for row in rows:
        if row.get("transaction_type") != INCOME_TYPE:
            continue
        stamp = parse_timestamp(row.get("timestamp"))
        if stamp is None:
            continue
        stamps.append(stamp)
        key = stamp.isocalendar()[:2]
        by_week[key] = by_week.get(key, 0.0) + abs(float(row.get("amount") or 0.0))

    if not stamps:
        return []

    # Walk every week between the first and last payout so the zero weeks appear.
    first, last = min(stamps).date(), max(stamps).date()
    totals: List[float] = []
    cursor = first
    while cursor <= last:
        totals.append(by_week.get(cursor.isocalendar()[:2], 0.0))
        cursor = date.fromordinal(cursor.toordinal() + _DAYS_PER_WEEK)
    return totals


def volatility_index(weekly_totals: Sequence[float]) -> Optional[float]:
    """Coefficient of variation clamped to 0..1, or None on too little data.

    Clamped rather than scaled: beyond a standard deviation equal to the mean,
    income is simply "wildly erratic" and the scorer's band does not get finer.
    """
    usable = [t for t in weekly_totals]
    if len(usable) < _MIN_WEEKS_FOR_VOLATILITY:
        return None
    mean = statistics.fmean(usable)
    if mean <= 0:
        return 1.0
    return round(min(statistics.pstdev(usable) / mean, 1.0), 4)


def build(
    *,
    date_of_birth: Optional[date],
    platform_accounts: Sequence[dict],
    transactions: Sequence[dict],
    stash_balance: float,
    today: Optional[date] = None,
) -> dict:
    """Derives the eight features, naming every value that fell back to a default."""
    reference = today or date.today()
    assumptions: List[str] = []

    age = age_from(date_of_birth, reference)
    if age is None or not 18 <= age <= 75:
        if age is not None:
            assumptions.append(
                f"Recorded date of birth gives an age of {age}, outside the 18-75 range "
                f"the scorer accepts; {DEFAULT_AGE} used instead."
            )
        else:
            assumptions.append(f"No date of birth on file; age assumed to be {DEFAULT_AGE}.")
        age = DEFAULT_AGE

    # --- Platform-declared figures ----------------------------------------- #
    declared_weekly = sum(float(p.get("weekly_payout") or 0.0) for p in platform_accounts)
    declared_gigs = sum(float(p.get("gigs_per_week") or 0.0) for p in platform_accounts)
    declared_hours = sum(float(p.get("hours_per_week") or 0.0) for p in platform_accounts)

    rated = [p for p in platform_accounts if p.get("customer_rating")]
    if rated:
        # Weighted by payout so the platform a worker actually earns on drives
        # the rating, not a dormant account with one five-star review.
        weights = [max(float(p.get("weekly_payout") or 0.0), 1.0) for p in rated]
        rating = sum(float(p["customer_rating"]) * w for p, w in zip(rated, weights)) / sum(weights)
        rating = round(min(max(rating, 1.0), 5.0), 2)
    else:
        assumptions.append(
            f"No platform rating recorded; {DEFAULT_RATING} used. Connect a platform "
            "with its rating for a sharper score."
        )
        rating = DEFAULT_RATING

    if platform_accounts:
        primary_source = max(
            platform_accounts, key=lambda p: float(p.get("weekly_payout") or 0.0)
        )
        primary_platform = classify_platform(primary_source.get("platform"))
    else:
        assumptions.append(
            f"No platforms connected; primary platform recorded as '{_DEFAULT_PLATFORM}'."
        )
        primary_platform = _DEFAULT_PLATFORM

    # --- Ledger-measured figures, which override declarations --------------- #
    weekly_totals = _weekly_payout_totals(transactions)
    measured_weekly = statistics.fmean(weekly_totals) if weekly_totals else 0.0

    if weekly_totals:
        average_weekly_payout = round(measured_weekly, 2)
    elif declared_weekly > 0:
        average_weekly_payout = round(declared_weekly, 2)
        assumptions.append(
            "Weekly payout is the figure declared when connecting platforms; no "
            "payouts have been logged yet to confirm it."
        )
    else:
        average_weekly_payout = 0.0
        assumptions.append("No income evidence at all; weekly payout recorded as zero.")

    measured_volatility = volatility_index(weekly_totals)
    if measured_volatility is None:
        assumptions.append(
            f"Fewer than {_MIN_WEEKS_FOR_VOLATILITY} weeks of payouts, so income "
            f"stability cannot be measured; {DEFAULT_VOLATILITY} assumed."
        )
        payout_volatility_index = DEFAULT_VOLATILITY
    else:
        payout_volatility_index = measured_volatility

    if declared_gigs > 0:
        gigs_per_week = int(min(declared_gigs, _MAX_GIGS_PER_WEEK))
    else:
        payout_count = sum(1 for r in transactions if r.get("transaction_type") == INCOME_TYPE)
        weeks = max(len(weekly_totals), 1)
        gigs_per_week = int(min(payout_count / weeks, _MAX_GIGS_PER_WEEK))
        if gigs_per_week == 0:
            assumptions.append("No gig count available; recorded as zero completed gigs a week.")

    if declared_hours > 0:
        hours_per_week = int(min(declared_hours, _MAX_HOURS_PER_WEEK))
    else:
        assumptions.append(
            f"No active hours recorded; {DEFAULT_HOURS_PER_WEEK} a week assumed."
        )
        hours_per_week = DEFAULT_HOURS_PER_WEEK

    return {
        "age": age,
        "primary_gig_platform": primary_platform,
        "platform_customer_rating": rating,
        "completed_gigs_per_week": gigs_per_week,
        "average_weekly_payout": average_weekly_payout,
        "payout_volatility_index": payout_volatility_index,
        "active_platform_hours_per_week": hours_per_week,
        "resilience_stash_balance": round(max(float(stash_balance), 0.0), 2),
        "connected_platforms": len(platform_accounts),
        "verified_platforms": sum(1 for p in platform_accounts if p.get("verified")),
        "assumptions": assumptions,
    }


def scoring_payload(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Strips the profile down to exactly the scoring service's request body."""
    return {
        key: profile[key]
        for key in (
            "age",
            "primary_gig_platform",
            "platform_customer_rating",
            "completed_gigs_per_week",
            "average_weekly_payout",
            "payout_volatility_index",
            "active_platform_hours_per_week",
            "resilience_stash_balance",
        )
    }


def demo() -> None:
    """Self-check: classification, the measured-beats-declared rule, and the defaults."""
    assert classify_platform("Swiggy Instamart") == "Food Delivery"
    assert classify_platform("Uber Driver") == "Ride-Hailing"
    assert classify_platform("Upwork") == "Freelance"
    assert classify_platform("Some New App") == "Other"
    assert classify_platform(None) == "Other"

    today = date(2026, 3, 15)
    assert age_from(date(2000, 3, 15), today) == 26
    assert age_from(date(2000, 3, 16), today) == 25  # birthday has not landed yet
    assert age_from(None, today) is None

    # Nothing on file: every feature is a default, and every default is named.
    bare = build(
        date_of_birth=None, platform_accounts=[], transactions=[], stash_balance=0, today=today
    )
    assert bare["age"] == DEFAULT_AGE
    assert bare["primary_gig_platform"] == "Other"
    assert bare["average_weekly_payout"] == 0.0
    assert len(bare["assumptions"]) >= 5

    payouts = [
        {"timestamp": "2026-02-02T10:00:00", "amount": 8000, "transaction_type": "platform_payout"},
        {"timestamp": "2026-02-09T10:00:00", "amount": 12000, "transaction_type": "platform_payout"},
        {"timestamp": "2026-02-16T10:00:00", "amount": 10000, "transaction_type": "platform_payout"},
        {"timestamp": "2026-02-20T10:00:00", "amount": 500, "transaction_type": "debit"},
    ]
    accounts = [
        {"platform": "Swiggy", "customer_rating": 4.8, "weekly_payout": 3000,
         "gigs_per_week": 40, "hours_per_week": 30, "verified": True},
        {"platform": "Uber", "customer_rating": 4.2, "weekly_payout": 1000,
         "gigs_per_week": 10, "hours_per_week": 12, "verified": False},
    ]

    profile = build(
        date_of_birth=date(1996, 1, 1),
        platform_accounts=accounts,
        transactions=payouts,
        stash_balance=15_000,
        today=today,
    )
    assert profile["age"] == 30
    # Swiggy earns more, so it -- not Uber -- names the primary category.
    assert profile["primary_gig_platform"] == "Food Delivery"
    # Payout-weighted rating sits nearer Swiggy's 4.8 than the plain mean of 4.5.
    assert 4.5 < profile["platform_customer_rating"] < 4.8
    # Measured weekly mean (10,000) beats the 4,000 declared on the forms.
    assert profile["average_weekly_payout"] == 10_000.0
    assert profile["completed_gigs_per_week"] == 50
    assert profile["active_platform_hours_per_week"] == 42
    assert profile["verified_platforms"] == 1
    assert 0 < profile["payout_volatility_index"] < 0.5

    # A gap week counts as a zero week, which must raise measured volatility.
    gappy = build(
        date_of_birth=date(1996, 1, 1),
        platform_accounts=accounts,
        transactions=[payouts[0], payouts[2]],
        stash_balance=0,
        today=today,
    )
    assert gappy["payout_volatility_index"] > profile["payout_volatility_index"]

    # Declared-only: no ledger, so the form figure is used and flagged as unconfirmed.
    declared = build(
        date_of_birth=date(1996, 1, 1),
        platform_accounts=accounts,
        transactions=[],
        stash_balance=0,
        today=today,
    )
    assert declared["average_weekly_payout"] == 4000.0
    assert any("declared" in note for note in declared["assumptions"])

    assert set(scoring_payload(profile)) == {
        "age", "primary_gig_platform", "platform_customer_rating", "completed_gigs_per_week",
        "average_weekly_payout", "payout_volatility_index", "active_platform_hours_per_week",
        "resilience_stash_balance",
    }

    print("income_profile.py self-check passed")


if __name__ == "__main__":
    demo()
