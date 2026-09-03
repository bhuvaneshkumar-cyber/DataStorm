# GigSave – Node.js Backend (`backend/node/`)

> **Phase 3 – Backend & Fintech Logic Lead**
> Node.js port of the savings engine originally prototyped in `backend/savings.py`.
> The Python prototype is **reference-only** — do not modify it.

---

## Folder layout

```
backend/
├── savings.py          ← Python prototype (REFERENCE ONLY – do not touch)
├── test_savings.py     ← Python tests     (REFERENCE ONLY – do not touch)
└── node/               ← All Node.js work lives here
    ├── src/
    │   ├── config/
    │   │   ├── index.js        env + constants loader (dotenv)
    │   │   └── db.js           Mongoose connection helper
    │   ├── models/
    │   │   ├── Transaction.js  Mongoose schema – debit / platform_payout events
    │   │   └── SavingsAccount.js Mongoose schema – per-user pending state
    │   ├── services/
    │   │   └── savingsEngine.js  Core savings logic (round-up, income smoothing, sweep decision)
    │   ├── listeners/
    │   │   └── webhookListener.js  Inbound webhook handler (HMAC verify -> process -> persist)
    │   ├── routes/
    │   │   └── webhookRoutes.js    Express router – POST /webhooks/*
    │   ├── utils/
    │   │   └── index.js        Shared helpers
    │   ├── app.js              Express app factory + middleware wiring
    │   └── server.js           HTTP server entry point (reads PORT from env)
    ├── tests/                  Jest test suite (mirrors test_savings.py cases)
    ├── .env.example            Environment variable template
    ├── .gitignore
    ├── package.json            Exact-pinned dependencies (no ^ or ~)
    └── README.md               ← you are here
```

---

## Business logic (ported from `savings.py`)

| Function | Rule |
|---|---|
| `roundUp(amount, multiple=50)` | `(50 - amount % 50) % 50` – e.g. ₹132 → ₹18 round-up |
| `movingAverage(values, window=30)` | Mean of last 30 elements; empty → 0 |
| `incomeSurplus(current, history, pct=0.10)` | `max(0, current − avg) × pct`, 2 d.p. |
| `sweepDecision(roundups, surplus, threshold=100, mandateLimit=1000)` | eligible iff total ∈ [₹100, ₹1000] |
| `SavingsEngine` | Stateful accumulator; `process()` adds events; `authorizeAndReset()` clears on sweep |

---

## Quick start

### Prerequisites
- Node.js ≥ 18
- MongoDB running locally **or** an Atlas connection string

### 1 – Configure environment

```bash
# from backend/node/
cp .env.example .env
# Edit .env – set MONGO_URI and any other values
```

### 2 – Install dependencies

```bash
# from backend/node/
npm install
```

### 3 – Start the dev server (auto-restarts on file changes)

```bash
npm run dev
```

The server starts on `http://localhost:3001` (override via `PORT` in `.env`).

Verify it is running:

```bash
curl http://localhost:3001/health
# {"status":"ok","service":"gigsave-backend-node"}
```

### 4 – Run tests

```bash
npm test
```

---

## Available npm scripts

| Script | Command | Purpose |
|---|---|---|
| `npm start` | `node src/server.js` | Production start |
| `npm run dev` | `nodemon src/server.js` | Dev server with hot-reload |
| `npm test` | `jest --runInBand --forceExit` | Run Jest test suite |

---

## Important constraints

- **Do NOT modify** `backend/savings.py` or `backend/test_savings.py`.
- **Do NOT touch** the `frontend/` folder.
- Keep all Phase 3 work inside `backend/node/`.
- Dependency versions are **exact-pinned** in `package.json` — do not add `^` or `~` ranges without team sign-off.
