"""Cash-flow aggregation for the expense tracker. Pure functions over rows.

Aggregating server-side rather than in the browser is what keeps the expense
tracker, the tax estimate and the credit path quoting the same numbers: they all
read these functions instead of each re-summing a list of transactions their own
way.

No database types appear here -- the input is plain dicts shaped like
`db_service.get_transactions` output -- so the arithmetic is testable on its own.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence

INCOME_TYPE = "platform_payout"
EXPENSE_TYPE = "debit"

# Shown when a row carries no category of its own. A literal rather than None so
# it groups and sorts like any other bucket instead of needing a special case.
UNCATEGORISED = "Uncategorised"


def parse_timestamp(value: object) -> Optional[datetime]:
    """Accepts the ISO strings the API emits and the datetimes the ORM holds."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _bucket(rows: Sequence[dict], key) -> List[dict]:
    """Sums income and expense per bucket, in ascending key order.

    Buckets with only expenses and buckets with only income both appear: a chart
    that silently drops a zero-income day draws a cash-flow line that never
    happened.
    """
    income: Dict[str, float] = defaultdict(float)
    expense: Dict[str, float] = defaultdict(float)

    for row in rows:
        stamp = parse_timestamp(row.get("timestamp"))
        if stamp is None:
            continue
        bucket = key(stamp)
        amount = abs(float(row.get("amount") or 0.0))
        if row.get("transaction_type") == INCOME_TYPE:
            income[bucket] += amount
        elif row.get("transaction_type") == EXPENSE_TYPE:
            expense[bucket] += amount

    return [
        {
            "period": period,
            "income": round(income[period], 2),
            "expense": round(expense[period], 2),
            "net": round(income[period] - expense[period], 2),
        }
        for period in sorted(set(income) | set(expense))
    ]


def _totals_by_category(rows: Sequence[dict], transaction_type: str) -> List[dict]:
    """Category split for one side of the ledger, largest share first."""
    totals: Dict[str, float] = defaultdict(float)
    for row in rows:
        if row.get("transaction_type") != transaction_type:
            continue
        label = (row.get("category") or row.get("merchant") or UNCATEGORISED).strip()
        totals[label or UNCATEGORISED] += abs(float(row.get("amount") or 0.0))

    grand = sum(totals.values())
    return sorted(
        (
            {
                "category": label,
                "total": round(amount, 2),
                # Guarded: an all-zero ledger is possible and must not divide by zero.
                "share_pct": round(amount / grand * 100, 2) if grand else 0.0,
            }
            for label, amount in totals.items()
        ),
        key=lambda item: item["total"],
        reverse=True,
    )


def within_window(rows: Iterable[dict], window_days: int, today: Optional[date] = None) -> List[dict]:
    """Rows timestamped within the last `window_days`, undated rows excluded.

    An undated row cannot be placed on a time axis, so counting it in the totals
    while omitting it from the chart would make the two disagree.
    """
    cutoff = datetime.combine((today or date.today()) - timedelta(days=window_days), datetime.min.time())
    kept = []
    for row in rows:
        stamp = parse_timestamp(row.get("timestamp"))
        if stamp is not None and stamp >= cutoff:
            kept.append(row)
    return kept


def summarise(rows: Sequence[dict], window_days: int = 90, today: Optional[date] = None) -> dict:
    """Everything the expense tracker charts, from one pass over the rows."""
    scoped = within_window(rows, window_days, today)

    total_income = round(
        sum(abs(float(r.get("amount") or 0.0)) for r in scoped if r.get("transaction_type") == INCOME_TYPE),
        2,
    )
    total_expense = round(
        sum(abs(float(r.get("amount") or 0.0)) for r in scoped if r.get("transaction_type") == EXPENSE_TYPE),
        2,
    )

    return {
        "window_days": window_days,
        "total_income": total_income,
        "total_expense": total_expense,
        "net": round(total_income - total_expense, 2),
        "daily": _bucket(scoped, lambda stamp: stamp.date().isoformat()),
        "monthly": _bucket(scoped, lambda stamp: stamp.strftime("%Y-%m")),
        "expense_categories": _totals_by_category(scoped, EXPENSE_TYPE),
        "income_sources": _totals_by_category(scoped, INCOME_TYPE),
        "transaction_count": len(scoped),
    }


def observed_days(rows: Sequence[dict], today: Optional[date] = None) -> int:
    """Days from the oldest dated row to today, at least one.

    This is what turns a partial history into an annual figure in the tax
    estimate, so it counts elapsed calendar days rather than the number of rows:
    a worker who logged three payouts across two months has observed two months,
    not three days.
    """
    stamps = [s for s in (parse_timestamp(r.get("timestamp")) for r in rows) if s is not None]
    if not stamps:
        return 1
    return max((today or date.today()) - min(stamps).date(), timedelta(days=1)).days or 1


def to_ledger(rows: Sequence[dict]) -> List[dict]:
    """Reshapes stored transactions into the scoring service's ledger contract.

    One conversion, used by both the credit page and the metric breakdown, so
    the two can never disagree about what a stored row means.
    """
    ledger: List[dict] = []
    for row in rows:
        stamp = parse_timestamp(row.get("timestamp"))
        if stamp is None:
            continue
        is_income = row.get("transaction_type") == INCOME_TYPE
        ledger.append(
            {
                "date": stamp.date().isoformat(),
                "type": "credit" if is_income else "debit",
                "amount": abs(float(row.get("amount") or 0.0)),
                "category": row.get("category") or row.get("merchant"),
                "source": "platform" if is_income else "bank",
                "description": row.get("merchant"),
            }
        )
    return ledger


def demo() -> None:
    """Self-check on the bucketing, the shares, and the empty-ledger guards."""
    today = date(2026, 3, 15)
    rows = [
        {"timestamp": "2026-03-15T09:00:00", "amount": 900, "transaction_type": "platform_payout", "category": "Swiggy"},
        {"timestamp": "2026-03-15T20:00:00", "amount": 132, "transaction_type": "debit", "category": "Fuel"},
        {"timestamp": "2026-02-10T11:00:00", "amount": 1100, "transaction_type": "platform_payout", "category": "Uber"},
        {"timestamp": "2026-02-10T13:00:00", "amount": 68, "transaction_type": "debit", "merchant": "Chai stall"},
        {"timestamp": None, "amount": 500, "transaction_type": "debit", "category": "Rent"},
        {"timestamp": "2020-01-01T00:00:00", "amount": 9999, "transaction_type": "debit", "category": "Ancient"},
    ]

    summary = summarise(rows, window_days=90, today=today)
    # The undated row and the six-year-old row are both out of the window.
    assert summary["transaction_count"] == 4
    assert summary["total_income"] == 2000.0
    assert summary["total_expense"] == 200.0
    assert summary["net"] == 1800.0

    assert [d["period"] for d in summary["daily"]] == ["2026-02-10", "2026-03-15"]
    assert [m["period"] for m in summary["monthly"]] == ["2026-02", "2026-03"]
    assert summary["monthly"][1]["net"] == round(900 - 132, 2)

    # A row with no category falls back to its merchant, then to the literal.
    expense_labels = [c["category"] for c in summary["expense_categories"]]
    assert expense_labels == ["Fuel", "Chai stall"], expense_labels
    assert abs(sum(c["share_pct"] for c in summary["expense_categories"]) - 100.0) < 0.01

    # Empty input must produce a valid, all-zero summary rather than raising.
    empty = summarise([], window_days=30, today=today)
    assert empty["total_income"] == 0.0 and empty["daily"] == []
    assert observed_days([], today=today) == 1

    # Elapsed days, not row count.
    assert observed_days(rows[:4], today=today) == 33

    ledger = to_ledger(rows)
    assert len(ledger) == 5  # the undated row cannot be placed on a date axis
    assert ledger[0] == {
        "date": "2026-03-15",
        "type": "credit",
        "amount": 900.0,
        "category": "Swiggy",
        "source": "platform",
        "description": None,
    }

    print("analytics.py self-check passed")


if __name__ == "__main__":
    demo()
