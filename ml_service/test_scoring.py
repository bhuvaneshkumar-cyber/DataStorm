"""Smoke check: rules ordering, ML path, hybrid math, and graceful fallback.

Run with: python ml_service/test_scoring.py   (or pytest)
"""

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

import main
from model_pipeline import FEATURE_ORDER, CreditModelPipeline
from schemas import CreditScoreRequest
from scoring_rules import calculate_rule_score, categorize

# Floor for a prototype trained on synthetic data. The label is a deliberately
# noisy function of the features (LABEL_NOISE_RATIO), which puts the Bayes-optimal
# accuracy at roughly 0.92 - so this floor sits just under the ceiling. A score at
# 1.0 would mean the noise term stopped doing its job and the label had leaked.
MIN_HOLDOUT_ACCURACY = 0.85

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


def test_synthetic_features_are_correlated_and_in_range():
    """The generator must produce a population that could actually exist."""
    pipeline = CreditModelPipeline.__new__(CreditModelPipeline)
    pipeline.random_state = 42
    X, y = pipeline._synthetic_training_set(4000)

    assert list(X.columns) == FEATURE_ORDER
    # Every column has to satisfy the same bounds the request schema enforces,
    # or the model is trained on rows it can never be asked to score.
    assert X["age"].between(18, 75).all()
    assert X["platform_customer_rating"].between(1.0, 5.0).all()
    assert X["completed_gigs_per_week"].between(0, 200).all()
    assert X["payout_volatility_index"].between(0.0, 1.0).all()
    assert X["active_platform_hours_per_week"].between(0, 120).all()
    assert (X["average_weekly_payout"] >= 0).all() and (X["resilience_stash_balance"] >= 0).all()

    # Ratings must cluster high, the way a deactivation policy forces them to.
    assert X["platform_customer_rating"].median() > 4.0

    # Hours -> payout -> stash must actually co-move; independent draws (the old
    # behaviour) would sit near zero here.
    assert X["active_platform_hours_per_week"].corr(X["average_weekly_payout"]) > 0.3
    assert X["average_weekly_payout"].corr(X["resilience_stash_balance"]) > 0.3

    # Both classes must be well represented for the stratified split to work.
    share = float(np.mean(y))
    assert 0.3 < share < 0.6, share


def test_model_accuracy_clears_the_prototype_floor():
    pipeline = CreditModelPipeline()
    assert pipeline.is_ready
    assert pipeline.holdout_accuracy is not None
    assert pipeline.holdout_accuracy >= MIN_HOLDOUT_ACCURACY, pipeline.holdout_accuracy
    # A perfect score would mean the label leaked; the noise term prevents it.
    assert pipeline.holdout_accuracy < 1.0, pipeline.holdout_accuracy


def test_shap_returns_empty_list_when_the_explainer_breaks():
    """SHAP failures must degrade to an unexplained score, never a 500."""
    pipeline = CreditModelPipeline()

    class BrokenExplainer:
        def shap_values(self, *_args, **_kwargs):
            raise RuntimeError("explainer exploded")

    pipeline.explainer = BrokenExplainer()
    assert pipeline._explain(pd.DataFrame([dict.fromkeys(FEATURE_ORDER, 0)])) == []

    # No explainer at all is the other fallback path.
    pipeline.explainer = None
    assert pipeline._explain(pd.DataFrame([dict.fromkeys(FEATURE_ORDER, 0)])) == []


def test_endpoint_hybrid_and_shap():
    with TestClient(main.app) as client:
        health = client.get("/health").json()
        assert health["ml_model_loaded"] is True
        assert health["holdout_accuracy"] >= MIN_HOLDOUT_ACCURACY, health

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
    test_synthetic_features_are_correlated_and_in_range()
    test_model_accuracy_clears_the_prototype_floor()
    test_shap_returns_empty_list_when_the_explainer_breaks()
    test_endpoint_hybrid_and_shap()
    test_fallback_when_model_dies()
    print("all checks passed")
