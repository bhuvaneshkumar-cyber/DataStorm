"""Route-level tests for the financials and insurance endpoints.

The parsing and ranking logic is covered by each module's own self-check; what
these add is the HTTP contract around them -- the upload guards, the error
codes, and the guarantee that an unknown figure reaches the client as null
rather than as a confident zero.
"""

import io

import pytest
from fastapi.testclient import TestClient

import financial_statements
import insurance_advisor
from main import app

client = TestClient(app)


REPORT = """Acme Freight Private Limited
Statement of Profit and Loss (Rs. in lakhs)
Particulars                            2025-26     2024-25
Revenue from operations                2,400.00    2,050.00
Depreciation and amortisation            180.00      165.00
Finance costs                            120.00      140.00
Profit before tax                        400.00      300.00
Tax expense                              100.00       75.00
Profit for the year                      300.00      225.00
Equity share capital                     250.00      250.00
Reserves and surplus                     950.00      650.00
Long term borrowings                     800.00      900.00
Short term borrowings                    300.00      280.00
Current maturities of long term debt     200.00      190.00
"""


def _upload(content: str, filename: str = "accounts.txt"):
    return {"file": (filename, io.BytesIO(content.encode("utf-8")), "text/plain")}


class TestModuleSelfChecks:
    """Runs each module's own assertions inside the suite, so CI sees them."""

    def test_financial_statements_self_check(self):
        financial_statements.demo()

    def test_insurance_advisor_self_check(self):
        insurance_advisor.demo()


class TestAnalyzeFinancials:
    def test_reads_reported_figures_and_derives_the_rest(self):
        response = client.post("/analyze-financials", files=_upload(REPORT))
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["reporting_scale"] == "lakh"
        assert body["scale_multiplier"] == 100_000.0
        assert body["source_format"] == "txt"

        metrics = body["metrics"]
        assert metrics["revenue"]["value"] == 2_400.0 * 100_000
        assert metrics["revenue"]["source"] == "reported"
        assert metrics["profit_after_tax"]["value"] == 300.0 * 100_000

        # Not stated anywhere in the report, so it must be reconstructed.
        assert metrics["ebitda"]["source"] == "derived"
        assert metrics["ebitda"]["value"] == (400.0 + 120.0 + 180.0) * 100_000
        assert metrics["net_worth"]["value"] == (250.0 + 950.0) * 100_000
        assert metrics["total_debt"]["value"] == (800.0 + 300.0) * 100_000

    def test_ratios_are_computed_from_the_extracted_figures(self):
        body = client.post("/analyze-financials", files=_upload(REPORT)).json()
        ratios = body["ratios"]

        # Ratios are reported to two decimals, which is how they are quoted in a
        # credit note; the assertions round the same way rather than chasing
        # float noise the API deliberately does not expose.
        assert ratios["debt_to_equity"]["value"] == pytest.approx(round(1100.0 / 1200.0, 2))
        assert ratios["dscr"]["value"] == pytest.approx(round(700.0 / 320.0, 2))
        assert ratios["pat_margin_pct"]["value"] == pytest.approx(12.5)
        assert body["unresolved"] == []

    def test_every_figure_carries_the_line_it_came_from(self):
        body = client.post("/analyze-financials", files=_upload(REPORT)).json()
        found = body["evidence"]["line_items_found"]
        assert "Revenue from operations" in found["revenue"]["line"]
        assert found["profit_before_tax"]["label"] == "profit before tax"

    def test_a_document_with_no_accounts_warns_instead_of_answering_zero(self):
        body = client.post(
            "/analyze-financials", files=_upload("Dear customer, your order has shipped.")
        ).json()
        assert body["metrics"]["revenue"]["value"] is None
        assert body["metrics"]["revenue"]["source"] == "unavailable"
        assert "revenue" in body["unresolved"]
        assert any("No recognisable" in warning for warning in body["warnings"])

    def test_missing_reporting_unit_is_warned_about(self):
        plain = REPORT.replace("(Rs. in lakhs)", "")
        body = client.post("/analyze-financials", files=_upload(plain)).json()
        assert body["reporting_scale"] == "rupees"
        assert body["metrics"]["revenue"]["value"] == 2_400.0
        assert any("No reporting unit" in warning for warning in body["warnings"])

    def test_unsupported_extension_and_empty_file_are_refused(self):
        assert client.post("/analyze-financials", files=_upload("x", "notes.exe")).status_code == 415
        assert client.post("/analyze-financials", files=_upload("", "empty.txt")).status_code == 400

    def test_a_csv_of_accounts_is_read_through_the_same_path(self):
        csv = (
            "Particulars,2025-26\n"
            "Revenue from operations,\"1,000.00\"\n"
            "Profit for the year,\"120.00\"\n"
            "Equity share capital,\"400.00\"\n"
        )
        body = client.post("/analyze-financials", files=_upload(csv, "accounts.csv")).json()
        assert body["source_format"] == "csv"
        assert body["metrics"]["revenue"]["value"] == 1_000.0
        assert body["metrics"]["profit_after_tax"]["value"] == 120.0


class TestEstimateFinancials:
    payload = {
        "gst_taxable_turnover": 900_000.0,
        "period_months": 6,
        "bank_rows": [
            {"type": "credit", "amount": 500_000, "description": "Customer receipts"},
            {"type": "debit", "amount": 180_000, "description": "Diesel and tolls"},
            {"type": "debit", "amount": 24_000, "description": "Interest on term loan"},
            {"type": "debit", "amount": 60_000, "description": "EMI repayment"},
        ],
    }

    def test_gst_turnover_drives_revenue_and_is_annualised(self):
        body = client.post("/estimate-financials", json=self.payload).json()
        assert body["metrics"]["revenue"]["source"] == "estimated"
        assert body["metrics"]["revenue"]["value"] == 1_800_000.0

    def test_interest_and_principal_are_classified_once_each(self):
        body = client.post("/estimate-financials", json=self.payload).json()
        # 24,000 interest and 60,000 principal, each annualised once and neither
        # counted in the other bucket or in operating outflow.
        assert body["metrics"]["finance_cost"]["value"] == 48_000.0
        assert body["metrics"]["current_portion_debt"]["value"] == 120_000.0
        assert body["metrics"]["ebitda"]["value"] == (500_000 - 180_000) * 2

    def test_balance_sheet_figures_are_refused_rather_than_guessed(self):
        body = client.post("/estimate-financials", json=self.payload).json()
        assert body["metrics"]["net_worth"]["value"] is None
        assert body["metrics"]["total_debt"]["value"] is None
        assert body["ratios"]["debt_to_equity"]["value"] is None
        assert "net_worth" in body["unresolved"]
        assert any("indicative" in warning for warning in body["warnings"])

    def test_a_very_short_period_is_flagged(self):
        body = client.post(
            "/estimate-financials", json={**self.payload, "period_months": 1}
        ).json()
        assert any("month(s)" in warning for warning in body["warnings"])

    def test_period_months_must_be_positive(self):
        assert (
            client.post("/estimate-financials", json={**self.payload, "period_months": 0}).status_code
            == 422
        )


class TestRecommendInsurance:
    def test_a_road_worker_is_ranked_and_priced(self):
        response = client.post(
            "/recommend-insurance",
            json={
                "credit_score": 420,
                "employment_type": "Ride-Hailing",
                "average_weekly_payout": 9_000,
                "resilience_stash_balance": 3_000,
                "active_platform_hours_per_week": 66,
                "payout_volatility_index": 0.4,
                "age": 29,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["matched_exposure_profile"] == "ride-hailing"
        assert body["risk_tier"] == "HIGH"
        options = body["recommendations"]
        assert options and all(
            a["priority"] >= b["priority"] for a, b in zip(options, options[1:])
        )
        assert {"personal_accident", "income_protection"} <= {o["code"] for o in options}
        assert all(o["reasons"] for o in options)
        assert all(o["indicative_monthly_premium_inr"] for o in options)

    def test_the_supplied_risk_tier_overrides_the_one_derived_from_the_score(self):
        body = client.post(
            "/recommend-insurance",
            json={"credit_score": 700, "employment_type": "driver", "risk_tier": "VERY_HIGH"},
        ).json()
        assert body["risk_tier"] == "VERY_HIGH"

    def test_no_logged_income_means_no_invented_premium(self):
        body = client.post(
            "/recommend-insurance", json={"credit_score": 500, "employment_type": "courier"}
        ).json()
        assert body["savings_runway_weeks"] == 0.0
        assert all(o["indicative_monthly_premium_inr"] is None for o in body["recommendations"])

    def test_an_out_of_range_score_is_rejected(self):
        assert (
            client.post("/recommend-insurance", json={"credit_score": 5_000}).status_code == 422
        )


def test_health_still_reports_ingestion_capability():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert "ingestion_formats" in body
