# GigSave

Prototype implementation for the gig-worker resilience savings workflow: automatic
micro-savings for gig workers, plus an alternative credit score built from
gig-work signals rather than a salary history.

## Architecture

Three services, one database. Everything server-side is Python/FastAPI, and all
persistence is Supabase PostgreSQL.

| Service | Path | Port | Responsibility |
|---|---|---|---|
| Financial API | `backend/` | 8000 | Webhook ingestion, round-ups, income smoothing, sweeps, dashboard |
| ML scoring | `ml_service/` | 8001 | Hybrid rule + RandomForest credit score with SHAP explanations |
| Dashboard | `frontend/dashboard/` | 5173 | React/Vite UI, reads both services over HTTP |

```text
backend/savings.py        Pure financial calculations (round-up, moving average, sweep rules)
backend/webhooks.py       Webhook auth (HMAC-SHA256), validation, deterministic event ids
backend/db_service.py     Ledger persistence, pending-contribution replay, sweep execution
backend/models.py         SQLAlchemy models: users, transactions, savings_sweeps
backend/database.py       Supabase engine + session factory (DATABASE_URL only)
backend/main.py           FastAPI app: /health, /api/*, /webhooks/*
ml_service/schemas.py         Pydantic contracts (8 gig features)
ml_service/scoring_rules.py   Deterministic 0-800 rule engine and score bands
ml_service/model_pipeline.py  Synthetic training set, RandomForest, top-3 SHAP factors
ml_service/main.py            FastAPI app: /health, /predict-credit-score
frontend/dashboard/src/       Dashboard UI; every figure comes from a live service
```

## Workflow

1. **Secure onboarding:** obtain time-bound AA consent and authorize a capped UPI
   AutoPay mandate.
2. **Read-only ingestion:** bank debits and platform payouts arrive at
   `POST /webhooks/transaction`, authenticated with an HMAC-SHA256 signature over
   the raw body (or a shared secret header).
3. **Dual engine:** a ₹132 debit rounds up to the next ₹50 for an ₹18
   contribution; a payout contributes 10% of however much it exceeds the rolling
   30-payout average.
4. **Authorize and execute:** contributions accumulate in the ledger until they
   clear the ₹100 minimum and sit under the mandate cap, then a sweep is written
   and the transactions it consumed are marked swept.
5. **Resilience and relief:** the stash balance, pending total, and sweep history
   drive the dashboard.

Contributions accumulate in `transactions.status` rather than in a separate
counter, so the pending balance is always re-derivable from the ledger rows and
can never drift away from them.

## Running it

Copy `.env.example` to `.env` and set `DATABASE_URL` (and `WEBHOOK_SECRET` if you
want the webhook endpoints open). Then:

```bash
docker compose up --build
```

Or run the services directly:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt
.venv\Scripts\python backend\main.py          # http://127.0.0.1:8000/docs

py -3.11 -m venv .venv_ml
.venv_ml\Scripts\pip install -r ml_service\requirements.txt
.venv_ml\Scripts\python ml_service\main.py    # http://127.0.0.1:8001/docs

cd frontend\dashboard
npm install
npm run dev                                    # http://127.0.0.1:5173
```

Both requirements files are pinned for **Python 3.11** (what the Dockerfiles use).
`numpy` 1.26 and `shap` 0.46 publish no wheels for 3.13+, so a newer interpreter
will try to build them from source.

The dashboard needs all three vars in `frontend/dashboard/.env.example`. It has no
local fallback data: a missing var or an unreachable service renders an error,
never a placeholder number.

## Test

```powershell
python -m unittest discover -s backend -p "test_*.py"
.venv_ml\Scripts\python -m pytest ml_service -q
cd frontend\dashboard; npx tsc --noEmit; npm run build
```

## Not yet built

Real bank/platform provider adapters, mTLS termination, an OAuth 2.0 gateway,
encrypted secrets storage, authentication (the dashboard reads one fixed
`VITE_DASHBOARD_USER_ID`), and a gig-platform connector for the six worker
attributes in `frontend/dashboard/src/config.ts`.
