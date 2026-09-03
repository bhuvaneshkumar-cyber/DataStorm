"""FastAPI service: hybrid (rules + RandomForest) gig-worker credit scoring.

Two ways in:
  POST /predict-credit-score  - score a fully specified applicant.
  POST /analyze-statement     - upload a bank/payout statement, derive what it
                                evidences, and score that.

Both return the same score object plus a risk assessment. Every layer degrades
rather than fails: no ML model falls back to rules, no parser libraries fall
back to a clear 503 on the upload route only.
"""

import logging
import shutil
import tempfile
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Iterator, Optional

import pandas as pd
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

import config
import credit_metrics
import document_ingestion
import financial_statements
import insurance_advisor
import risk_policy
import statement_features
from model_pipeline import CreditModelPipeline
from schemas import (
    CreditScoreRequest,
    CreditScoreResponse,
    FinancialAnalysisResponse,
    FinancialEstimateRequest,
    InsuranceRecommendation,
    InsuranceRequest,
    MetricAnalysis,
    StatementAnalysis,
    StatementScoreResponse,
    TransactionAnalysisRequest,
)
from scoring_rules import calculate_rule_score, categorize

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

pipeline: Optional[CreditModelPipeline] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Train the model once at startup, not per request."""
    global pipeline
    pipeline = CreditModelPipeline()
    yield
    pipeline = None


app = FastAPI(
    title="Gig-Worker Financial Resilience - Scoring Service",
    version="1.1.0",
    description=(
        "Hybrid rule + ML credit scoring with SHAP explanations, risk-based "
        "pricing, and multi-format statement ingestion."
    ),
    lifespan=lifespan,
)

# Hackathon MVP: wide open, same as backend/main.py. The frontend calls this
# service directly (VITE_ML_URL), so it needs its own CORS, not just the backend's.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


def _score(applicant: CreditScoreRequest) -> CreditScoreResponse:
    """Scores one applicant. Degrades to 100% rule-based if the ML path fails.

    Shared by both entry points so the two routes can never drift apart on how a
    score is composed.
    """
    start = time.perf_counter()

    rule_score = calculate_rule_score(applicant)
    result = pipeline.predict(applicant) if pipeline else None

    if result is None:
        # ponytail: rules-only confidence is a fixed constant, not a calibrated number.
        final_score = rule_score
        ml_score, confidence, explanation = None, config.RULES_ONLY_CONFIDENCE, []
    else:
        ml_score, confidence, explanation = result
        final_score = round(
            rule_score * config.RULE_WEIGHT + ml_score * config.ML_WEIGHT, 2
        )

    ml_available = result is not None

    return CreditScoreResponse(
        final_score=final_score,
        category=categorize(final_score),
        confidence=confidence,
        rule_score=rule_score,
        ml_score=ml_score,
        ml_available=ml_available,
        explanation=explanation,
        risk_assessment=risk_policy.assess(final_score, applicant, ml_available),
        latency_ms=round((time.perf_counter() - start) * 1000, 2),
    )


@app.get("/health")
def health() -> dict:
    """Liveness, plus which optional capabilities this deployment actually has."""
    ready = pipeline is not None and pipeline.is_ready
    return {
        "status": "ok",
        "ml_model_loaded": ready,
        "mode": "hybrid" if ready else "rules_only",
        "ingestion_formats": document_ingestion.available_formats(),
    }


@app.post("/predict-credit-score", response_model=CreditScoreResponse)
def predict_credit_score(payload: CreditScoreRequest) -> CreditScoreResponse:
    """Score one fully specified applicant."""
    return _score(payload)


# --------------------------------------------------------------------------- #
# Transaction-driven metrics
# --------------------------------------------------------------------------- #


def _metric_analysis(
    records: list, platform_rating: Optional[float], opening_balance: float
) -> MetricAnalysis:
    """Runs the ledger through the metric engine and attaches a risk grade.

    The grade comes from risk_policy rather than a second set of bands, so the
    ledger path and the feature path can never disagree about what a score means.
    """
    try:
        transactions = credit_metrics.from_records(records)
        analysis = credit_metrics.analyze(transactions, platform_rating, opening_balance)
    except credit_metrics.InsufficientDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return MetricAnalysis(
        **analysis, risk_grade=risk_policy.risk_grade(analysis["credit_score"])
    )


@app.post("/analyze-transactions", response_model=MetricAnalysis)
def analyze_transactions(payload: TransactionAnalysisRequest) -> MetricAnalysis:
    """Score a transaction ledger and explain the result metric by metric.

    Source-agnostic: bank rows, platform payout feeds and manual entries all
    score through the same path once expressed as standardized transactions.
    """
    return _metric_analysis(
        [tx.model_dump() for tx in payload.transactions],
        payload.platform_rating,
        payload.opening_balance,
    )


# --------------------------------------------------------------------------- #
# Statement ingestion
# --------------------------------------------------------------------------- #

# Used only for features a statement cannot evidence and the caller did not send.
# Deliberately unflattering: an unevidenced applicant should not be scored as if
# the missing facts were favourable. Every use is reported in supplied_features.
_FALLBACKS = {
    "age": 30,
    "primary_gig_platform": "Other",
    "platform_customer_rating": 4.0,
    "completed_gigs_per_week": 0,
    "average_weekly_payout": 0.0,
    "payout_volatility_index": 0.5,
    "active_platform_hours_per_week": 40,
    "resilience_stash_balance": 0.0,
}


def _save_upload(upload: UploadFile, directory: Path) -> Path:
    """Streams the upload to disk, enforcing the size cap as it goes.

    Streamed rather than read into memory so an oversized file is rejected
    before it can exhaust the process, not after.
    """
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in config.ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type {suffix or '(none)'}. Allowed: "
                f"{', '.join(sorted(config.ALLOWED_UPLOAD_EXTENSIONS))}"
            ),
        )

    destination = directory / f"statement{suffix}"
    written = 0
    with destination.open("wb") as handle:
        while chunk := upload.file.read(1024 * 1024):
            written += len(chunk)
            if written > config.MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds the {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
                )
            handle.write(chunk)

    if written == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty."
        )
    return destination


@contextmanager
def _parsed_upload(file: UploadFile) -> Iterator[dict]:
    """Saves an upload, parses it, and always deletes it again.

    Shared by both upload routes so the size cap, the extension allowlist, the
    parser error mapping and -- most importantly -- the guaranteed cleanup exist
    once. Uploaded documents are personal financial data and must not outlive
    the request that read them.

    The parse is wrapped separately from the `yield`: catching around the yield
    too would swallow the caller's own exceptions and report an unrelated
    scoring failure as an unreadable file.
    """
    workspace = Path(tempfile.mkdtemp(prefix="gigsave-upload-"))
    try:
        path = _save_upload(file, workspace)

        try:
            parsed = document_ingestion.ingest(str(path))
        except document_ingestion.DependencyMissingError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc
        except document_ingestion.UnsupportedFormatError as exc:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
            ) from exc
        except document_ingestion.IngestionError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc

        yield parsed
    finally:
        file.file.close()
        shutil.rmtree(workspace, ignore_errors=True)


def _tabulate(parsed: dict) -> pd.DataFrame:
    """Gets a transaction table out of whatever the ingestor returned.

    CSV/Excel already yield a frame. A PDF yields tables whose first row is the
    header; the widest table is the statement body, narrower ones are summary
    boxes.
    """
    frame = parsed.get("dataframe")
    if frame is not None:
        return frame

    tables = parsed.get("tables") or []
    if not tables:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "No transaction table could be located in the document. "
                "A CSV or Excel export of the statement parses far more reliably."
            ),
        )

    widest = max(tables, key=lambda t: len(t["data"][0]) if t["data"] else 0)
    rows = widest["data"]
    try:
        # PDF tables skip _promote_header, so they need the same label cleanup.
        return pd.DataFrame(rows[1:], columns=document_ingestion.dedupe_columns(rows[0]))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The extracted table is malformed (ragged rows): {exc}",
        ) from exc


def _merge_features(
    derived: dict, overrides: dict
) -> tuple[CreditScoreRequest, dict]:
    """Statement evidence wins, then caller overrides, then documented fallbacks.

    Returns the request and a record of everything that did NOT come from the
    statement, so the response can show exactly what was assumed.
    """
    supplied: dict = {}
    merged = dict(derived)

    for name, fallback in _FALLBACKS.items():
        if name in merged:
            continue
        if overrides.get(name) is not None:
            merged[name] = overrides[name]
            supplied[name] = {"value": overrides[name], "source": "caller"}
        else:
            merged[name] = fallback
            supplied[name] = {"value": fallback, "source": "default"}

    try:
        return CreditScoreRequest(**merged), supplied
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Derived features failed validation: {exc}",
        ) from exc


@app.post("/analyze-statement", response_model=StatementScoreResponse)
def analyze_statement(
    file: UploadFile = File(..., description="Bank or platform payout statement."),
    age: Optional[int] = Form(None),
    platform_customer_rating: Optional[float] = Form(None),
    active_platform_hours_per_week: Optional[int] = Form(None),
    primary_gig_platform: Optional[str] = Form(None),
) -> StatementScoreResponse:
    """Ingests a statement, derives what it evidences, and scores the result.

    Form fields cover the facts no statement contains (age, rating, hours) and
    override inference where the caller knows better. The response reports the
    source of every feature so a decision can be audited back to its evidence.
    """
    overrides = {
        "age": age,
        "platform_customer_rating": platform_customer_rating,
        "active_platform_hours_per_week": active_platform_hours_per_week,
        "primary_gig_platform": primary_gig_platform,
    }

    with _parsed_upload(file) as parsed:
        table = _tabulate(parsed)

        try:
            insights = statement_features.derive_features(table)
        except statement_features.StatementParseError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc

        applicant, supplied = _merge_features(insights.derived, overrides)

        # A ledger needs dates; a statement without them still scores on derived
        # features, it just cannot produce the per-metric breakdown.
        metric_analysis = None
        try:
            records = statement_features.to_transaction_records(table)
            metric_analysis = _metric_analysis(
                records,
                applicant.platform_customer_rating,
                insights.evidence.get("opening_balance", 0.0),
            )
        except statement_features.StatementParseError as exc:
            insights.warnings.append(f"Per-metric breakdown unavailable: {exc}")
        except HTTPException as exc:
            insights.warnings.append(f"Per-metric breakdown unavailable: {exc.detail}")

        return StatementScoreResponse(
            statement_analysis=StatementAnalysis(
                source_format=parsed.get("source_format", "unknown"),
                extraction_method=parsed.get("extraction_method"),
                derived_features=insights.derived,
                supplied_features=supplied,
                unresolved_features=insights.unresolved,
                evidence=insights.evidence,
                warnings=insights.warnings,
            ),
            features_used=applicant,
            score=_score(applicant),
            metric_analysis=metric_analysis,
        )


# --------------------------------------------------------------------------- #
# Micro-insurance
# --------------------------------------------------------------------------- #


@app.post("/recommend-insurance", response_model=InsuranceRecommendation)
def recommend_insurance(payload: InsuranceRequest) -> dict:
    """Ranks micro-insurance cover for one worker's risk profile and job type.

    Reads the same risk bands as the scoring and pricing paths, so the tier a
    worker is quoted a loan at is the tier their insurance advice assumes.
    """
    return insurance_advisor.recommend(
        credit_score=payload.credit_score,
        employment_type=payload.employment_type,
        average_weekly_payout=payload.average_weekly_payout,
        resilience_stash_balance=payload.resilience_stash_balance,
        active_platform_hours_per_week=payload.active_platform_hours_per_week,
        payout_volatility_index=payload.payout_volatility_index,
        age=payload.age,
        risk_tier=payload.risk_tier,
    )


# --------------------------------------------------------------------------- #
# Corporate financial statements
# --------------------------------------------------------------------------- #


@app.post("/analyze-financials", response_model=FinancialAnalysisResponse)
def analyze_financials(
    file: UploadFile = File(..., description="Annual report or financial statements."),
) -> dict:
    """Extracts Revenue, PAT, EBITDA, Net Worth, Debt, D/E and DSCR from accounts.

    Shares the ingestion cascade with statement upload, so bordered and
    borderless PDF tables, scanned pages needing OCR, Excel, CSV, Word and text
    all arrive here already parsed. What differs is the reading: this looks for
    a set of accounts rather than a transaction ledger.

    Every figure comes back labelled `reported`, `derived` or `unavailable`, and
    a figure that could not be established is null rather than zero.
    """
    with _parsed_upload(file) as parsed:
        analysis = financial_statements.analyze_document(
            text=parsed.get("text", ""),
            tables=parsed.get("tables"),
            dataframe=parsed.get("dataframe"),
        )
        return {
            "source_format": parsed.get("source_format", "unknown"),
            "extraction_method": parsed.get("extraction_method"),
            **analysis.as_dict(),
        }


@app.post("/estimate-financials", response_model=FinancialAnalysisResponse)
def estimate_financials(payload: FinancialEstimateRequest) -> dict:
    """Estimates the same figures from GSTR-3B turnover and bank flows.

    The path for a borrower with no audited accounts, which is most of them.
    Balance-sheet figures come back unavailable rather than approximated: there
    is no honest way to infer equity from a record of cash movements.
    """
    analysis = financial_statements.estimate_from_operations(
        gst_taxable_turnover=payload.gst_taxable_turnover,
        bank_rows=[row.model_dump() for row in payload.bank_rows],
        period_months=payload.period_months,
    )
    return {"source_format": "estimated", "extraction_method": None, **analysis.as_dict()}


if __name__ == "__main__":
    # Distinct default port: backend/main.py already owns 8000.
    uvicorn.run("main:app", host="0.0.0.0", port=config.PORT, reload=True)
