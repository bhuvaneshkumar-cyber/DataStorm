# GigSave

Financial resilience for gig workers: automatic micro-savings, income smoothing,
and an alternative credit score built from gig-work signals — platform payouts,
work consistency, spending behaviour — instead of a salary history or a CIBIL
record.

<!--
SCREENSHOT: hero / dashboard overview
docs/screenshots/dashboard.png
-->
![Dashboard overview](docs/screenshots/dashboard.png)

---

## Table of contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [Project structure](#project-structure)
- [Screenshots](#screenshots)
- [Getting started](#getting-started)
- [Environment variables](#environment-variables)
- [Testing](#testing)
- [API reference](#api-reference)
- [Not yet built](#not-yet-built)

---

## What it does

| Capability | Description |
|---|---|
| **Automatic savings** | Round-up on debits (₹132 → next ₹50, ₹18 saved) and income smoothing (10% of a payout above the rolling 30-payout average) accumulate into a Resilience Stash. |
| **Alternative credit score** | A hybrid rule engine + RandomForest model scores a worker on 8 gig-work features, with SHAP-based explanations for every score. |
| **Statement scoring** | Upload a bank/payout statement (PDF, CSV, Excel, Word, TXT) and the ML service derives income, volatility, and savings behaviour directly from it — no manual entry required. |
| **Emergency loans** | Short-term credit offers priced off the alternative score, with risk grade, interest rate, and credit limit computed per applicant. |
| **Micro-insurance** | Insurance products ranked by the risks a worker's gig actually exposes them to. |
| **Tax estimates** | Presumptive-tax and slab estimates for gig income. |
| **Business accounts** | Uploaded financial statements broken down into metrics and ratios. |
| **Credit-policy bot** | Q&A over the platform's lending and scoring policy. |
| **Webhook ingestion** | Bank debits and platform payouts land at `POST /webhooks/transaction`, authenticated with an HMAC-SHA256 signature. |

---

## Architecture

Three services, one database. Everything server-side is Python/FastAPI, and all
persistence is Supabase PostgreSQL.

| Service | Path | Port | Responsibility |
|---|---|---|---|
| Financial API | `backend/` | 8000 | Auth, webhook ingestion, round-ups, income smoothing, sweeps, loans, tax, insurance, bot |
| ML scoring | `ml_service/` | 8001 | Hybrid rule + RandomForest credit score, statement ingestion, SHAP explanations |
| Dashboard | `frontend/dashboard/` | 5173 | React/Vite UI, reads both services over HTTP |

```
                     ┌─────────────────────┐
                     │   Dashboard (5173)  │
                     │   React + Vite      │
                     └──────────┬──────────┘
                                │  HTTPS (browser)
                 ┌──────────────┴───────────────┐
                 ▼                               ▼
     ┌───────────────────────┐       ┌───────────────────────┐
     │  Financial API (8000) │──────▶│  ML Scoring (8001)     │
     │  FastAPI               │ HTTP  │  FastAPI               │
     │  auth · webhooks       │ (int) │  scoring · statements  │
     │  savings · loans       │       │  SHAP explanations     │
     │  tax · insurance       │       └───────────────────────┘
     └───────────┬────────────┘
                 │
                 ▼
     ┌───────────────────────┐
     │  Supabase PostgreSQL   │
     └───────────────────────┘
```

Inside Docker, the financial API reaches the scorer over the compose network
(`ML_SERVICE_URL=http://ml_service:8001`); the browser reaches both services
over `localhost`, since Docker service names mean nothing to it.

---

## Project structure

```
backend/
├── main.py             FastAPI app: /health, /api/*, /webhooks/*
├── bootstrap.py         Idempotent schema sync (create/alter tables on boot)
├── database.py          Supabase engine + session factory (DATABASE_URL only)
├── models.py            SQLAlchemy models: users, transactions, sweeps, loans, platforms
├── savings.py           Pure financial calculations (round-up, moving average, sweep rules)
├── webhooks.py          Webhook auth (HMAC-SHA256), validation, deterministic event ids
├── db_service.py        Ledger persistence, pending-contribution replay, sweep execution
├── scoring_client.py    HTTP client to the ML service, with typed unavailability errors
├── loan_policy.py        Loan eligibility and pricing rules
├── tax_rules.py          Presumptive-tax and slab calculations
├── policy_kb.py          Knowledge base backing the credit-policy bot
└── routers/              auth, transactions, platforms, credit, loans, insurance, tax, bot

ml_service/
├── main.py                  FastAPI app: /health, /predict-credit-score, /analyze-statement
├── schemas.py                Pydantic contracts (8 gig features)
├── scoring_rules.py           Deterministic 0-800 rule engine and score bands
├── model_pipeline.py          Synthetic training set, RandomForest, top-3 SHAP factors
├── credit_metrics.py          Per-metric breakdown (income, spending, liquidity, stability)
├── risk_policy.py             Risk grade, interest rate, credit limit
├── insurance_advisor.py       Micro-insurance ranking
├── statement_features.py      Derives income/volatility/savings from a raw statement
├── document_ingestion.py      PDF/OCR/CSV/Excel/Word parsing
└── financial_statements.py    Business-account metric analysis

frontend/dashboard/src/
├── pages/     Dashboard, Expenses, Platforms, Credit, Loans, Insurance, Tax,
│              Financials, Settings, SignIn, SignUp, LenderDashboard
├── lib/       api.ts (every endpoint), client.ts (transport, auth, errors), types.ts
└── auth/      AuthContext (session/token handling)
```

---

## Screenshots

Drop PNGs into `docs/screenshots/` with the filenames below — each is already
wired into this README and will render automatically once the file exists.

| Area | File | Preview |
|---|---|---|
| Sign in | `docs/screenshots/signin.png` | ![Sign in](docs/screenshots/signin.png) |
| Dashboard overview | `docs/screenshots/dashboard.png` | ![Dashboard](docs/screenshots/dashboard.png) |
| Alternative credit score | `docs/screenshots/credit.png` | ![Credit](docs/screenshots/credit.png) |
| Statement upload & scoring | `docs/screenshots/credit-statement.png` | ![Statement scoring](docs/screenshots/credit-statement.png) |
| Emergency loans | `docs/screenshots/loans.png` | ![Loans](docs/screenshots/loans.png) |
| Micro-insurance | `docs/screenshots/insurance.png` | ![Insurance](docs/screenshots/insurance.png) |
| Expenses | `docs/screenshots/expenses.png` | ![Expenses](docs/screenshots/expenses.png) |
| Platforms | `docs/screenshots/platforms.png` | ![Platforms](docs/screenshots/platforms.png) |
| Tax estimate | `docs/screenshots/tax.png` | ![Tax](docs/screenshots/tax.png) |
| Business accounts | `docs/screenshots/financials.png` | ![Financials](docs/screenshots/financials.png) |
| API docs (`/docs`) | `docs/screenshots/api-docs.png` | ![API docs](docs/screenshots/api-docs.png) |

**Multi-language sign-in** — English, Hindi, and Tamil, switchable from the
sign-in screen itself:

| English | Hindi | Tamil |
|---|---|---|
| ![Sign in (English)](docs/screenshots/signin.png) | ![Sign in (Hindi)](docs/screenshots/signin-hindi.png) | ![Sign in (Tamil)](docs/screenshots/signin-tamil.png) |

Until an image exists at a given path, GitHub/most Markdown viewers show a
broken-image icon in its place — that's expected and harmless.

---

## Getting started

### Docker (recommended)

```bash
cp .env.example .env      # fill in DATABASE_URL at minimum
docker compose up --build
```

| URL | Service |
|---|---|
| http://localhost:5173 | Dashboard |
| http://localhost:8000/docs | Financial API (Swagger) |
| http://localhost:8001/health | ML scoring service |

### Running services directly

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

Both requirements files are pinned for **Python 3.11** (what the Dockerfiles
use) — `numpy` 1.26 and `shap` 0.46 publish no wheels for 3.13+, so a newer
interpreter will try to build them from source.

---

## Environment variables

| Variable | Where | Purpose |
|---|---|---|
| `DATABASE_URL` | root `.env` | Supabase Postgres connection string. Required — there is no local/SQLite fallback. |
| `WEBHOOK_SECRET` | root `.env` | HMAC secret for `/webhooks/*`. Left unset, webhook endpoints stay closed (fail shut). |
| `ML_SERVICE_URL` | `docker-compose.yml` | How the financial API reaches the scorer *inside Docker* (`http://ml_service:8001`, the compose service name — not `localhost`). |
| `VITE_BACKEND_URL` | `frontend/dashboard/.env` | Browser-facing financial API URL. Must be host-reachable, not a Docker service name. |
| `VITE_ML_URL` | `frontend/dashboard/.env` | Browser-facing ML service URL, for direct statement uploads. |

A special character (like `@`) in a Postgres password must be URL-encoded
(`@` → `%40`) inside `DATABASE_URL`, or the connection string parses wrong.

---

## Testing

```powershell
python -m unittest discover -s backend -p "test_*.py"
.venv_ml\Scripts\python -m pytest ml_service -q
cd frontend\dashboard; npx tsc --noEmit; npm run build
```

---

## API reference

- Interactive Swagger UI: `http://localhost:8000/docs` (financial API) and
  `http://localhost:8001/docs` (ML service).
- Full request/response contracts: [`API_CONTRACT.md`](API_CONTRACT.md).

---

## Not yet built

Real bank/platform provider adapters, mTLS termination, an OAuth 2.0 gateway,
and encrypted secrets storage.
