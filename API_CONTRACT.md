# DataStrom Financial Engine — API Contract

Two services. The **financial engine** (`:8000`) owns identity and everything
persisted about a person; the **scoring service** (`:8001`) owns the models and
the document parsers and holds no user data at all.

The dashboard talks to both: the engine for everything account-shaped, the
scorer directly for file uploads so a statement never has to exist in two
places.

---

## 1. Connection

| | Financial engine | Scoring service |
|---|---|---|
| Default base URL | `http://localhost:8000` | `http://localhost:8001` |
| Interactive docs | `/docs` | `/docs` |
| Health | `GET /health` | `GET /health` |
| Auth | Bearer JWT on every `/api/*` route | none (stateless, holds nothing) |
| Persistence | Supabase PostgreSQL | none |

The engine also calls the scorer server-to-server (`ML_SERVICE_URL`). That is
deliberate: **a credit score is never accepted from the browser.** Anything a
loan is granted against is derived on the server from the applicant's own
recorded evidence.

---

## 2. Authentication

Register or sign in, then send `Authorization: Bearer <access_token>` on every
subsequent request. Tokens are HS256, signed with `JWT_SECRET`, and expire after
`JWT_TTL_HOURS` (default 12).

One credential store serves both audiences, separated by `role`:

| Role | Reaches |
|---|---|
| `worker` | transactions, sweeps, platforms, credit, loans, insurance, tax |
| `lender` | the loan queue and the decision route |

Both reach `/api/auth/*` and `/api/policy-bot/*`. Cross-role access is `403`,
not `404`: the caller is authenticated and the route exists, they are simply on
the wrong side of the product. `role` is fixed at registration and cannot be
changed through the API.

### `POST /api/auth/register` → `201`

```jsonc
{
  "name": "Meena S",
  "email": "meena@example.com",
  "password": "at-least-8-characters",
  "role": "worker",              // or "lender"; defaults to worker
  "language": "ta",              // en | hi | ta
  "phone": "9876543210",         // optional
  "employment_type": "Swiggy delivery partner",  // optional, drives insurance advice
  "date_of_birth": "1996-05-14"  // optional; without it the score assumes age 30
}
```

Returns `{ access_token, token_type, expires_in_hours, user }`. `409` if the
email is taken.

### `POST /api/auth/login`

`{ email, password, expected_role? }`. `expected_role` pins the request to one
door, so a worker signing in at the lender portal gets a clear `403` rather than
an empty dashboard.

A wrong password and an unknown email return the **same** `401` message, so the
form cannot be used to enumerate accounts.

### `GET /api/auth/me` · `PATCH /api/auth/me`

Read or update the caller's own profile. The patch accepts `name`, `phone`,
`language`, `employment_type`, `date_of_birth` — and silently ignores anything
else, including `role`.

---

## 3. Money (worker)

### `GET /api/transactions?limit=50`

The caller's own rows, newest first. Never anyone else's.

### `POST /api/transactions` → `201`

```jsonc
{
  "amount": 132.0,
  "transaction_type": "debit",   // or "platform_payout"
  "merchant": "HP Petrol",       // optional
  "category": "Fuel",            // optional; drives the expense breakdown only
  "threshold": 100.0,            // optional, minimum sweep size
  "mandate_limit": 1000.0        // optional, UPI AutoPay cap
}
```

Returns the row plus the sweep it *would* trigger:

```jsonc
{
  "transaction_id": "…",
  "amount": 132.0,
  "transaction_type": "debit",
  "sweep_decision": { "amount": 18.0, "eligible": false, "reason": "minimum threshold not reached" }
}
```

The sweep is **advised, not executed**. Money leaving an account is never a side
effect of recording that it arrived; authorizing is a separate call.

### `GET /api/expenses/summary?window_days=90`

Everything the expense tracker charts, aggregated server-side so the tax and
credit paths quote the same numbers:

```jsonc
{
  "window_days": 90,
  "total_income": 112800.0, "total_expense": 23520.0, "net": 89280.0,
  "daily":   [{ "period": "2026-03-15", "income": 9000, "expense": 1960, "net": 7040 }],
  "monthly": [{ "period": "2026-03",    "income": 9000, "expense": 1960, "net": 7040 }],
  "expense_categories": [{ "category": "Fuel", "total": 15840, "share_pct": 67.3 }],
  "income_sources":     [{ "category": "Swiggy", "total": 112800, "share_pct": 100.0 }],
  "transaction_count": 37
}
```

Rows with no timestamp are excluded from both the totals and the series, so the
two can never disagree.

### `GET /api/sweeps?limit=50` · `POST /api/sweeps` → `201`

`{ "sweep_amount": 118.0, "transaction_id": null, "reason": "…" }`

### `GET /api/dashboard`

`{ user_id, total_stash_balance, income_30d_baseline, recent_sweeps[] }` for the
caller. (The old `/api/users/{user_id}/dashboard` is **gone** — a user id in the
path is an invitation to read someone else's finances by editing the URL.)

---

## 4. Platforms (worker)

Connecting a platform is how "I drive for Uber" becomes evidence a lender can
price.

| Route | Does |
|---|---|
| `GET /api/platforms` | the caller's connections |
| `POST /api/platforms` → `201` | connect one; `409` if already connected (case-insensitive) |
| `PATCH /api/platforms/{id}` | revise its figures |
| `DELETE /api/platforms/{id}` → `204` | disconnect; `404` for a row that is not yours |
| `GET /api/platforms/income-profile` | the eight scored features, derived |

Body: `{ platform, account_handle?, customer_rating?, weekly_payout?, gigs_per_week?, hours_per_week? }`.
A connection starts `verified: false` — the figures are a declaration until a
logged payout corroborates them.

`income-profile` collapses connections *plus* the logged ledger into what the
scorer wants, and names every value that fell back to a default:

```jsonc
{
  "primary_gig_platform": "Food Delivery",
  "platform_customer_rating": 4.8,
  "average_weekly_payout": 9400.0,
  "completed_gigs_per_week": 58,
  "active_platform_hours_per_week": 44,
  "payout_volatility_index": 0.11,
  "resilience_stash_balance": 25000.0,
  "age": 30,
  "connected_platforms": 1, "verified_platforms": 0,
  "assumptions": ["No date of birth on file; age assumed to be 30."]
}
```

**Measured beats declared:** if the ledger can support a figure, it wins over the
number typed into a connection form.

---

## 5. Credit (worker)

### `GET /api/credit/score`

`{ profile, score }` — the income profile above, and the hybrid score derived
from it. `503` if the scoring service is unreachable: an approximate score would
end up written onto a loan application as though it were an assessment.

### `GET /api/credit/metrics`

The per-metric breakdown of the caller's own logged ledger — the same analysis a
statement upload produces, without needing a statement. `422` when there are no
dated transactions yet.

### Statement upload

Goes **straight to the scoring service** (§8), not through the engine.

---

## 6. Loans

### Worker

| Route | Does |
|---|---|
| `GET /api/loans/eligibility` | may I apply, and on what terms |
| `GET /api/loans` | my applications, newest first |
| `POST /api/loans` → `201` | apply |

`POST` takes **only** `{ amount, tenor_months, purpose? }`. The score is derived
server-side and frozen onto the row; a body that could name its own score could
name 800.

- `409` — an application is already awaiting a decision.
- `422` — the terms are not available (below threshold, over the ceiling, tenor
  too long). Well-formed request, permitted caller, unavailable terms.

Eligibility is answerable *before* the form appears, so someone below the
threshold reads why rather than collecting a rejection.

### Lender

| Route | Does |
|---|---|
| `GET /api/loans/queue?status=pending` | the queue, **oldest first** |
| `PATCH /api/loans/{id}` | `{ status: "approved" \| "rejected", lender_note? }` |

A lender sees the score, its grade, the indicative rate, the amount and tenor,
and the applicant's name — **never the raw statement or transaction list.** The
score shown is the one frozen at application time, so a later drift cannot
rewrite the basis of a decision. Deciding twice is `409`.

---

## 7. Insurance, tax, and the policy bot

| Route | Does |
|---|---|
| `GET /api/insurance/recommendations` | cover ranked by this worker's real exposures |
| `GET /api/tax/summary?presumptive=true&deductions=0` | estimated liability from logged income |
| `GET /api/policy-bot/topics` | what the bot can answer |
| `POST /api/policy-bot/ask` | `{ question, language }` → an answer, or an honest "I don't know" |

The tax figure is an estimate annualised from the days observed, assuming a
resident individual under 60 on the new regime with section 44AD presumptive
taxation. It is not a filing and not advice; `notes[]` says so and lists every
assumption.

The bot answers from a curated policy base, not a language model. Every number
it quotes matches the code that enforces it. Below a confidence threshold it
returns `confident: false` with suggested topics rather than guessing.

---

## 8. Scoring service (`:8001`)

Stateless and unauthenticated. Holds no user data; uploaded files are deleted
before the response returns.

| Route | Does |
|---|---|
| `GET /health` | liveness, model mode, and which parsers are installed |
| `POST /predict-credit-score` | score one fully specified applicant |
| `POST /analyze-transactions` | score a ledger, explained metric by metric |
| `POST /analyze-statement` | upload a bank/payout statement, derive and score |
| `POST /recommend-insurance` | rank cover for a risk profile |
| `POST /analyze-financials` | Revenue, PAT, EBITDA, net worth, debt, D/E, DSCR from accounts |
| `POST /estimate-financials` | the same figures from GSTR-3B turnover + bank flows |

### `POST /analyze-statement` (multipart)

`file` plus optional `age`, `platform_customer_rating`,
`active_platform_hours_per_week`, `primary_gig_platform` — the facts no
statement contains. The response reports the **source of every feature**
(statement, caller, or documented default) so a decision can be audited back to
its evidence.

Formats: PDF (bordered and borderless tables, with OCR fallback for scans), CSV,
Excel, Word, plain text. Up to 25 MB. Parsers are optional dependencies; a
core-only install answers `503` here with a clear message rather than failing to
start, and `GET /health` reports what a deployment can actually read.

### `POST /analyze-financials` (multipart)

Same ingestion cascade, read as a set of accounts rather than a ledger. Every
figure is labelled by how it was reached:

| `source` | Means |
|---|---|
| `reported` | stated outright in the document |
| `derived` | reconstructed from figures that were (EBITDA from PBT + interest + depreciation) |
| `estimated` | inferred from GSTR-3B and bank flows |
| `unavailable` | could not be established — `value` is `null`, **never `0`** |

Indian reporting conventions are handled natively: `(Rs. in lakhs)` scale
headers, `1,23,456.78` grouping, `(1,234.56)` accounting negatives, and `Cr`
meaning *credit* rather than *crore*.

### `POST /estimate-financials`

`{ gst_taxable_turnover?, bank_rows[], period_months }` for a borrower with no
audited accounts. Balance-sheet figures come back `unavailable` rather than
approximated: there is no honest way to infer equity from a record of cash
movements, and a D/E ratio built on a guess is worse than no ratio.

---

## 9. Error conventions

Both services answer with FastAPI's `{"detail": …}`, either a string or a list
of per-field validation errors. The dashboard unwraps both, so a user sees
"amount must be greater than 0" rather than "HTTP 422".

| Status | Means |
|---|---|
| `401` | no token, or it expired — the app signs out and returns to sign-in |
| `403` | authenticated, but on the wrong side of the product |
| `404` | no such row, **or** a row that is not yours (confirming an id exists is itself a leak) |
| `409` | a conflict with existing state (duplicate email, second open application, deciding twice) |
| `413` / `415` | upload too large / unsupported file type |
| `422` | well-formed but unprocessable (validation, or terms not available) |
| `503` | a dependency is down — the database, or the scoring service. Retryable. |
