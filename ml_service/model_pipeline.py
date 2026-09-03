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
from sklearn.model_selection import train_test_split

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

# Share of the synthetic population labelled creditworthy. Fixing this keeps the
# classes balanced enough for a stratified split however the features are drawn.
GOOD_CLASS_SHARE = 0.45

# Label noise, expressed as a fraction of the latent score's own spread rather
# than as an absolute sigma. Creditworthiness is not fully determined by eight
# features, so some irreducible error belongs in the labels - but pinning it to
# a fixed sigma made the difficulty an accident of how the features happened to
# be scaled. At 0.25 the Bayes-optimal accuracy is ~0.92, so a model scoring
# just under that is at the ceiling, not underfitting.
LABEL_NOISE_RATIO = 0.25


class CreditModelPipeline:
    """Encode -> predict -> explain. Never raises: callers fall back to rules."""

    def __init__(self, n_samples: int = 4000, random_state: int = 42):
        self.random_state = random_state
        self.model: RandomForestClassifier | None = None
        self.explainer: shap.TreeExplainer | None = None
        # Held-out accuracy from the last training run; None if training failed.
        self.holdout_accuracy: float | None = None
        self._train(n_samples)

    # ---------------------------------------------------------------- training

    def _synthetic_training_set(self, n: int) -> tuple[pd.DataFrame, np.ndarray]:
        """Generate a labelled sample whose signal mirrors the rule engine.

        The features are drawn *correlated*, not independently. Real gig-work
        data is heavily structured - hours drive payout, payout drives how much
        can be saved, ratings cluster near the top because low-rated workers get
        deactivated - and a model trained on independent uniform draws learns a
        feature space that no real applicant lives in. It scores well in testing
        and then attributes nonsense in production, because it has seen
        combinations (90 hours a week for a 1200 rupee payout, a 3.1 rating that
        was never deactivated) that cannot occur.
        """
        rng = np.random.default_rng(self.random_state)

        # Right-skewed: gig work skews young, with a long tail of older workers.
        age = np.clip(18 + rng.gamma(2.2, 6.0, n), 18, 65).astype(int)

        # Platform mix roughly reflects Indian metro gig work.
        platform = rng.choice(len(PLATFORMS), n, p=[0.34, 0.38, 0.18, 0.10])
        is_freelance = platform == PLATFORMS.index("Freelance")

        # Hours are the root driver; most work near-full-time, some part-time.
        hours = np.clip(rng.normal(42, 14, n), 5, 90)

        # Earnings per hour: freelance pays better per hour and spreads wider.
        hourly = np.where(
            is_freelance,
            rng.lognormal(np.log(320), 0.45, n),
            rng.lognormal(np.log(185), 0.30, n),
        )
        payout = np.clip(hours * hourly, 800, 30000)

        # Gig count follows hours - except freelancers bill few, large jobs.
        gigs = np.where(
            is_freelance,
            rng.integers(1, 8, n),
            np.clip(hours * rng.normal(1.9, 0.45, n), 0, 120),
        ).astype(int)

        # Ratings pile up near 5.0: sub-4.2 workers are deactivated, so the tail
        # is thin. Uniform 1-5 would hand the model variance that does not exist.
        rating = np.round(np.clip(5.0 - rng.beta(2.0, 7.5, n) * 3.0, 1.0, 5.0), 2)

        # Volatility is mostly low-to-moderate; freelance income swings hardest.
        volatility = np.round(
            np.clip(rng.beta(2.2, 5.0, n) + np.where(is_freelance, 0.12, 0.0), 0.0, 1.0), 3
        )

        # Savings are a habit multiplied by capacity, not an independent draw:
        # a worker cannot stash what they never earned.
        savings_habit = rng.beta(1.8, 3.2, n)
        stash = np.round(np.clip(savings_habit * payout * rng.uniform(0, 11, n), 0, 150000), 2)

        df = pd.DataFrame(
            {
                "age": age,
                "primary_gig_platform": platform,
                "platform_customer_rating": rating,
                "completed_gigs_per_week": gigs,
                "average_weekly_payout": np.round(payout, 2),
                "payout_volatility_index": volatility,
                "active_platform_hours_per_week": hours.astype(int),
                "resilience_stash_balance": stash,
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
        noise = rng.normal(0, LABEL_NOISE_RATIO * float(latent.std()), n)

        # Cut at a quantile rather than a fixed 0.55. With correlated features
        # the latent distribution shifts, and a hard cut can leave one class
        # nearly empty - which would break the stratified split downstream.
        threshold = float(np.quantile(latent, 1.0 - GOOD_CLASS_SHARE))
        labels = ((latent + noise) > threshold).astype(int)
        return df, labels

    def _train(self, n_samples: int) -> None:
        try:
            X, y = self._synthetic_training_set(n_samples)
            # Held-out split so the logged accuracy reflects generalization,
            # not memorization of the training rows.
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=self.random_state, stratify=y
            )
            self.model = RandomForestClassifier(
                n_estimators=120,
                max_depth=8,
                min_samples_leaf=5,
                random_state=self.random_state,
                n_jobs=-1,
            ).fit(X_train, y_train)
            self.explainer = shap.TreeExplainer(self.model)
            self.holdout_accuracy = round(float(self.model.score(X_test, y_test)), 4)
            logger.info(
                "Model trained on %d synthetic rows (train accuracy %.3f, held-out accuracy %.3f)",
                len(X_train),
                self.model.score(X_train, y_train),
                self.holdout_accuracy,
            )
        except Exception:
            logger.exception("Model training failed; service will run rules-only")
            self.model = None
            self.explainer = None
            self.holdout_accuracy = None

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
