"""Checks for the transaction-driven metric engine and its endpoints.

Run with: .venv_ml\\Scripts\\python -m pytest ml_service -q
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import config
import credit_metrics as cm
import main
import metric_definitions as md


def ledger(
    months: int = 6,
    weekly_payout: float = 9000.0,
    payout_jitter: float = 0.0,
    days_per_month: int = 20,
    monthly_rent: float = 8000.0,
    start: date = date(2026, 1, 1),
) -> list[cm.Transaction]:
    """A synthetic but realistic gig ledger: frequent payouts, monthly rent."""
    rows: list[cm.Transaction] = []
    for month in range(months):
        anchor = date(start.year + (start.month - 1 + month) // 12,
                      (start.month - 1 + month) % 12 + 1, 1)
        per_day = weekly_payout / 7.0
        for day in range(days_per_month):
            drift = 1.0 + (payout_jitter if month % 2 else -payout_jitter)
            rows.append(
                cm.Transaction(
                    anchor + timedelta(days=day), "credit", per_day * drift, "swiggy", "platform"
                )
            )
        rows.append(cm.Transaction(anchor + timedelta(days=4), "debit", monthly_rent, "rent", "manual"))
    return rows


# --------------------------------------------------------------------------- #
# Definitions
# --------------------------------------------------------------------------- #


def test_metric_definitions_are_structurally_sound():
    """Weights that do not sum to 100, or bands out of order, silently produce
    wrong scores with no runtime error. This is the only thing that catches it."""
    assert md.validate_definitions() == []


def test_bands_are_contiguous_so_no_value_falls_through():
    """The source engine used {min,max} pairs with gaps: a volatility of 0.155
    matched no band and fell through to the *worst* one. Ordered upper bounds
    make that impossible - every value in every metric must score."""
    for name, spec in md.ALL_METRICS.items():
        probes = [-1e9, 0, 0.155, 1, 2.5, 47, 100, 1e9]
        for probe in probes:
            score, status = md.score_from_bands(probe, spec.bands)
            assert isinstance(status, str) and status, (name, probe)
            assert 0 <= score <= 100, (name, probe, score)

    # The specific value that broke the original.
    score, status = md.score_from_bands(0.155, md.INCOME_METRICS["income_volatility"].bands)
    assert status == "Stable" and score == 80


# --------------------------------------------------------------------------- #
# Metric behaviour
# --------------------------------------------------------------------------- #


def test_steady_earner_outscores_erratic_one():
    steady = cm.analyze(ledger(payout_jitter=0.0))
    erratic = cm.analyze(ledger(payout_jitter=0.6))
    assert steady["credit_score"] > erratic["credit_score"], (steady, erratic)
    assert (
        steady["metrics"]["income_volatility"]["score"]
        > erratic["metrics"]["income_volatility"]["score"]
    )


def test_saver_outscores_overspender():
    saver = cm.analyze(ledger(monthly_rent=8_000))
    spender = cm.analyze(ledger(monthly_rent=25_000))
    assert saver["category_scores"]["spending_behavior"] > spender["category_scores"]["spending_behavior"]
    assert spender["metrics"]["net_cash_flow_ratio"]["value"] < saver["metrics"]["net_cash_flow_ratio"]["value"]


def test_score_stays_inside_the_service_scale():
    for rows in (ledger(months=1, days_per_month=1), ledger(months=12, weekly_payout=60_000)):
        result = cm.analyze(rows)
        assert config.MIN_SCORE <= result["credit_score"] <= config.MAX_SCORE


def test_diversification_counts_distinct_sources():
    single = ledger(months=3)
    mixed = single + [
        cm.Transaction(date(2026, 2, day), "credit", 3000, platform, "platform")
        for day, platform in ((2, "uber"), (9, "upwork"), (16, "zomato"))
    ]
    assert (
        cm.analyze(mixed)["metrics"]["income_diversification"]["value"]
        > cm.analyze(single)["metrics"]["income_diversification"]["value"]
    )


def test_work_stability_measures_the_longest_drought():
    rows = [
        cm.Transaction(date(2026, 1, 1), "credit", 5000, "uber", "platform"),
        cm.Transaction(date(2026, 1, 3), "credit", 5000, "uber", "platform"),
        cm.Transaction(date(2026, 3, 1), "credit", 5000, "uber", "platform"),
    ]
    result = cm.income_metrics(rows)["work_stability"]
    assert result.value == 57, result  # 3 Jan -> 1 Mar
    assert result.status == "Extended Gaps"


def test_consistency_penalises_bursty_work():
    """Two active months six months apart must not read as perfectly consistent.
    Consistency is judged against the calendar, not against active months only."""
    bursty = [
        cm.Transaction(date(2026, 1, day), "credit", 5000, "uber", "platform") for day in range(1, 5)
    ] + [
        cm.Transaction(date(2026, 6, day), "credit", 5000, "uber", "platform") for day in range(1, 5)
    ]
    assert cm.income_metrics(bursty)["income_consistency"].value < 40


def test_opening_balance_lifts_liquidity():
    """Starting a running balance at zero understates anyone who began the
    period with money in the account."""
    rows = ledger(months=3)
    without = cm.liquidity_metrics(rows, opening_balance=0.0)["avg_daily_balance"].value
    with_opening = cm.liquidity_metrics(rows, opening_balance=50_000)["avg_daily_balance"].value
    assert with_opening > without


def test_fixed_obligations_need_recurrence_across_months():
    """Counting transactions rather than months lets twenty coffees in one month
    register as a fixed monthly commitment."""
    base = ledger(months=4, monthly_rent=0.0)
    one_off_spree = base + [
        cm.Transaction(date(2026, 2, day), "debit", 400, "food", "manual") for day in range(1, 21)
    ]
    recurring = base + [
        cm.Transaction(date(2026, month, 5), "debit", 8000, "rent", "manual")
        for month in range(1, 5)
    ]
    assert cm.spending_metrics(one_off_spree)["fixed_obligation_ratio"].value == 0.0
    assert cm.spending_metrics(recurring)["fixed_obligation_ratio"].value > 0.0


def test_gig_stability_prefers_a_known_rating_over_history_length():
    rows = ledger(months=1)
    assert cm.gig_metrics(rows)["gig_stability"].status == "Limited Earning History"
    assert cm.gig_metrics(rows, platform_rating=4.8)["gig_stability"].status == "Excellent Platform Rating"


def test_coaching_names_the_weakest_metrics_first():
    weak = cm.analyze(ledger(months=6, weekly_payout=1500, monthly_rent=9000, days_per_month=3))
    assert weak["weaknesses"], weak["category_scores"]
    assert weak["recommended_actions"]
    assert len(weak["recommended_actions"]) <= 5
    # A profile with nothing to praise still gets an encouraging line, never an empty list.
    assert weak["strengths"]


# --------------------------------------------------------------------------- #
# Input validation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "row",
    [
        {"date": "not-a-date", "type": "credit", "amount": 100},
        {"date": "2026-01-01", "type": "transfer", "amount": 100},
        {"date": "2026-01-01", "type": "credit", "amount": "abc"},
        {"date": "2026-01-01", "type": "credit", "amount": -5},
    ],
)
def test_from_records_rejects_bad_rows_with_the_index(row):
    with pytest.raises(cm.InsufficientDataError, match="Transaction 0"):
        cm.from_records([row])


def test_empty_ledger_is_rejected():
    with pytest.raises(cm.InsufficientDataError):
        cm.from_records([])
    with pytest.raises(cm.InsufficientDataError):
        cm.analyze([])


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


def _payload(rows: list[cm.Transaction]) -> dict:
    return {
        "transactions": [
            {
                "date": tx.date.isoformat(),
                "type": tx.type,
                "amount": round(tx.amount, 2),
                "category": tx.category,
                "source": tx.source,
            }
            for tx in rows
        ]
    }


def test_analyze_transactions_endpoint():
    with TestClient(main.app) as client:
        response = client.post("/analyze-transactions", json=_payload(ledger()))
        assert response.status_code == 200, response.text
        body = response.json()

        assert config.MIN_SCORE <= body["credit_score"] <= config.MAX_SCORE
        assert body["risk_grade"]["code"].startswith("GS-")
        assert set(body["category_scores"]) == set(md.CATEGORY_WEIGHTS)
        assert body["coverage"]["months_observed"] == 6
        assert body["metrics"]["avg_monthly_income"]["status"]


def test_analyze_transactions_rejects_a_malformed_ledger():
    with TestClient(main.app) as client:
        # Caught by Pydantic before the engine sees it.
        assert client.post("/analyze-transactions", json={"transactions": []}).status_code == 422
        bad_type = client.post(
            "/analyze-transactions",
            json={"transactions": [{"date": "2026-01-01", "type": "transfer", "amount": 10}]},
        )
        assert bad_type.status_code == 422


def test_statement_upload_also_returns_the_metric_breakdown():
    csv = "\n".join(
        [
            "Txn Date,Narration,Debit,Credit,Closing Balance",
            '01/01/2026,SWIGGY PAYOUT,,"4,000.00","9,000.00"',
            '03/01/2026,UPI-PETROL HPCL,"500.00",,"8,500.00"',
            '15/01/2026,SWIGGY PAYOUT,,"3,900.00","12,400.00"',
            '05/02/2026,RENT LANDLORD,"8,000.00",,"4,400.00"',
            '12/02/2026,ZOMATO INCENTIVE,,"4,100.00","8,500.00"',
            '05/03/2026,RENT LANDLORD,"8,000.00",,"500.00"',
            '14/03/2026,SWIGGY PAYOUT,,"4,400.00","4,900.00"',
        ]
    )
    with TestClient(main.app) as client:
        response = client.post("/analyze-statement", files={"file": ("s.csv", csv, "text/csv")})
        assert response.status_code == 200, response.text
        body = response.json()

        analysis = body["metric_analysis"]
        assert analysis is not None
        assert analysis["coverage"]["months_observed"] == 3
        assert analysis["coverage"]["debits"] == 3

        # Opening balance is backed out of the first row, not taken from the close.
        assert body["statement_analysis"]["evidence"]["opening_balance"] == 5000.0

        # Rent recurs monthly and must register as a fixed obligation.
        assert analysis["metrics"]["fixed_obligation_ratio"]["value"] > 0


def test_statement_without_dates_still_scores_but_reports_the_gap():
    """The feature score does not depend on dates; the ledger does. A statement
    missing them must degrade to one result, not fail the whole request."""
    csv = "Narration,Credit\nSWIGGY PAYOUT,4000\nSWIGGY PAYOUT,4200\n"
    with TestClient(main.app) as client:
        response = client.post("/analyze-statement", files={"file": ("s.csv", csv, "text/csv")})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["metric_analysis"] is None
        assert any("breakdown unavailable" in w for w in body["statement_analysis"]["warnings"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
