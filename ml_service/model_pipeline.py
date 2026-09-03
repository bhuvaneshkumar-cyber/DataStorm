"""RandomForest scoring pipeline with SHAP explainability.

The model is trained on synthetic data at startup (hackathon: no labelled
portfolio exists yet). Swap `_synthetic_training_set` for a real dataset loader
and the rest of this module is unchanged.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import RandomForestClassifier

from schemas import CreditScoreRequest

logger = logging.getLogger(__name__)

# Ordinal encoding for the one categorical feature. Fixed list => stable column
# meaning across restarts; unseen values fall back to "Other".
PLATFORMS = ["Ride-Hailing", "Food Delivery", "Freelance", "Other"]
PLATFORM_CODES = {name: i for i, name in enumerate(PLATFORMS)}

FEATURE_ORDER = [
    "age",
    "primary_gig_platform",
    "platform_customer_rating",
    "completed_gigs_per_week",
    "average_weekly_payout",
    "payout_volatility_index",
    "active_platform_hours_per_week",
    "resilience_stash_balance",
]

MAX_SCORE = 800.0


class CreditModelPipeline:
    """Encode -> predict -> explain. Never raises: callers fall back to rules."""

    def __init__(self, n_samples: int = 4000, random_state: int = 42):
        self.random_state = random_state
        self.model: RandomForestClassifier | None = None
        self.explainer: shap.TreeExplainer | None = None
        self._train(n_samples)

    # ---------------------------------------------------------------- training

    def _synthetic_training_set(self, n: int) -> tuple[pd.DataFrame, np.ndarray]:
        """Generate a labelled sample whose signal mirrors the rule engine."""
        rng = np.random.default_rng(self.random_state)
        df = pd.DataFrame(
            {
                "age": rng.integers(18, 66, n),
                "primary_gig_platform": rng.integers(0, len(PLATFORMS), n),
                "platform_customer_rating": np.round(rng.uniform(1.0, 5.0, n), 2),
                "completed_gigs_per_week": rng.integers(0, 120, n),
                "average_weekly_payout": np.round(rng.uniform(1000, 25000, n), 2),
                "payout_volatility_index": np.round(rng.uniform(0.0, 1.0, n), 3),
                "active_platform_hours_per_week": rng.integers(5, 90, n),
                "resilience_stash_balance": np.round(rng.uniform(0, 80000, n), 2),
            }
        )[FEATURE_ORDER]

        # Latent creditworthiness: stash runway + rating + stability - volatility.
        runway = df["resilience_stash_balance"] / df["average_weekly_payout"].clip(lower=1)
        latent = (
            0.35 * np.clip(runway / 6.0, 0, 1)
            + 0.25 * (df["platform_customer_rating"] - 1.0) / 4.0
            + 0.20 * (1.0 - df["payout_volatility_index"])
            + 0.12 * np.clip(df["average_weekly_payout"] / 20000.0, 0, 1)
            + 0.08 * np.clip(df["completed_gigs_per_week"] / 60.0, 0, 1)
        )
        noise = rng.normal(0, 0.06, n)
        labels = ((latent + noise) > 0.55).astype(int)
        return df, labels

    def _train(self, n_samples: int) -> None:
        try:
            X, y = self._synthetic_training_set(n_samples)
            self.model = RandomForestClassifier(
                n_estimators=120,
                max_depth=8,
                min_samples_leaf=5,
                random_state=self.random_state,
                n_jobs=-1,
            ).fit(X, y)
            self.explainer = shap.TreeExplainer(self.model)
            logger.info(
                "Model trained on %d synthetic rows (train accuracy %.3f)",
                n_samples,
                self.model.score(X, y),
            )
        except Exception:
            logger.exception("Model training failed; service will run rules-only")
            self.model = None
            self.explainer = None

    @property
    def is_ready(self) -> bool:
        return self.model is not None

    # --------------------------------------------------------------- inference

    @staticmethod
    def encode(payload: CreditScoreRequest) -> pd.DataFrame:
        """Turn one request into a single-row frame in FEATURE_ORDER."""
        row = payload.model_dump()
        row["primary_gig_platform"] = PLATFORM_CODES.get(
            row["primary_gig_platform"], PLATFORM_CODES["Other"]
        )
        return pd.DataFrame([row])[FEATURE_ORDER]

    def predict(self, payload: CreditScoreRequest) -> tuple[float, float, list[dict]] | None:
        """Return (ml_score 0-800, confidence, top-3 SHAP factors), or None on failure."""
        if self.model is None:
            return None
        try:
            X = self.encode(payload)
            proba = self.model.predict_proba(X)[0]
            classes = list(self.model.classes_)
            good_p = float(proba[classes.index(1)]) if 1 in classes else 0.0
            return round(good_p * MAX_SCORE, 2), round(float(proba.max()), 4), self._explain(X)
        except Exception:
            logger.exception("ML prediction failed; degrading to rule engine")
            return None

    def _explain(self, X: pd.DataFrame) -> list[dict]:
        """Top 3 features by |SHAP| for the positive class. Empty list on failure."""
        if self.explainer is None:
            return []
        try:
            values = self.explainer.shap_values(X, check_additivity=False)
            if isinstance(values, list):  # older shap: one array per class
                row = np.asarray(values[-1])[0]
            else:
                row = np.asarray(values)[0]
                if row.ndim == 2:  # newer shap: (n_features, n_classes)
                    row = row[:, -1]
            top = np.argsort(np.abs(row))[::-1][:3]
            return [
                {
                    "feature": FEATURE_ORDER[i],
                    "impact": round(float(row[i]), 4),
                    "direction": "positive" if row[i] >= 0 else "negative",
                }
                for i in top
            ]
        except Exception:
            logger.exception("SHAP explanation failed; returning empty explanation")
            return []
