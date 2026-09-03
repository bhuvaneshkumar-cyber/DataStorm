"""Smoke check: rules ordering, ML path, hybrid math, and graceful fallback.

Run with: python ml_service/test_scoring.py   (or pytest)
"""

from fastapi.testclient import TestClient

import main
from schemas import CreditScoreRequest
from scoring_rules import calculate_rule_score, categorize

STRONG = {
    "age": 34,
    "primary_gig_platform": "Ride-Hailing",
    "platform_customer_rating": 4.9,
    "completed_gigs_per_week": 70,
    "average_weekly_payout": 14000.0,
    "payout_volatility_index": 0.08,
    "active_platform_hours_per_week": 45,
    "resilience_stash_balance": 70000.0,
}
WEAK = {
    "age": 19,
    "primary_gig_platform": "Other",
    "platform_customer_rating": 2.9,
    "completed_gigs_per_week": 4,
    "average_weekly_payout": 1500.0,
    "payout_volatility_index": 0.85,
    "active_platform_hours_per_week": 80,
    "resilience_stash_balance": 0.0,
}


def test_rules_rank_and_bound():
    strong = calculate_rule_score(CreditScoreRequest(**STRONG))
    weak = calculate_rule_score(CreditScoreRequest(**WEAK))
    assert strong > weak, (strong, weak)
    assert 0 <= weak <= 800 and 0 <= strong <= 800
    assert categorize(strong) == "Good" and categorize(weak) == "Poor"


def test_endpoint_hybrid_and_shap():
    with TestClient(main.app) as client:
        assert client.get("/health").json()["ml_model_loaded"] is True

        body = client.post("/predict-credit-score", json=STRONG).json()
        assert body["ml_available"] is True
        expected = round(body["rule_score"] * 0.4 + body["ml_score"] * 0.6, 2)
        assert abs(body["final_score"] - expected) < 0.01, body
        assert len(body["explanation"]) == 3, body["explanation"]
        assert body["category"] in {"Poor", "Standard", "Good"}
        assert body["latency_ms"] >= 0

        # Validation boundary: rating outside 1.0-5.0 must be rejected.
        assert client.post("/predict-credit-score", json={**STRONG, "platform_customer_rating": 5.4}).status_code == 422


def test_fallback_when_model_dies():
    with TestClient(main.app) as client:
        main.pipeline.model = None  # simulate a broken/unloaded model
        body = client.post("/predict-credit-score", json=STRONG).json()
        assert body["ml_available"] is False and body["ml_score"] is None
        assert body["final_score"] == body["rule_score"], body


if __name__ == "__main__":
    test_rules_rank_and_bound()
    test_endpoint_hybrid_and_shap()
    test_fallback_when_model_dies()
    print("all checks passed")
