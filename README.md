# GigSave

Prototype implementation for the gig-worker resilience savings workflow. AltCred is used as a structural baseline for modular auth, API boundaries, validation, health checks, and deployment practices, while this MVP keeps the financial rules dependency-light.

## Current vertical slice

- `frontend/`: editable architecture/workflow prototype
- `backend/savings.py`: deterministic financial functions plus `SavingsEngine` event orchestration
- `backend/test_savings.py`: unit tests for calculations, event processing, thresholds, and authorization
- `backend/requirements.txt`: explicit no-dependency Python service baseline
- `ml_service/`: FastAPI hybrid credit-scoring service (rules 40% + RandomForest 60%, SHAP explanations)

## Current Workflow

1. **Secure onboarding:** register in the React Native client, obtain time-bound AA consent, and authorize a capped UPI AutoPay mandate.
2. **Read-only ingestion:** receive bank debit and platform-payout webhooks through an OAuth 2.0, mTLS, TLS 1.3 gateway.
3. **Dual engine:** round a debit such as ₹132 up to the nearest ₹50 contribution of ₹18; calculate payout surplus against a rolling 30-day average.
4. **Authorize and execute:** aggregate pending contributions, require the ₹100 minimum, enforce the mandate cap, and execute the exact approved AutoPay amount.
5. **Resilience and relief:** hold funds in the Resilience Stash, show balance and sweep history, and return an immediate withdrawal to the primary bank account during a lean week.

## Prototype Structure

```text
frontend/                 Editable architecture and workflow board
backend/savings.py        Domain calculations and SavingsEngine orchestration
backend/test_savings.py   Unit tests for the financial workflow
backend/requirements.txt  Dependency declaration (standard library only)
ml_service/schemas.py     Pydantic request/response contracts (8 gig features)
ml_service/scoring_rules.py  Deterministic 0-800 rule engine and score bands
ml_service/model_pipeline.py RandomForest training, inference, top-3 SHAP factors
ml_service/main.py        FastAPI app: GET /health, POST /predict-credit-score
ml_service/test_scoring.py Rule ordering, hybrid math, and ML-failure fallback
```

## Scoring Service

Hybrid score = `rule_score * 0.4 + ml_score * 0.6`, both on a 0-800 scale. If the
model is unavailable or prediction raises, the response degrades to 100% rule-based
(`ml_available: false`) rather than failing the request.

```powershell
.venv_ml\Scripts\pip install -r ml_service\requirements.txt
py -3.12 -m venv .venv_ml
.venv_ml\Scripts\python ml_service\main.py   # http://127.0.0.1:8000/docs
```

Pinned for Python 3.11/3.12 - `scikit-learn` and `numpy` 1.26 have no 3.14 wheels.

## Test

```powershell
python -m unittest discover -s backend -p "test_*.py"
.venv_ml\Scripts\python -m pytest ml_service -q
```

The prototype deliberately leaves provider adapters, NestJS HTTP endpoints, PostgreSQL persistence, signed webhook verification, mTLS termination, encrypted secrets, and native mobile screens as the next integration layer. The calculation and event-orchestration boundary is tested and ready to be called by those adapters.
