"""Micro-insurance recommendations from a worker's risk profile and job type.

Lives in the scoring service, beside the risk policy it reasons about, rather
than in a separate insurance microservice. There is one risk model in this
system and this is where it lives; a second service would have to be handed the
same profile and would then own a second, quietly diverging opinion of it.

The output is advice, not a product. Nothing here binds cover, quotes a real
premium or names an insurer -- it ranks the *kinds* of protection a person's
actual exposure argues for, and says why each one placed where it did.

Deterministic and rule-based on purpose. "Why was accident cover ranked first"
is a question a worker deserves a straight answer to, and every rank here comes
with the sentence that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import config

# Exposure profile per job family. `road` is time spent in traffic, `physical`
# is bodily risk from the work itself, `asset` is dependence on a vehicle or
# equipment whose loss stops income immediately.
_EMPLOYMENT_EXPOSURE: Dict[str, Dict[str, float]] = {
    "ride-hailing": {"road": 1.0, "physical": 0.7, "asset": 1.0},
    "food delivery": {"road": 1.0, "physical": 0.6, "asset": 0.9},
    "delivery": {"road": 0.9, "physical": 0.6, "asset": 0.8},
    "driver": {"road": 1.0, "physical": 0.6, "asset": 1.0},
    "courier": {"road": 0.9, "physical": 0.6, "asset": 0.8},
    "construction": {"road": 0.2, "physical": 1.0, "asset": 0.3},
    "domestic": {"road": 0.2, "physical": 0.5, "asset": 0.1},
    # Asset exposure here is a laptop or a camera, not a vehicle: replaceable at
    # a cost that hurts rather than one that ends the income entirely.
    "freelance": {"road": 0.1, "physical": 0.2, "asset": 0.35},
    "consultant": {"road": 0.1, "physical": 0.2, "asset": 0.35},
    "other": {"road": 0.4, "physical": 0.4, "asset": 0.4},
}
_DEFAULT_EXPOSURE = _EMPLOYMENT_EXPOSURE["other"]

# Premium is expressed as a share of weekly earnings rather than in rupees.
# A flat "₹300 a month" means something very different to a worker earning
# 4,000 a week than to one earning 15,000, and the affordability question is
# the one that actually decides whether cover is taken up.
_PREMIUM_BAND_PCT: Dict[str, Tuple[float, float]] = {
    "personal_accident": (0.3, 0.8),
    "health_hospitalisation": (1.2, 2.5),
    "income_protection": (1.0, 2.0),
    "asset_vehicle": (0.8, 1.8),
    "term_life": (0.5, 1.2),
}

# Weeks of stash below which a hospital bill or an idle week becomes a crisis
# rather than an inconvenience. Matches the covenant threshold in risk_policy.
_THIN_RUNWAY_WEEKS = 2.0
_BURNOUT_HOURS = 60
_VOLATILE_INCOME = 0.35
_OLDER_WORKER_AGE = 45

# A recommendation below this is not shown: a ranked list where everything is
# "recommended" tells a worker nothing about where to start.
_MIN_PRIORITY = 0.25


@dataclass(frozen=True)
class CoverType:
    """One kind of protection, and what makes it more or less urgent."""

    code: str
    title: str
    description: str


_COVERS: Sequence[CoverType] = (
    CoverType(
        "personal_accident",
        "Personal accident cover",
        "Pays a lump sum for death or permanent disability from an accident, and a "
        "weekly amount while you cannot work. The cheapest cover per rupee of "
        "protection for anyone who earns on the road.",
    ),
    CoverType(
        "health_hospitalisation",
        "Health and hospitalisation cover",
        "Pays hospital bills directly so a medical event does not have to be funded "
        "out of savings or, more often, out of a moneylender's loan.",
    ),
    CoverType(
        "income_protection",
        "Income protection",
        "Replaces part of your weekly earnings during an illness or injury that keeps "
        "you off the platform. The gap this fills is the one a savings buffer covers "
        "for a week and cannot cover for a month.",
    ),
    CoverType(
        "asset_vehicle",
        "Vehicle and equipment cover",
        "Repairs or replaces the vehicle or equipment you earn with. Without it, one "
        "breakdown stops your income and your repayments at the same time.",
    ),
    CoverType(
        "term_life",
        "Term life cover",
        "Pays your family a fixed sum if you die during the term. Cheap while you are "
        "young, and the only cover here that is about someone other than you.",
    ),
)


def _exposure_for(employment_type: Optional[str]) -> Tuple[Dict[str, float], str]:
    """Matches a free-text job description to an exposure profile.

    Substring matching rather than exact lookup: people write "Swiggy delivery
    partner" and "part-time driver", not the label a dropdown would have given.
    """
    lowered = (employment_type or "").strip().lower()
    if lowered:
        for key, exposure in _EMPLOYMENT_EXPOSURE.items():
            if key in lowered:
                return exposure, key
    return _DEFAULT_EXPOSURE, "other"


def recommend(
    credit_score: float,
    employment_type: Optional[str],
    average_weekly_payout: float = 0.0,
    resilience_stash_balance: float = 0.0,
    active_platform_hours_per_week: int = 40,
    payout_volatility_index: float = 0.5,
    age: int = 30,
    risk_tier: Optional[str] = None,
) -> Dict[str, Any]:
    """Ranks cover types for one worker, with the reason behind each rank."""
    exposure, matched = _exposure_for(employment_type)
    weekly = max(float(average_weekly_payout), 0.0)
    runway_weeks = resilience_stash_balance / weekly if weekly > 0 else 0.0

    tier = risk_tier or _tier_from(credit_score)
    # A weak score is not a reason to sell more insurance -- it is a signal that
    # this person has the least capacity to absorb a shock unaided, which is
    # exactly what cover is for.
    fragility = {"LOW": 0.0, "MODERATE": 0.15, "HIGH": 0.3, "VERY_HIGH": 0.45}.get(tier, 0.3)

    thin_buffer = runway_weeks < _THIN_RUNWAY_WEEKS
    long_hours = active_platform_hours_per_week > _BURNOUT_HOURS
    erratic = payout_volatility_index > _VOLATILE_INCOME

    scores: Dict[str, Tuple[float, List[str]]] = {
        "personal_accident": (
            0.45 + exposure["road"] * 0.35 + exposure["physical"] * 0.15 + fragility * 0.3,
            _reasons(
                (exposure["road"] >= 0.8, "You earn on the road, where injury risk is highest."),
                (exposure["physical"] >= 0.8, "Your work carries a high risk of physical injury."),
                (thin_buffer, "Your savings buffer would not cover a month off work."),
            ),
        ),
        "health_hospitalisation": (
            # The highest floor of any cover here. Hospitalisation is the shock
            # that most reliably turns into debt in India, and it does so
            # regardless of what a person does for a living.
            0.45 + fragility * 0.5 + (0.2 if thin_buffer else 0.0) + (0.15 if age >= _OLDER_WORKER_AGE else 0.0),
            _reasons(
                (thin_buffer, "A hospital bill would have to come out of borrowing, not savings."),
                (age >= _OLDER_WORKER_AGE, "Premiums rise steeply from here; locking in now costs less."),
                (fragility >= 0.3, "Your risk profile leaves little room to absorb a medical shock."),
            ),
        ),
        "income_protection": (
            0.25 + (0.35 if erratic else 0.0) + (0.25 if thin_buffer else 0.0)
            + (0.2 if long_hours else 0.0) + fragility * 0.2,
            _reasons(
                (erratic, "Your week-to-week income already swings; an injury would compound it."),
                (long_hours, f"{active_platform_hours_per_week} hours a week is not sustainable indefinitely."),
                (thin_buffer, "Nothing else would replace your earnings during a long absence."),
            ),
        ),
        "asset_vehicle": (
            0.2 + exposure["asset"] * 0.5 + (0.15 if thin_buffer else 0.0),
            _reasons(
                (exposure["asset"] >= 0.8, "Your income stops the day your vehicle does."),
                (thin_buffer, "A repair bill would have to be borrowed rather than paid."),
            ),
        ),
        "term_life": (
            0.2 + (0.25 if age < _OLDER_WORKER_AGE else 0.1) + exposure["road"] * 0.15 + fragility * 0.1,
            _reasons(
                (age < _OLDER_WORKER_AGE, "Term cover is at its cheapest at your age."),
                (exposure["road"] >= 0.8, "Road work raises the risk this cover exists for."),
            ),
        ),
    }

    covers = {cover.code: cover for cover in _COVERS}
    ranked = []
    for code, (raw, reasons) in scores.items():
        priority = round(min(max(raw, 0.0), 1.0), 3)
        if priority < _MIN_PRIORITY:
            continue
        low, high = _PREMIUM_BAND_PCT[code]
        ranked.append(
            {
                "code": code,
                "title": covers[code].title,
                "description": covers[code].description,
                "priority": priority,
                "urgency": _urgency(priority),
                "reasons": reasons or ["A baseline protection worth holding at any risk level."],
                "indicative_monthly_premium_inr": _premium_band(weekly, low, high),
                "premium_pct_of_weekly_payout": [low, high],
            }
        )

    ranked.sort(key=lambda item: item["priority"], reverse=True)

    return {
        "employment_type": employment_type,
        "matched_exposure_profile": matched,
        "risk_tier": tier,
        "credit_score": round(float(credit_score), 2),
        "savings_runway_weeks": round(runway_weeks, 2),
        "recommendations": ranked,
        "notes": [
            "Guidance from your risk profile, not a quote. No policy is issued and no "
            "premium is collected here.",
            "Premium ranges are indicative shares of your weekly earnings; an insurer's "
            "actual price will depend on your age, health and sum assured.",
        ]
        + (
            [
                "Your savings buffer covers under two weeks of earnings. Building that "
                "buffer protects against small shocks more cheaply than any policy; "
                "insurance is for the shocks a buffer cannot absorb."
            ]
            if thin_buffer
            else []
        ),
    }


def _reasons(*conditions: Tuple[bool, str]) -> List[str]:
    """Keeps only the reasons that actually apply to this worker."""
    return [reason for applies, reason in conditions if applies]


def _tier_from(score: float) -> str:
    """Same boundaries as risk_policy, so the two never disagree about a score."""
    if score >= config.SCORE_EXCELLENT:
        return "LOW"
    if score >= config.SCORE_GOOD:
        return "MODERATE"
    if score >= config.SCORE_STANDARD:
        return "HIGH"
    return "VERY_HIGH"


def _urgency(priority: float) -> str:
    if priority >= 0.75:
        return "essential"
    if priority >= 0.5:
        return "recommended"
    return "optional"


def _premium_band(weekly_payout: float, low_pct: float, high_pct: float) -> Optional[List[float]]:
    """Monthly premium range in rupees, or None when earnings are unknown.

    None rather than zero: a zero premium reads as free cover, and "we cannot
    price this until you log some income" is the honest answer.
    """
    if weekly_payout <= 0:
        return None
    monthly = weekly_payout * config.WEEKS_PER_MONTH
    return [round(monthly * low_pct / 100, 2), round(monthly * high_pct / 100, 2)]


def demo() -> None:
    """Self-check: exposure routing, ordering, and the honest-unknown cases."""
    rider = recommend(
        credit_score=430,
        employment_type="Swiggy delivery partner",
        average_weekly_payout=8_000,
        resilience_stash_balance=4_000,
        active_platform_hours_per_week=68,
        payout_volatility_index=0.45,
        age=27,
    )
    # "swiggy delivery partner" contains "delivery" but not "food delivery", so
    # the broader profile is the one that matches -- which is the intent: an
    # unrecognised brand name should still land on a sensible exposure.
    assert rider["matched_exposure_profile"] == "delivery"
    # The scoring service's own platform category matches the specific profile.
    assert (
        recommend(credit_score=500, employment_type="Food Delivery")[
            "matched_exposure_profile"
        ]
        == "food delivery"
    )
    assert rider["risk_tier"] == "HIGH"
    assert rider["savings_runway_weeks"] == 0.5

    ranked = rider["recommendations"]
    assert ranked, "a road worker must be offered something"
    assert all(a["priority"] >= b["priority"] for a, b in zip(ranked, ranked[1:]))

    by_code = {item["code"]: item for item in ranked}
    top_two = [item["code"] for item in ranked[:2]]
    # Accident and income protection are the two exposures this rider actually
    # carries -- erratic pay and 68-hour weeks on the road -- so both lead, and
    # which of them edges ahead is a tuning question rather than a contract.
    assert set(top_two) == {"personal_accident", "income_protection"}, top_two
    assert all(item["urgency"] == "essential" for item in ranked[:2])
    assert any("road" in reason for reason in by_code["personal_accident"]["reasons"])
    assert any("swings" in reason for reason in by_code["income_protection"]["reasons"])
    assert any("68 hours" in reason for reason in by_code["income_protection"]["reasons"])
    # A thin buffer is called out as a cheaper fix than a policy.
    assert any("buffer" in note for note in rider["notes"])

    # Every recommendation is priced against real earnings.
    for item in ranked:
        assert item["indicative_monthly_premium_inr"] is not None
        low, high = item["indicative_monthly_premium_inr"]
        assert 0 < low < high

    # A desk freelancer's exposure is different, so the ranking is too.
    freelancer = recommend(
        credit_score=700,
        employment_type="Freelance designer",
        average_weekly_payout=15_000,
        resilience_stash_balance=90_000,
        active_platform_hours_per_week=35,
        payout_volatility_index=0.12,
        age=34,
    )
    assert freelancer["matched_exposure_profile"] == "freelance"
    assert freelancer["risk_tier"] == "LOW"
    codes = [item["code"] for item in freelancer["recommendations"]]
    # Vehicle cover should not outrank health for someone who does not drive.
    assert codes.index("health_hospitalisation") < codes.index("asset_vehicle")
    # A well-buffered worker is not lectured about their buffer.
    assert not any("buffer" in note for note in freelancer["notes"])

    # An unknown job still gets advice, from the neutral exposure profile.
    unknown = recommend(credit_score=500, employment_type=None, average_weekly_payout=5_000)
    assert unknown["matched_exposure_profile"] == "other"
    assert unknown["recommendations"]

    # No income logged: advice still ranks, but nothing is priced.
    unpriced = recommend(credit_score=500, employment_type="driver", average_weekly_payout=0)
    assert unpriced["savings_runway_weeks"] == 0.0
    assert all(
        item["indicative_monthly_premium_inr"] is None for item in unpriced["recommendations"]
    )

    # Tier boundaries agree with the scoring bands rather than restating them.
    assert _tier_from(config.SCORE_EXCELLENT) == "LOW"
    assert _tier_from(config.SCORE_GOOD) == "MODERATE"
    assert _tier_from(config.SCORE_STANDARD) == "HIGH"
    assert _tier_from(config.SCORE_STANDARD - 1) == "VERY_HIGH"

    print("insurance_advisor.py self-check passed")


if __name__ == "__main__":
    demo()
