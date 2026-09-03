"""Indian income-tax estimation for gig income. Pure functions, no I/O.

Scoped deliberately to the situation this product's users are actually in: an
individual under 60, resident, earning from gig platforms, taxed under the
default new regime, and eligible for presumptive taxation under section 44AD
because platform earnings arrive digitally.

What that scope buys is an estimate that is honest about being one. What it
excludes -- old regime, capital gains, house property, foreign income,
partnership income, senior-citizen slabs -- is excluded loudly in `notes`
rather than silently mis-computed.

ponytail: slabs as a constant table. Move to a per-FY lookup the first time two
financial years need to be estimable at once.
"""

from __future__ import annotations

from datetime import date
from typing import List, Sequence, Tuple

# --------------------------------------------------------------------------- #
# Statute
# --------------------------------------------------------------------------- #

# New-regime slabs for FY 2025-26 (Finance Act 2025), as (upper bound, rate).
# `None` is the open-ended top band. Ordered low to high; the walk below relies
# on that ordering, so a new band must be inserted in place, not appended.
_SLABS: Sequence[Tuple[float | None, float]] = (
    (400_000.0, 0.0),
    (800_000.0, 0.05),
    (1_200_000.0, 0.10),
    (1_600_000.0, 0.15),
    (2_000_000.0, 0.20),
    (2_400_000.0, 0.25),
    (None, 0.30),
)

# Section 87A: full rebate for total income at or below the ceiling, capped at
# the stated amount. This is what makes income up to 12 lakh tax-free.
_REBATE_INCOME_CEILING = 1_200_000.0
_REBATE_MAX = 60_000.0

# Health and education cess, applied to tax plus surcharge.
_CESS_RATE = 0.04

# Surcharge on tax, by total income. New regime caps the top rate at 25%.
_SURCHARGE_BANDS: Sequence[Tuple[float, float]] = (
    (20_000_000.0, 0.25),
    (10_000_000.0, 0.15),
    (5_000_000.0, 0.10),
)

# Section 44AD presumptive business income: 6% of turnover received digitally.
# Gig platform payouts are bank/UPI credits, so the digital rate is the one that
# applies rather than the 8% cash rate.
_PRESUMPTIVE_RATE_DIGITAL = 0.06
_PRESUMPTIVE_TURNOVER_LIMIT = 30_000_000.0

# Aggregate turnover above which GST registration is mandatory for a service
# provider outside the special-category states.
_GST_SERVICE_THRESHOLD = 2_000_000.0

DAYS_PER_YEAR = 365


def financial_year(on: date | None = None) -> str:
    """Indian FY label for a date, e.g. '2025-26'. The FY starts on 1 April."""
    today = on or date.today()
    start = today.year if today.month >= 4 else today.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def slab_breakdown(taxable_income: float) -> List[dict]:
    """Tax due in each slab. Returns every band, including the ones taxed at nil.

    Showing empty bands too is the point: a person seeing "0 to 4,00,000 -- nil"
    understands the shape of the calculation in a way a list of only the bands
    they crossed does not convey.
    """
    income = max(taxable_income, 0.0)
    rows: List[dict] = []
    floor = 0.0

    for ceiling, rate in _SLABS:
        upper = income if ceiling is None else min(income, ceiling)
        in_band = max(upper - floor, 0.0)
        rows.append(
            {
                "band": _band_label(floor, ceiling),
                "rate_pct": round(rate * 100, 2),
                "taxable_in_band": round(in_band, 2),
                "tax": round(in_band * rate, 2),
            }
        )
        if ceiling is None:
            break
        floor = ceiling

    return rows


def _band_label(floor: float, ceiling: float | None) -> str:
    if ceiling is None:
        return f"Above {_lakh(floor)}"
    return f"{_lakh(floor)} to {_lakh(ceiling)}"


def _lakh(amount: float) -> str:
    """Renders a rupee bound the way Indian tax tables do."""
    if amount == 0:
        return "0"
    if amount >= 10_000_000:
        return f"{amount / 10_000_000:g} crore"
    return f"{amount / 100_000:g} lakh"


def _surcharge_rate(total_income: float) -> float:
    for floor, rate in _SURCHARGE_BANDS:
        if total_income > floor:
            return rate
    return 0.0


def estimate(
    gross_income_observed: float,
    observed_days: int,
    deductions: float = 0.0,
    use_presumptive: bool = True,
    today: date | None = None,
) -> dict:
    """Annualises observed income and estimates the tax on it.

    `observed_days` is what turns a few weeks of logged payouts into an annual
    figure. It is clamped to at least one day so a same-day account cannot
    divide by zero, and never above a year so a long history is reported as
    itself rather than being scaled down.
    """
    days = max(int(observed_days), 1)
    gross = max(float(gross_income_observed), 0.0)
    annualised = gross * DAYS_PER_YEAR / days if days < DAYS_PER_YEAR else gross

    notes: List[str] = [
        "An estimate from the income logged in this app, not a filing and not tax advice.",
        "Assumes a resident individual under 60 taxed under the default new regime.",
    ]

    if days < DAYS_PER_YEAR:
        notes.append(
            f"Annualised from {days} day(s) of logged income. The estimate sharpens "
            "as more of the year is recorded."
        )

    # Section 44AD replaces itemised expenses with a deemed profit, so the two
    # cannot both be claimed. Presumptive is the default because it is almost
    # always the lower liability for a worker without heavy documented costs.
    presumptive_deduction = 0.0
    if use_presumptive and annualised <= _PRESUMPTIVE_TURNOVER_LIMIT:
        presumptive_deduction = round(annualised * (1 - _PRESUMPTIVE_RATE_DIGITAL), 2)
        taxable_base = annualised - presumptive_deduction
        claimed_deductions = 0.0
        notes.append(
            "Presumptive taxation under section 44AD: 6% of digitally received "
            "turnover is treated as profit, so expenses are not itemised separately."
        )
    else:
        taxable_base = annualised
        claimed_deductions = min(max(float(deductions), 0.0), annualised)
        taxable_base -= claimed_deductions
        if use_presumptive:
            notes.append(
                "Turnover exceeds the section 44AD limit, so presumptive taxation "
                "does not apply and books must be maintained."
            )

    taxable_income = round(max(taxable_base, 0.0), 2)
    slabs = slab_breakdown(taxable_income)
    tax_before_rebate = round(sum(row["tax"] for row in slabs), 2)

    rebate = (
        round(min(tax_before_rebate, _REBATE_MAX), 2)
        if taxable_income <= _REBATE_INCOME_CEILING
        else 0.0
    )
    tax_after_rebate = max(tax_before_rebate - rebate, 0.0)

    surcharge = round(tax_after_rebate * _surcharge_rate(taxable_income), 2)
    cess = round((tax_after_rebate + surcharge) * _CESS_RATE, 2)
    total_tax = round(tax_after_rebate + surcharge + cess, 2)

    if rebate > 0 and total_tax == 0:
        notes.append(
            "The section 87A rebate cancels the liability entirely at this income level."
        )

    gst_required = annualised > _GST_SERVICE_THRESHOLD
    if gst_required:
        notes.append(
            "Annualised turnover is above the 20 lakh services threshold, so GST "
            "registration is mandatory."
        )

    notes.append(
        "Advance tax under section 44AD is payable in a single instalment by 15 March."
        if presumptive_deduction > 0
        else "Advance tax is payable in four instalments: 15 Jun, 15 Sep, 15 Dec, 15 Mar."
    )

    return {
        "financial_year": financial_year(today),
        "regime": "New regime (default)",
        "observed_days": days,
        "gross_income_observed": round(gross, 2),
        "annualised_gross_income": round(annualised, 2),
        "presumptive_deduction": presumptive_deduction,
        "deductions_claimed": round(claimed_deductions, 2),
        "taxable_income": taxable_income,
        "slabs": slabs,
        "tax_before_rebate": tax_before_rebate,
        "rebate": rebate,
        "surcharge": surcharge,
        "cess": cess,
        "total_tax": total_tax,
        "effective_rate_pct": round(total_tax / annualised * 100, 2) if annualised else 0.0,
        "monthly_set_aside": round(total_tax / 12, 2),
        "gst_registration_required": gst_required,
        "notes": notes,
    }


def demo() -> None:
    """Self-check on the boundaries where an arithmetic slip changes a number."""
    assert financial_year(date(2026, 3, 31)) == "2025-26"
    assert financial_year(date(2026, 4, 1)) == "2026-27"

    # Nothing earned, nothing owed, and no division by zero on day zero.
    zero = estimate(0.0, 0)
    assert zero["total_tax"] == 0.0 and zero["effective_rate_pct"] == 0.0

    # 30 days of 50k annualises to ~608k turnover; 44AD deems 6% profit, well
    # under the rebate ceiling, so nothing is payable.
    small = estimate(50_000.0, 30)
    assert small["annualised_gross_income"] > 600_000
    assert small["total_tax"] == 0.0

    # Without the presumptive deduction the same turnover is taxed in full and
    # still clears the rebate ceiling, so it stays nil -- but the taxable base moves.
    itemised = estimate(50_000.0, 30, use_presumptive=False)
    assert itemised["taxable_income"] > small["taxable_income"]

    # A full year of income taxed directly, above the rebate ceiling.
    big = estimate(2_000_000.0, 365, use_presumptive=False)
    # 0 on the first 4L, 5% of 4L = 20k, 10% of 4L = 40k, 15% of 4L = 60k, 20% of 4L = 80k.
    assert big["tax_before_rebate"] == 200_000.0
    assert big["rebate"] == 0.0
    assert big["cess"] == 8_000.0
    assert big["total_tax"] == 208_000.0
    # The GST threshold is a strict "exceeds": exactly 20 lakh does not trigger it.
    assert not big["gst_registration_required"]
    assert estimate(2_000_001.0, 365, use_presumptive=False)["gst_registration_required"]

    # Slab bands must partition the income exactly, with no gap and no overlap.
    assert abs(sum(r["taxable_in_band"] for r in big["slabs"]) - big["taxable_income"]) < 0.01

    # A history longer than a year is reported as itself, not scaled down.
    long_history = estimate(1_000_000.0, 900)
    assert long_history["annualised_gross_income"] == 1_000_000.0

    print("tax_rules.py self-check passed")


if __name__ == "__main__":
    demo()
