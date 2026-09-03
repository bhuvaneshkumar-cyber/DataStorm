"""FastAPI service: hybrid (rules + RandomForest) gig-worker credit scoring."""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from model_pipeline import CreditModelPipeline
from schemas import CreditScoreRequest, CreditScoreResponse
from scoring_rules import calculate_rule_score, categorize

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

RULE_WEIGHT, ML_WEIGHT = 0.4, 0.6

pipeline: CreditModelPipeline | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Train the model once at startup, not per request."""
    global pipeline
    pipeline = CreditModelPipeline()
    yield
    pipeline = None


app = FastAPI(
    title="Gig-Worker Financial Resilience - Scoring Service",
    version="1.0.0",
    description="Hybrid rule + ML credit scoring with SHAP explanations.",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    """Liveness, plus whether the ML path is available (rules always are)."""
    ready = pipeline is not None and pipeline.is_ready
    return {"status": "ok", "ml_model_loaded": ready, "mode": "hybrid" if ready else "rules_only"}


@app.post("/predict-credit-score", response_model=CreditScoreResponse)
def predict_credit_score(payload: CreditScoreRequest) -> CreditScoreResponse:
    """Score one applicant. Degrades to 100% rule-based if the ML path fails."""
    start = time.perf_counter()

    rule_score = calculate_rule_score(payload)
    result = pipeline.predict(payload) if pipeline else None

    if result is None:
        # ponytail: rules-only confidence is a fixed 0.6, not a calibrated number.
        final_score, ml_score, confidence, explanation = rule_score, None, 0.6, []
    else:
        ml_score, confidence, explanation = result
        final_score = round(rule_score * RULE_WEIGHT + ml_score * ML_WEIGHT, 2)

    return CreditScoreResponse(
        final_score=final_score,
        category=categorize(final_score),
        confidence=confidence,
        rule_score=rule_score,
        ml_score=ml_score,
        ml_available=result is not None,
        explanation=explanation,
        latency_ms=round((time.perf_counter() - start) * 1000, 2),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
