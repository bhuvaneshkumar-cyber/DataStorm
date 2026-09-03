"""Thin client for the scoring service, used wherever the backend needs a score.

The backend scores server-side rather than trusting a figure posted by the
browser. That is not caution for its own sake: a loan application carries the
score it was judged on, so a client able to name its own score could name 800
and be approved. Every score persisted by this service comes from here.

The scoring service is a hard dependency for those routes and a soft one
everywhere else, so failures raise a single typed error and each caller decides
whether that is fatal or merely a missing panel.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://localhost:8001").rstrip("/")

# Scoring is CPU-bound but small; ten seconds is generous for a healthy service
# and short enough that an unhealthy one does not hold a request open.
TIMEOUT_SECONDS = float(os.getenv("ML_SERVICE_TIMEOUT", "10"))


class ScoringUnavailable(Exception):
    """The scoring service could not be reached, or answered with an error."""


# One pooled client for the process. Rebuilding a client per request throws away
# the connection pool and, on Windows, leaks ephemeral ports under load.
_client: Optional[httpx.Client] = None


def get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(base_url=ML_SERVICE_URL, timeout=TIMEOUT_SECONDS)
    return _client


def close_client() -> None:
    """Releases the pool at shutdown. Safe to call when nothing was opened."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


def _post(path: str, payload: Dict[str, Any], what: str) -> Dict[str, Any]:
    """POSTs JSON and unwraps the service's own error message on failure.

    Surfacing the upstream `detail` matters: "422 Unprocessable Entity" tells a
    worker nothing, while "average_weekly_payout: must be >= 0" tells them
    exactly which piece of their profile is unusable.
    """
    try:
        response = get_client().post(path, json=payload)
    except httpx.HTTPError as exc:
        logger.warning("Scoring service unreachable at %s%s: %s", ML_SERVICE_URL, path, exc)
        raise ScoringUnavailable(
            f"The scoring service is unreachable, so {what} is not available right now."
        ) from exc

    if response.is_success:
        return response.json()

    detail = ""
    try:
        body = response.json()
        detail = body.get("detail") if isinstance(body, dict) else ""
        if not isinstance(detail, str):
            detail = str(detail)
    except ValueError:
        detail = response.text[:200]

    logger.warning("Scoring service returned %s for %s: %s", response.status_code, path, detail)
    raise ScoringUnavailable(detail or f"The scoring service could not complete {what}.")


def score_applicant(features: Dict[str, Any]) -> Dict[str, Any]:
    """Hybrid credit score plus the full risk assessment for one applicant."""
    return _post("/predict-credit-score", features, "your credit score")


def analyze_transactions(
    transactions: list, platform_rating: Optional[float] = None, opening_balance: float = 0.0
) -> Dict[str, Any]:
    """Per-metric breakdown of a ledger, for the 'why' behind a score."""
    return _post(
        "/analyze-transactions",
        {
            "transactions": transactions,
            "platform_rating": platform_rating,
            "opening_balance": opening_balance,
        },
        "the metric breakdown",
    )


def recommend_insurance(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Ranked micro-insurance paths for a scored, employed profile."""
    return _post("/recommend-insurance", payload, "an insurance recommendation")


def health() -> Dict[str, Any]:
    """Never raises: this backs the backend's own /health, which must always answer."""
    try:
        response = get_client().get("/health")
        response.raise_for_status()
        return {"status": "reachable", **response.json()}
    except (httpx.HTTPError, ValueError) as exc:
        return {"status": "unreachable", "url": ML_SERVICE_URL, "error": str(exc)}
