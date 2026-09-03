# GigSave

Credit for gig workers, built from the work they already do.

A delivery rider with three years of steady earnings and no CIBIL file is
invisible to a lender. This scores them on what they *can* evidence — platform
payouts, spending habits, a savings buffer — and gives a lender enough to price
that risk without ever handing over the raw statement behind it.

## What it does

**For workers**

| | |
|---|---|
| **Authentication** | JWT sign-in and registration, in English, Hindi or Tamil. The language follows the account, not the browser. |
| **Expense tracker** | Log income and spending; cash-flow charts, category splits, and the round-up each entry produces. |
| **Platform management** | Connect the apps you earn on. Those connections are the evidence the score is built on. |
| **Alternative credit** | A 0–800 score with no bureau record: 40% transparent rules, 60% model, with SHAP drivers and a per-metric breakdown of *why*. |
| **Micro insurance** | Cover ranked by the risks your work actually carries, each with the reason it placed there. |
| **Tax summary** | Estimated liability annualised from logged income, under the new regime with section 44AD. |
| **Emergency loans** | Apply once the score clears the threshold — eligibility is answerable before you fill in a form. |
| **Policy bot** | Docked on every signed-in screen, answering from published policy in your own language. |
| **Business accounts** | Revenue, PAT, EBITDA, net worth, debt, D/E and DSCR read straight out of filed accounts — or estimated from GSTR-3B and bank flows when there are none. |

**For lenders**

A separate sign-in onto the same credential store, a queue of incoming
applications oldest-first, and each one shown with the score, its risk grade, the
indicative rate and the early warning signals behind it. Approve or reject with
a note. **A lender never sees the applicant's statement or transaction list** —
the decision is about risk, and the raw ledger buys no better decision at a real
privacy cost.

## Two ideas the whole thing rests on

**Nothing is scored from the browser.** A loan application carries the score it
was judged on, so the backend derives that score server-side from the
applicant's own recorded evidence and freezes it onto the row. A request that
could name its own credit score could name 800.

**An unknown is never dressed up as a number.** Every derived figure carries its
provenance — read from the document, supplied by the caller, or a documented
default. A figure that cannot be established comes back `null`, never `0`: a
DSCR of 0.0 reads as "cannot service its debt" and a DSCR of `null` reads as "we
do not know", and those must not be confused.

## Architecture

```text
frontend/dashboard/     React + Vite dashboard, both portals
backend/                FastAPI: identity, money, platforms, loans, tax, bot
backend/node/           Express + MongoDB port of the savings engine, HMAC webhooks
ml_service/             FastAPI: scoring models, document ingestion, financial analysis
```

The scoring service holds no user data and no session. The backend calls it
server-to-server; the browser calls it directly only to upload a document, which
it parses in memory and deletes before answering.

<details>
<summary>Module map</summary>

```text
backend/security.py           PBKDF2 password hashing, JWT issue/verify
backend/deps.py               who is calling, and may they
backend/models.py             users, transactions, sweeps, platforms, loans
backend/bootstrap.py          idempotent schema sync at startup
backend/analytics.py          cash-flow aggregation (pure)
backend/income_profile.py     connections + ledger -> the 8 scored features (pure)
backend/loan_policy.py        who may borrow, how much, how long (pure)
backend/tax_rules.py          Indian slabs, 87A, 44AD, cess, GST (pure)
backend/policy_kb.py          the bot's knowledge base and retriever
backend/scoring_client.py     server-to-server calls to the scorer
backend/savings.py            round-up and income-smoothing arithmetic (pure)
backend/routers/              one module per area of the product

ml_service/scoring_rules.py       deterministic 0-800 rule engine
ml_service/model_pipeline.py      RandomForest + top-3 SHAP factors
ml_service/risk_policy.py         grade, decision, pricing, covenants, warnings
ml_service/document_ingestion.py  PDF/CSV/Excel/DOCX parsing with OCR fallback
ml_service/statement_features.py  Indian money parsing, statement -> features
ml_service/credit_metrics.py      ledger -> 14 metrics across 4 weighted categories
ml_service/financial_statements.py corporate accounts: reported / derived / estimated
ml_service/insurance_advisor.py   cover ranked by employment exposure

frontend/dashboard/src/lib/client.ts   the one place the app touches the network
frontend/dashboard/src/lib/api.ts      every endpoint, one function each
frontend/dashboard/src/i18n/           en / hi / ta, typed against the English keys
frontend/dashboard/src/auth/           session, route guards
frontend/dashboard/src/components/     shell, charts, policy bot, primitives
frontend/dashboard/src/pages/          one screen each
```

</details>

## Run it

```powershell
# 1. Scoring service
py -3.12 -m venv .venv_ml
.venv_ml\Scripts\pip install -r ml_service\requirements.txt -r ml_service\requirements-ingestion.txt
.venv_ml\Scripts\python ml_service\main.py          # http://127.0.0.1:8001/docs

# 2. Financial engine
pip install -r backend\requirements.txt
copy backend\.env.example backend\.env              # set DATABASE_URL and JWT_SECRET
python backend\main.py                              # http://127.0.0.1:8000/docs

# 3. Dashboard
cd frontend\dashboard; npm install; npm run dev     # http://localhost:5173
```

Or `docker compose up` with `DATABASE_URL` and `JWT_SECRET` in a root `.env`.

`JWT_SECRET` is required in any real deployment. Without it the service mints a
random key per process — every restart signs everyone out, which is loud on
purpose. It never falls back to a hardcoded default, because a checked-in
default lets anyone mint a valid token.

The scoring service pins Python 3.11/3.12: `scikit-learn` and `numpy` 1.26 have
no 3.14 wheels. Document parsers are optional — `/analyze-statement` answers
`503` with a clear message rather than the service failing to start, and
`GET /health` reports which formats a deployment can read. OCR additionally
needs the `tesseract-ocr` binary, already in the `ml_service` image.

## Test

```powershell
cd backend; python -m unittest discover -s . -p "test_*.py"   # 38 tests
.venv_ml\Scripts\python -m pytest ml_service -q               # 71 tests
cd backend/node; npm install; npm test                        # 51 tests
cd frontend/dashboard; npm run build                          # typecheck + build
```

`backend/test_api.py` runs the real application against in-memory SQLite with
the scorer stubbed, so the authorization rules are exercised without needing
Postgres or a second process. The pure modules (`tax_rules`, `analytics`,
`income_profile`, `loan_policy`, `policy_kb`, `security`, `financial_statements`,
`insurance_advisor`) each carry a `demo()` self-check runnable as
`python <module>.py`.

## Scoring

Hybrid score = `rule_score * 0.4 + ml_score * 0.6`, both on 0–800. If the model
is unavailable the response degrades to 100% rule-based (`ml_available: false`)
rather than failing, and says so in the UI.

Every score carries a `risk_assessment`: a GS-1..GS-8 grade, an
APPROVE/REFER/DECLINE decision, an indicative rate (base + risk premium in bps),
a credit limit as a multiple of monthly payout, covenants, and Early Warning
Signals naming the specific fragility behind the number — thin savings buffer,
erratic income, platform standing, unsustainable hours. Decision boundaries are
the same constants as the public score bands, so a `Good` applicant can never
come back declined. All of it is tunable from `ml_service/.env`.

`POST /analyze-transactions` answers a different question from
`/predict-credit-score`: fourteen metrics across four weighted categories —
income quality (35%), spending behaviour (30%), liquidity (20%), gig stability
(15%) — each scored 0–100 and composited onto the same 0–800 scale, with the
weakest driving an ordered list of actions the worker can actually take.

## Charts

The palette is not a matter of taste. Both series colours were run through a
contrast and colour-vision validator in light and dark mode, and clear the
lightness band, the chroma floor, the CVD separation floor and 3:1 contrast
against their own surface. Status colours are reserved, never reused as a series
colour, and always ship with a written label — a score band is not something a
reader should have to infer from a hue. Every chart has a table view beside it.

## Still to build

Real bank and platform provider adapters, mTLS termination, an OAuth 2.0
gateway, encrypted secrets storage, and native mobile screens. The calculation
and event-orchestration boundary (`backend/savings.py` and its Node port
`backend/node/src/services/savingsEngine.js`) is tested and wired end to end:
`backend/node` has a real Express server with an HMAC-verified
`/webhooks/transaction` and `/webhooks/sweep`, backed by MongoDB via Mongoose.
