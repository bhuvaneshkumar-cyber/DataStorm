"""Emergency-loan eligibility: who may apply, for how much, over how long.

Pure functions over the scoring service's own risk assessment. Deliberately
derives nothing itself -- the ceiling, the tenor and the rate all come from the
assessment the scorer produced -- so the terms a worker is offered can never
disagree with the terms a lender sees on the same application.

The one number this module owns is the application threshold, and it defaults to
the same band boundary the scorer uses to separate Standard from Poor. Below it
an application is refused outright rather than accepted and then declined,
because a rejection recorded against someone's name is not a neutral event.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

# Matches ml_service's SCORE_STANDARD. Overridable, but moving it apart from the
# scorer's band means "eligible to apply" and "not automatically declined" stop
# lining up, so change both together.
APPLY_THRESHOLD = float(os.getenv("LOAN_APPLY_THRESHOLD", "400"))

# A decision the scorer will not stand behind is not an application we accept.
_BLOCKING_DECISIONS = frozenset({"DECLINE"})

# Floor on a usable advance. Below this the paperwork costs more than the money
# is worth to the borrower.
MIN_LOAN_AMOUNT = float(os.getenv("LOAN_MIN_AMOUNT", "1000"))


def evaluate(
    score: float,
    risk_assessment: Optional[Dict[str, Any]],
    requested_amount: Optional[float] = None,
    requested_tenor: Optional[int] = None,
) -> Dict[str, Any]:
    """Whether this applicant may borrow, and on what terms.

    `requested_amount` and `requested_tenor` are optional: with them the result
    answers "may I have this loan", without them it answers "what could I ask
    for", and the eligibility page uses the second form to fill in its limits.
    """
    assessment = risk_assessment or {}
    max_amount = float(assessment.get("max_credit_limit_inr") or 0.0)
    max_tenor = int(assessment.get("recommended_tenor_months") or 0)
    decision = assessment.get("decision")

    result: Dict[str, Any] = {
        "eligible": False,
        "credit_score": round(float(score), 2),
        "threshold": APPLY_THRESHOLD,
        "reason": "",
        "max_amount_inr": round(max_amount, 2),
        "max_tenor_months": max_tenor,
        "indicative_interest_rate_pct": assessment.get("indicative_interest_rate_pct"),
        "risk_grade": (assessment.get("risk_grade") or {}).get("code"),
    }

    if score < APPLY_THRESHOLD:
        result["reason"] = (
            f"An alternative credit score of at least {APPLY_THRESHOLD:.0f} is needed to "
            f"apply; yours is {score:.0f}. Building your Resilience Stash and logging "
            "payouts consistently are the two fastest ways to raise it."
        )
        return result

    if decision in _BLOCKING_DECISIONS:
        result["reason"] = (
            "The underwriting engine declines lending at this risk level, so an "
            "application cannot be accepted right now."
        )
        return result

    if max_amount < MIN_LOAN_AMOUNT:
        result["reason"] = (
            "Your assessed credit limit is below the minimum advance of "
            f"{MIN_LOAN_AMOUNT:.0f} rupees. More logged payout history will raise it."
        )
        return result

    if requested_amount is not None:
        if requested_amount > max_amount:
            result["reason"] = (
                f"You can borrow up to {max_amount:,.0f} rupees at your current score; "
                f"{requested_amount:,.0f} is above that ceiling."
            )
            return result
        if requested_amount < MIN_LOAN_AMOUNT:
            result["reason"] = f"The smallest advance is {MIN_LOAN_AMOUNT:.0f} rupees."
            return result

    if requested_tenor is not None and requested_tenor > max_tenor:
        result["reason"] = (
            f"The longest tenor at your risk grade is {max_tenor} months."
        )
        return result

    result["eligible"] = True
    result["reason"] = (
        f"Eligible to apply for up to {max_amount:,.0f} rupees over {max_tenor} months."
    )
    return result


def demo() -> None:
    """Self-check on each gate, including the ones that must refuse."""
    good = {
        "decision": "APPROVE",
        "max_credit_limit_inr": 120_000.0,
        "recommended_tenor_months": 24,
        "indicative_interest_rate_pct": 15.5,
        "risk_grade": {"code": "GS-1", "label": "Minimal Risk"},
    }

    open_ended = evaluate(700, good)
    assert open_ended["eligible"] and open_ended["max_amount_inr"] == 120_000.0
    assert open_ended["risk_grade"] == "GS-1"

    assert evaluate(700, good, requested_amount=50_000, requested_tenor=12)["eligible"]

    # Below the band boundary: refused before any request is even considered.
    low = evaluate(399, good, requested_amount=1_000)
    assert not low["eligible"] and "at least 400" in low["reason"]

    # Exactly at the threshold is eligible: the gate is "at least", not "above".
    assert evaluate(400, good)["eligible"]

    # The engine's own decline outranks a passing score.
    declined = evaluate(500, {**good, "decision": "DECLINE"})
    assert not declined["eligible"] and "declines lending" in declined["reason"]

    # Over the ceiling, and under the floor, both refuse with a usable message.
    assert not evaluate(700, good, requested_amount=500_000)["eligible"]
    assert not evaluate(700, good, requested_amount=100)["eligible"]
    assert not evaluate(700, good, requested_tenor=36)["eligible"]

    # A zero limit is a refusal, not an approval for nothing.
    assert not evaluate(700, {**good, "max_credit_limit_inr": 0.0})["eligible"]

    # A missing assessment must refuse rather than raise.
    assert not evaluate(700, None)["eligible"]

    print("loan_policy.py self-check passed")


if __name__ == "__main__":
    demo()
