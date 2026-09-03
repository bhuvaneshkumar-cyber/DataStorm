"""Checks for statement ingestion, feature derivation, and risk pricing.

Run with: .venv_ml\\Scripts\\python -m pytest ml_service -q
"""

import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import config
import main
import risk_policy
from schemas import CreditScoreRequest
from document_ingestion import dedupe_columns
from statement_features import (
    StatementParseError,
    derive_features,
    identify_columns,
    infer_primary_platform,
    parse_indian_amount,
)

# Four calendar weeks of Swiggy payouts, in the shape an Indian bank exports:
# DD/MM/YYYY dates, Indian digit grouping, a rupee symbol, and blank debit cells.
STATEMENT_CSV = """Txn Date,Narration,Debit,Credit,Closing Balance
01/01/2026,SWIGGY PAYOUT WEEKLY,,"4,000.00","4,000.00"
03/01/2026,UPI-PETROL PUMP,"500.00",,"3,500.00"
08/01/2026,SWIGGY PAYOUT WEEKLY,,"4,200.00","7,700.00"
15/01/2026,SWIGGY PAYOUT WEEKLY,,"3,900.00","11,600.00"
22/01/2026,SWIGGY PAYOUT WEEKLY,,"4,100.00","15,700.00"
28/01/2026,ZOMATO INCENTIVE,,"1,500.00","17,200.00"
"""

APPLICANT = {
    "age": 29,
    "primary_gig_platform": "Ride-Hailing",
    "platform_customer_rating": 4.7,
    "completed_gigs_per_week": 62,
    "average_weekly_payout": 9200.0,
    "payout_volatility_index": 0.18,
    "active_platform_hours_per_week": 44,
    "resilience_stash_balance": 15000.0,
}


# --------------------------------------------------------------------------- #
# Indian money parsing
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1,23,456.78", 123456.78),   # lakh-crore digit grouping
        ("(1,234.56)", -1234.56),     # accounting negative
        ("Rs. 2.5 Lakh", 250000.0),   # scale word
        ("₹ 4,000.00", 4000.0),       # rupee symbol
        ("5,000.00 Cr", 5000.0),      # trailing Cr is Credit, not Crore
        ("1.5 crore", 15000000.0),    # spelled out, so it IS a multiplier
        ("-", None),                  # absent, which is not zero
        ("N/A", None),
        ("", None),
        (None, None),
        (float("nan"), None),
        (4200, 4200.0),
    ],
)
def test_parse_indian_amount(raw, expected):
    assert parse_indian_amount(raw) == expected


def test_zero_is_not_treated_as_missing():
    """0.0 is a real balance; conflating it with None would hide an empty stash."""
    assert parse_indian_amount("0.00") == 0.0


# --------------------------------------------------------------------------- #
# Column and platform detection
# --------------------------------------------------------------------------- #


def test_identify_columns_prefers_specific_headers():
    df = pd.DataFrame(columns=["Value Date", "Particulars", "Debit Amount", "Credit Amount", "Balance"])
    columns = identify_columns(df)
    assert columns["credit"] == "Credit Amount"
    assert columns["debit"] == "Debit Amount"
    assert columns["date"] == "Value Date"
    assert columns["narration"] == "Particulars"
    assert columns["balance"] == "Balance"


def test_infer_platform_picks_the_most_frequent():
    assert infer_primary_platform(["SWIGGY PAYOUT", "swiggy payout", "UBER TRIP"]) == "Food Delivery"


def test_infer_platform_returns_none_without_evidence():
    """None means "no evidence", which must stay distinct from the "Other" category."""
    assert infer_primary_platform(["NEFT TRANSFER", "ATM WDL"]) is None


# --------------------------------------------------------------------------- #
# Feature derivation
# --------------------------------------------------------------------------- #


def _statement_frame() -> pd.DataFrame:
    return pd.read_csv(io.StringIO(STATEMENT_CSV), dtype=str)


def test_derive_features_from_a_bank_statement():
    insights = derive_features(_statement_frame())
    derived = insights.derived

    # 17,700 credited over 28 days = 4 weeks.
    assert derived["average_weekly_payout"] == pytest.approx(4425.0, abs=1.0)
    assert derived["resilience_stash_balance"] == 17200.0        # closing balance, not a guess
    assert derived["primary_gig_platform"] == "Food Delivery"    # 4 Swiggy vs 1 Zomato
    assert 0.0 <= derived["payout_volatility_index"] <= 1.0
    assert derived["completed_gigs_per_week"] >= 1

    # Debits must never be counted as income.
    assert insights.evidence["payout_rows"] == 5
    assert insights.evidence["total_credited"] == 17700.0

    # Facts a statement cannot contain are declared, not invented.
    for field in ("age", "platform_customer_rating", "active_platform_hours_per_week"):
        assert field in insights.unresolved
        assert field not in derived


def test_duplicate_and_blank_headers_are_disambiguated():
    """Repeated or empty header cells are routine in bank exports. Left alone,
    df["Credit"] returns a DataFrame and every per-cell parse dies on a TypeError."""
    assert dedupe_columns(["Date", "Credit", "Credit", "", "Credit"]) == [
        "Date", "Credit", "Credit_1", "column_4", "Credit_2"
    ]

    df = pd.DataFrame(
        [["01/01/2026", "SWIGGY", "1000", "1000"]],
        columns=dedupe_columns(["Date", "Narration", "Credit", "Credit"]),
    )
    assert derive_features(df).derived["average_weekly_payout"] == 1000.0


def test_missing_credit_column_is_rejected():
    df = pd.DataFrame({"Date": ["01/01/2026"], "Particulars": ["SWIGGY"]})
    with pytest.raises(StatementParseError, match="No credit"):
        derive_features(df)


def test_single_week_volatility_is_not_reported_as_perfectly_stable():
    """One observation has no spread. Returning 0.0 would hand out the maximum
    stability bonus on no evidence, so an unknown sits at the midpoint."""
    df = pd.DataFrame(
        {"Date": ["01/01/2026", "02/01/2026"], "Credit": ["1000", "1200"], "Narration": ["UBER", "UBER"]}
    )
    insights = derive_features(df)
    assert insights.derived["payout_volatility_index"] == 0.5
    assert any("volatility" in w for w in insights.warnings)


def test_no_date_column_leaves_weekly_features_unresolved():
    df = pd.DataFrame({"Narration": ["SWIGGY"], "Credit": ["4000"]})
    insights = derive_features(df)
    assert "average_weekly_payout" in insights.unresolved
    assert "average_weekly_payout" not in insights.derived


# --------------------------------------------------------------------------- #
# Risk policy
# --------------------------------------------------------------------------- #


def test_decisions_never_contradict_the_public_category():
    """A Good score must not come back declined, nor a Poor one approved."""
    assert risk_policy._decision(risk_policy.risk_tier(config.SCORE_GOOD)) == "APPROVE"
    assert risk_policy._decision(risk_policy.risk_tier(config.SCORE_STANDARD)) == "REFER"
    assert risk_policy._decision(risk_policy.risk_tier(config.SCORE_STANDARD - 1)) == "DECLINE"


def test_pricing_worsens_monotonically_as_score_falls():
    rates = [
        risk_policy.assess(score, CreditScoreRequest(**APPLICANT))["indicative_interest_rate_pct"]
        for score in (750, 620, 450, 200)
    ]
    assert rates == sorted(rates), rates


def test_declined_applicants_get_no_credit_limit():
    assessment = risk_policy.assess(150, CreditScoreRequest(**APPLICANT))
    assert assessment["decision"] == "DECLINE"
    assert assessment["max_credit_limit_inr"] == 0.0
    assert assessment["recommended_tenor_months"] == 0


def test_early_warning_signals_name_the_specific_fragility():
    fragile = CreditScoreRequest(
        **{**APPLICANT, "resilience_stash_balance": 0.0, "payout_volatility_index": 0.9}
    )
    codes = {s["code"] for s in risk_policy.early_warning_signals(fragile)}
    assert {"THIN_BUFFER", "INCOME_INSTABILITY"} <= codes

    assert "MODEL_DEGRADED" in {
        s["code"] for s in risk_policy.early_warning_signals(fragile, ml_available=False)
    }
    assert "MODEL_DEGRADED" not in {s["code"] for s in risk_policy.early_warning_signals(fragile)}


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


def test_predict_endpoint_carries_a_risk_assessment():
    with TestClient(main.app) as client:
        body = client.post("/predict-credit-score", json=APPLICANT).json()
        assessment = body["risk_assessment"]
        assert assessment["decision"] in {"APPROVE", "REFER", "DECLINE"}
        assert assessment["risk_grade"]["code"].startswith("GS-")
        assert assessment["indicative_interest_rate_pct"] > config.BASE_INTEREST_RATE_PCT


def test_analyze_statement_end_to_end():
    with TestClient(main.app) as client:
        response = client.post(
            "/analyze-statement",
            files={"file": ("statement.csv", STATEMENT_CSV, "text/csv")},
            data={"age": "31", "platform_customer_rating": "4.6"},
        )
        assert response.status_code == 200, response.text
        body = response.json()

        analysis = body["statement_analysis"]
        assert analysis["source_format"] == "csv"
        assert analysis["derived_features"]["primary_gig_platform"] == "Food Delivery"

        # Caller-supplied values are used and attributed, not silently defaulted.
        assert body["features_used"]["age"] == 31
        assert analysis["supplied_features"]["age"]["source"] == "caller"
        assert analysis["supplied_features"]["active_platform_hours_per_week"]["source"] == "default"

        assert body["score"]["risk_assessment"]["decision"] in {"APPROVE", "REFER", "DECLINE"}


def test_analyze_statement_rejects_unsupported_and_empty_files():
    with TestClient(main.app) as client:
        bad_type = client.post(
            "/analyze-statement", files={"file": ("notes.exe", b"MZ", "application/octet-stream")}
        )
        assert bad_type.status_code == 415

        empty = client.post("/analyze-statement", files={"file": ("empty.csv", b"", "text/csv")})
        assert empty.status_code == 400


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
