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
  "service_status": "healthy",
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

## 4. Instructions for Teammates 3 & 4

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
