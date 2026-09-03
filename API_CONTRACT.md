# DataStrom Financial Engine API Contract

This document provides the integration contract for connecting Frontend and Mobile clients (Teammates 3 & 4) to the Python backend and live Supabase PostgreSQL database.

---

## 1. Overview & Connection Info

* **Base URL (Local Development):** `http://localhost:8000`
* **Interactive API Documentation (Swagger):** `http://localhost:8000/docs`
* **Alternative API Documentation (ReDoc):** `http://localhost:8000/redoc`
* **Authentication:** No client API keys or authorization headers required for hackathon MVP endpoints.
* **CORS Status:** **Enabled** (`allow_origins=["*"]`, all methods and headers allowed). Frontend web apps can call the API directly without CORS proxy issues.

---

## 2. Supported vs. Unsupported Operations

| Operation | Supported? | Method & Endpoint | Description |
| :--- | :---: | :--- | :--- |
| **Check Backend Health** | **YES** | `GET /health` | Live connection test to Supabase PostgreSQL |
| **Fetch Transactions** | **YES** | `GET /api/transactions` | Query recent user debits and payouts |
| **Ingest Transaction** | **YES** | `POST /api/transactions` | Record transaction and calculate sweep decision |
| **Fetch Sweeps** | **YES** | `GET /api/sweeps` | Query authorized/executed savings sweeps |
| **Authorize/Create Sweep** | **YES** | `POST /api/sweeps` | Insert an authorized sweep record |
| **Fetch User Dashboard** | **YES** | `GET /api/users/{user_id}/dashboard` | Total stash balance, 30d baseline income, recent sweeps |
| **Update Transaction** | **NO** | *N/A* | *Currently not implemented* |
| **Update Sweep** | **NO** | *N/A* | *Currently not implemented* |

---

## 3. Endpoint Specifications

### 3.1 `GET /health`
Validates that the API server is operational and actively connected to Supabase PostgreSQL.

* **Method:** `GET`
* **URL:** `/health`
* **Query Parameters:** None
* **Success Response (`200 OK`):**
```json
{
  "service_status": "healthy",
  "database": {
    "status": "connected",
    "result": 1,
    "database_url_configured": true
  }
}
```
* **Failure Response (`503 Service Unavailable`):**
```json
{
  "service_status": "degraded",
  "database": {
    "status": "error",
    "error": "Connection error details",
    "database_url_configured": true
  }
}
```

---

### 3.2 `GET /api/transactions`
Fetches a list of historical bank transactions and payouts.

* **Method:** `GET`
* **URL:** `/api/transactions`
* **Query Parameters:**
  * `user_id` *(optional, UUID string)*: Filter transactions for a specific user.
  * `limit` *(optional, integer, default: 50)*: Number of records to return.
* **Success Response (`200 OK`):**
```json
[
  {
    "id": "4c744655-6ddf-4cdf-96e2-5b777345af90",
    "user_id": "c666bc75-751c-4e4b-866b-af5b0393d131",
    "amount": 97.0,
    "transaction_type": "UPI",
    "merchant": "Amazon",
    "status": "completed",
    "timestamp": "2026-09-03T12:34:29.386935"
  }
]
```

---

### 3.3 `POST /api/transactions`
Ingests a bank transaction (debit or platform payout), runs it through the deterministic `SavingsEngine`, and returns the calculation decision.

* **Method:** `POST`
* **URL:** `/api/transactions`
* **Headers:** `Content-Type: application/json`
* **Request Body:**
```json
{
  "user_id": "c666bc75-751c-4e4b-866b-af5b0393d131",
  "amount": 132.0,
  "transaction_type": "debit",
  "merchant": "Swiggy",
  "threshold": 100.0,
  "mandate_limit": 1000.0
}
```
* **Success Response (`201 Created`):**
```json
{
  "transaction_id": "5992405a-c7b8-4c35-be43-e427b11cd071",
  "amount": 132.0,
  "transaction_type": "debit",
  "sweep_decision": {
    "amount": 18.0,
    "eligible": false,
    "reason": "minimum threshold not reached"
  }
}
```
* **Validation Error (`400 Bad Request`):**
```json
{
  "detail": "transaction_type must be 'debit' or 'platform_payout'"
}
```

---

### 3.4 `GET /api/sweeps`
Fetches a list of authorized or executed savings sweeps.

* **Method:** `GET`
* **URL:** `/api/sweeps`
* **Query Parameters:**
  * `user_id` *(optional, UUID string)*: Filter sweeps for a specific user.
  * `limit` *(optional, integer, default: 50)*: Number of records to return.
* **Success Response (`200 OK`):**
```json
[
  {
    "id": "518450a1-3e3b-4063-a56f-b5152a5ed2e5",
    "user_id": "c666bc75-751c-4e4b-866b-af5b0393d131",
    "transaction_id": "4c744655-6ddf-4cdf-96e2-5b777345af90",
    "sweep_amount": 3.0,
    "reason": "Round-up savings",
    "created_at": "2026-09-03T12:38:18.328005"
  }
]
```

---

### 3.5 `POST /api/sweeps`
Records an authorized savings sweep directly in the database.

* **Method:** `POST`
* **URL:** `/api/sweeps`
* **Headers:** `Content-Type: application/json`
* **Request Body:**
```json
{
  "user_id": "c666bc75-751c-4e4b-866b-af5b0393d131",
  "sweep_amount": 18.0,
  "transaction_id": "5992405a-c7b8-4c35-be43-e427b11cd071",
  "reason": "UPI AutoPay sweep authorized"
}
```
* **Success Response (`201 Created`):**
```json
{
  "sweep_id": "f339fee2-7deb-45e8-b1cb-5cf456fefc12",
  "user_id": "c666bc75-751c-4e4b-866b-af5b0393d131",
  "sweep_amount": 18.0,
  "reason": "UPI AutoPay sweep authorized",
  "created_at": "2026-09-03T14:37:44.123456"
}
```

---

### 3.6 `GET /api/users/{user_id}/dashboard`
Aggregates user savings summary for instant mobile/frontend dashboard rendering.

* **Method:** `GET`
* **URL:** `/api/users/{user_id}/dashboard`
* **Path Parameters:**
  * `user_id` *(required, UUID string)*: The unique ID of the user.
* **Success Response (`200 OK`):**
```json
{
  "user_id": "c666bc75-751c-4e4b-866b-af5b0393d131",
  "total_stash_balance": 3.0,
  "income_30d_baseline": 0.0,
  "recent_sweeps": [
    {
      "id": "518450a1-3e3b-4063-a56f-b5152a5ed2e5",
      "sweep_amount": 3.0,
      "reason": "Round-up savings",
      "transaction_id": "4c744655-6ddf-4cdf-96e2-5b777345af90",
      "created_at": "2026-09-03T12:38:18.328005"
    }
  ]
}
```

---

## 4. Scoring Service (separate process, port 8001)

The credit-scoring service runs alongside the financial engine on its own port
with its own CORS, because the browser calls it directly (`VITE_ML_URL`).

* **Base URL (Local Development):** `http://localhost:8001`
* **Swagger:** `http://localhost:8001/docs`

| Operation | Method & Endpoint | Description |
| :--- | :--- | :--- |
| **Service health** | `GET /health` | Model status plus which document formats this deployment can parse |
| **Score an applicant** | `POST /predict-credit-score` | Hybrid rule + ML score, SHAP drivers, and a risk assessment |
| **Score a statement** | `POST /analyze-statement` | Upload a statement, derive features, score the result |
| **Score a ledger** | `POST /analyze-transactions` | Per-metric breakdown and coaching from raw transactions |

### 4.1 `POST /predict-credit-score`

Body is the 8 gig features (see `ml_service/schemas.py`). The response adds a
`risk_assessment` object to the existing score fields — this is **additive**,
so existing clients that ignore it keep working:

```json
{
  "final_score": 664.12,
  "category": "Good",
  "confidence": 0.87,
  "rule_score": 725.0,
  "ml_score": 623.53,
  "ml_available": true,
  "explanation": [{ "feature": "resilience_stash_balance", "impact": 0.14, "direction": "positive" }],
  "risk_assessment": {
    "risk_grade": { "code": "GS-1", "label": "Minimal Risk" },
    "risk_tier": "MODERATE",
    "decision": "APPROVE",
    "indicative_interest_rate_pct": 17.5,
    "risk_premium_bps": 350,
    "max_credit_limit_inr": 79672.0,
    "recommended_tenor_months": 12,
    "conditions": ["Quarterly re-verification of platform payout statements"],
    "early_warning_signals": []
  },
  "latency_ms": 12.4
}
```

`decision` is bound to the same thresholds as `category`: `Good` maps to
APPROVE, `Standard` to REFER, `Poor` to DECLINE.

### 4.2 `POST /analyze-statement`

* **Content-Type:** `multipart/form-data`
* **Fields:**
  * `file` *(required)*: the statement. `.pdf`, `.csv`, `.xlsx`, `.xls`, `.xlsm`, `.docx`, `.doc`, `.txt`. Max 25 MB.
  * `age`, `platform_customer_rating`, `active_platform_hours_per_week`, `primary_gig_platform` *(all optional)*: facts a statement cannot contain, or overrides for what was inferred.

* **Success Response (`200 OK`):**
```json
{
  "statement_analysis": {
    "source_format": "csv",
    "extraction_method": null,
    "derived_features": {
      "average_weekly_payout": 4425.0,
      "completed_gigs_per_week": 1,
      "payout_volatility_index": 0.037,
      "resilience_stash_balance": 17200.0,
      "primary_gig_platform": "Food Delivery"
    },
    "supplied_features": {
      "age": { "value": 31, "source": "caller" },
      "active_platform_hours_per_week": { "value": 40, "source": "default" }
    },
    "unresolved_features": ["age", "platform_customer_rating", "active_platform_hours_per_week"],
    "evidence": {
      "columns_detected": { "credit": "Credit", "debit": "Debit", "balance": "Closing Balance", "date": "Txn Date", "narration": "Narration" },
      "payout_rows": 5,
      "total_credited": 17700.0,
      "statement_days": 28,
      "period_start": "2026-01-01",
      "period_end": "2026-01-28",
      "weeks_observed": 5
    },
    "warnings": []
  },
  "features_used": { "...": "the full CreditScoreRequest that was scored" },
  "score": { "...": "same shape as POST /predict-credit-score" }
}
```

* **Error responses:**

| Status | Meaning |
| :---: | :--- |
| `400` | The uploaded file is empty |
| `413` | File exceeds the 25 MB limit |
| `415` | Unsupported file extension |
| `422` | Parsed, but no transaction table / no credit column / no positive credits |
| `503` | The parser for this format is not installed in this deployment (check `GET /health`) |

The response also carries a `metric_analysis` block (same shape as §4.3). It is
`null` when the statement had no usable date column, since a ledger cannot be
built without dates — the feature score is still returned, and the reason
appears in `statement_analysis.warnings`.

---

### 4.3 `POST /analyze-transactions`

Scores a raw ledger and explains it metric by metric. Source-agnostic: bank
rows, platform payout feeds and manual entries all score through this path once
expressed as standardized transactions.

* **Headers:** `Content-Type: application/json`
* **Request Body:**
```json
{
  "transactions": [
    { "date": "2026-03-02", "type": "credit", "amount": 780.5, "category": "swiggy", "source": "platform" },
    { "date": "2026-03-05", "type": "debit",  "amount": 7000.0, "category": "rent",   "source": "manual" }
  ],
  "platform_rating": 4.2,
  "opening_balance": 12000
}
```
  * `transactions` *(required, ≥1)*: `date` is ISO `YYYY-MM-DD`; `type` is `credit` or `debit`; `amount` is non-negative.
  * `platform_rating` *(optional, 1.0-5.0)*: used for gig stability; falls back to length of earning history.
  * `opening_balance` *(optional)*: balance before the first row. Without it the liquidity metrics measure cumulative net cash flow, which understates anyone who started the period with money.

* **Success Response (`200 OK`):**
```json
{
  "credit_score": 673.4,
  "composite_score": 84.18,
  "category_scores": {
    "income_quality": 74.5,
    "spending_behavior": 92.0,
    "liquidity": 100.0,
    "gig_stability": 70.0
  },
  "category_weights": { "income_quality": 35, "spending_behavior": 30, "liquidity": 20, "gig_stability": 15 },
  "metrics": {
    "avg_monthly_income": {
      "name": "avg_monthly_income",
      "value": 18787.54,
      "score": 40.0,
      "status": "Low Income",
      "description": "Average monthly credits. Raw earning capacity."
    }
  },
  "strengths": ["Liquidity is strong (100/100)"],
  "weaknesses": [],
  "recommended_actions": ["Add a second platform so one deactivation cannot end all income."],
  "coverage": {
    "transactions": 81, "credits": 78, "debits": 3,
    "months_observed": 3, "period_start": "2026-03-02", "period_end": "2026-05-30"
  },
  "risk_grade": { "code": "GS-1", "label": "Minimal Risk" }
}
```

`credit_score` is on the same 0-800 scale as `/predict-credit-score`, and
`risk_grade` comes from the same `risk_policy` bands, so the two paths can never
disagree about what a score means. Pricing is deliberately absent here: it needs
applicant facts (age, rating, hours) that a ledger does not contain.

* **Error responses:**

| Status | Meaning |
| :---: | :--- |
| `422` | Empty ledger, or a row with a bad date, type or amount — the message names the row index |

---

## 5. Instructions for Teammates 3 & 4

1. **How to run backend locally for frontend testing:**
   ```powershell
   cd backend
   python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```
2. **Calling from Frontend (JavaScript Fetch example):**
   ```javascript
   const API_BASE = "http://localhost:8000";

   // Fetch dashboard data
   async function loadDashboard(userId) {
     const response = await fetch(`${API_BASE}/api/users/${userId}/dashboard`);
     const data = await response.json();
     console.log("Stash Balance:", data.total_stash_balance);
     return data;
   }
   ```
3. **Data Types & Conventions:**
   * All IDs (`user_id`, `transaction_id`, `id`) are standard UUID strings (e.g. `c666bc75-751c-4e4b-866b-af5b0393d131`).
   * Financial amounts (`amount`, `sweep_amount`, `total_stash_balance`) are floating-point numbers in INR.
   * `transaction_type` expects either `"debit"` or `"platform_payout"`.
