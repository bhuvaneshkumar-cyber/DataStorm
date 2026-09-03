# GigSave

Prototype implementation for the gig-worker resilience savings workflow. AltCred is used as a structural baseline for modular auth, API boundaries, validation, health checks, and deployment practices, while this MVP keeps the financial rules dependency-light.

## Current vertical slice

- `frontend/`: editable architecture/workflow prototype
- `backend/savings.py`: deterministic financial functions plus `SavingsEngine` event orchestration
- `backend/test_savings.py`: unit tests for calculations, event processing, thresholds, and authorization
- `backend/requirements.txt`: explicit no-dependency Python service baseline
- `ml_service/`: FastAPI hybrid credit-scoring service (rules 40% + RandomForest 60%, SHAP explanations), risk-based pricing, and multi-format statement ingestion
- `backend/node/`: Express + MongoDB port of the savings engine, with HMAC-verified webhook ingestion

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
ml_service/config.py      Env-overridable score bands, pricing, upload limits
ml_service/schemas.py     Pydantic request/response contracts (8 gig features)
ml_service/scoring_rules.py  Deterministic 0-800 rule engine and score bands
ml_service/model_pipeline.py RandomForest training, inference, top-3 SHAP factors
ml_service/risk_policy.py Grade, decision, pricing, covenants, early warnings
ml_service/document_ingestion.py PDF/CSV/Excel/DOCX parsing with OCR fallback
ml_service/statement_features.py Indian money parsing, statement -> gig features + ledger
ml_service/metric_definitions.py Scoring bands and weights for the metric engine
ml_service/credit_metrics.py Transaction ledger -> per-metric scores and coaching
ml_service/main.py        FastAPI app: /health, /predict-credit-score,
                          /analyze-statement, /analyze-transactions
ml_service/test_scoring.py Rule ordering, hybrid math, and ML-failure fallback
ml_service/test_statement_ingestion.py Money parsing, derivation, pricing, uploads
ml_service/test_credit_metrics.py Bands, metric behaviour, ledger validation

frontend/dashboard/src/App.tsx            Shell, view routing, live dashboard
frontend/dashboard/src/pages/CreditAnalysis.tsx  Statement upload and results
frontend/dashboard/src/lib/api.ts         Typed client for both services
```

## Scoring Service

Hybrid score = `rule_score * 0.4 + ml_score * 0.6`, both on a 0-800 scale. If the
model is unavailable or prediction raises, the response degrades to 100% rule-based
(`ml_available: false`) rather than failing the request.

```powershell
py -3.12 -m venv .venv_ml
.venv_ml\Scripts\pip install -r ml_service\requirements.txt -r ml_service\requirements-ingestion.txt
.venv_ml\Scripts\python ml_service\main.py   # http://127.0.0.1:8001/docs
```

Pinned for Python 3.11/3.12 - `scikit-learn` and `numpy` 1.26 have no 3.14 wheels.

### Risk assessment

Every score carries a `risk_assessment`: a GS-1..GS-8 grade, an
APPROVE/REFER/DECLINE decision, an indicative rate (base + risk premium in bps),
a credit limit as a multiple of monthly payout, covenants, and Early Warning
Signals naming the specific fragility behind the number — thin savings buffer,
erratic income, platform standing, unsustainable hours. Decision boundaries are
the same constants as the public score bands, so a `Good` applicant can never
come back declined. All of it is tunable from `ml_service/.env` — see
`ml_service/.env.example`.

### Statement ingestion

`POST /analyze-statement` accepts a bank or platform payout statement as PDF,
CSV, Excel, DOCX or text, derives the features it can actually evidence, and
scores the result:

| Derived from the statement | Must be supplied by the caller |
|---|---|
| `average_weekly_payout`, `payout_volatility_index` | `age` |
| `completed_gigs_per_week`, `resilience_stash_balance` | `platform_customer_rating` |
| `primary_gig_platform` (from credit narrations) | `active_platform_hours_per_week` |

The response reports the source of every feature — statement, caller, or
documented default — plus the columns detected and the period covered, so a
decision can be audited back to its evidence. Features the statement cannot
support are listed under `unresolved_features` rather than invented.

Parsing handles what Indian statements actually contain: `1,23,456.78` digit
grouping, `(1,234.56)` accounting negatives, `Rs.`/`₹` prefixes, `2.5 Lakh`
scale words, and `Cr` meaning *credit* rather than *crore*. PDF extraction
cascades from bordered tables to borderless, then block-sorted text, then OCR
for scans.

Those parsers live in `requirements-ingestion.txt` and are **optional** — every
import is guarded, so a core-only install still runs and `/analyze-statement`
answers 503 with a clear message instead of the service failing to start.
`GET /health` reports which formats a deployment can parse. OCR additionally
needs the `tesseract-ocr` system binary, already in the `ml_service` image.

### Transaction metrics

`POST /analyze-transactions` scores a raw ledger instead of summary features,
and explains the result metric by metric. It answers a different question from
`/predict-credit-score`:

| | `/predict-credit-score` | `/analyze-transactions` |
|---|---|---|
| Input | 8 summarised features | A transaction ledger |
| Answers | *How* creditworthy | *Why*, metric by metric |
| Output | Score, SHAP drivers, pricing | Category scores, 14 metrics with status bands, coaching |

Fourteen metrics across four weighted categories — income quality (35%),
spending behaviour (30%), liquidity (20%), gig stability (15%) — each scored
0-100 against bands in `metric_definitions.py`, then composited onto the same
0-800 scale so `risk_policy` grades both paths identically. Weakest metrics
drive an ordered list of actions the worker can actually take.

The engine is source-agnostic: anything expressible as
`{date, type, amount, category, source}` can be scored. `/analyze-statement`
therefore returns a `metric_analysis` block too — one upload yields both the
feature score and the metric breakdown.

## Dashboard

```powershell
cd frontend/dashboard; npm install; npm run dev    # http://localhost:5173
```

Two live views, switched from the sidebar:

- **Dashboard** — stash, sweeps and score pulled from the backend and scoring
  service. If either is unreachable the sample snapshot still renders, with a
  banner saying the numbers are not live rather than passing them off as fresh.
- **Credit** — upload a statement and see the score, the underwriting decision,
  every metric with its status, the coaching actions, and a provenance panel
  showing which values came from the statement, which you supplied, and which
  fell back to a default.

Nav entries that are not built yet render an explicit placeholder instead of a
dead button. Set `VITE_BACKEND_URL`, `VITE_ML_URL` and `VITE_DEMO_USER_ID` in
`frontend/dashboard/.env.local` to point at running services.

## Test

```powershell
cd backend; python -m unittest discover -s . -p "test_*.py"   # 6 tests
.venv_ml\Scripts\python -m pytest ml_service -q              # 52 tests
cd backend/node; npm install; npm test                        # 51 tests
```

The prototype deliberately leaves real bank/platform provider adapters, mTLS termination, an OAuth 2.0 gateway, encrypted secrets storage, and native mobile screens as the next integration layer — see `checkpoint.md` for the current status and what's left. The calculation and event-orchestration boundary (`backend/savings.py` and its Node port `backend/node/src/services/savingsEngine.js`) is tested and wired up end-to-end: `backend/node` now has a real Express server with an HMAC-verified `/webhooks/transaction` and `/webhooks/sweep`, backed by MongoDB via Mongoose.
