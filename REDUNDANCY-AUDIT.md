# Redundancy and Integrity Audit

## Consolidation pass — 2026-09-03

Backend standardised on Python/FastAPI + Supabase PostgreSQL. MongoDB and Node
are gone from the repository.

| Entry | Finding | Decision |
|---|---|---|
| `backend/node/` | Express + MongoDB service duplicating `backend/savings.py`: a second savings engine, a second set of models, a second webhook contract, a second test suite. | **Deleted.** Its webhook ingestion, HMAC verification, and pending-contribution accumulation were ported to `backend/webhooks.py` and `backend/db_service.py`. |
| `frontend/index.html`, `app.js`, `styles.css` | Static editable architecture board. A design artifact, not part of the product. | **Deleted.** |
| `frontend/dashboard/src/data/financial-data.ts` | Hardcoded snapshot the dashboard fell back to whenever a service was unreachable, so a dead backend still rendered a full, plausible dashboard. | **Deleted.** The UI now surfaces the failure. |
| `frontend/dashboard/find_quotes.py` | One-off scratch script for fixing quote escaping in `App.tsx`. | **Deleted.** |
| AI Coach card, demo-state menu, notification/profile popovers | Not part of micro-savings or credit scoring; all driven by hardcoded strings. | **Deleted**, along with their now-orphaned CSS (~4 kB off the bundle). |
| Sidebar `AI Insights` / `Resilience` / `Settings` / `Profile` | Navigation to features that do not exist. | **Deleted.** Nav is now Dashboard, Stash, Transactions, Credit. |
| `db_service.process_transaction_event` | Duplicated `add_transaction` and mis-scoped the threshold (`10.0` vs `100.0` elsewhere); rebuilt the engine per event, so accumulated round-ups could never reach the sweep threshold. | **Replaced** by `process_webhook_event`, which replays the unswept ledger tail. |
| `Resilience-Dashboard-1/` | Separate Replit project with its own `.git`, reappeared as an untracked directory. Previously removed as a broken gitlink. | **Left on disk, added to `.gitignore`** so it is not committed as an embedded repository. Not ours to delete. |
| `savings.SavingsEngine` / `savings.Transaction` | In-memory accumulator with its own copy of the pending-contribution semantics. Nothing imported it once the ledger replay landed; keeping it meant two implementations that could disagree. | **Deleted.** `savings.py` is now pure functions only. |
| `backend/`, `ml_service/`, `frontend/dashboard/` | Distinct runtime responsibilities. | Retained. |

### Verification

- `python -m unittest discover -s backend` — **29 pass** (7 savings rules,
  22 webhook auth/validation/ledger-replay).
- `pytest ml_service` — **6 pass**, including new checks that the synthetic
  features are correlated and in-schema, that held-out accuracy clears its floor,
  and that SHAP degrades to an empty explanation instead of a 500.
- Model held-out accuracy **0.901**, against a measured Bayes ceiling of ~0.92
  for the calibrated label noise — the model is at the ceiling, not underfitting.
- FastAPI app imports and exposes 9 routes; `/webhooks/transaction` smoke-tested
  end to end for valid signature (200), bad signature (401), no credentials (401),
  and malformed body (400).
- `npx tsc --noEmit` and `npm run build` — clean; bundle CSS 20.4 kB → 16.5 kB.
- `pip install --dry-run --only-binary=:all: --python-version 3.11` resolves both
  requirements files individually and together, with no conflict between
  `scikit-learn`, `numpy`, `pandas`, and `fastapi`.

## Prior pass — `main` / `test-branch` merge, 2026-09-03

| Entry | Finding | Decision |
|---|---|---|
| `DataStorm-test-branch/` | Nested duplicate snapshot of the root prototype files; not used by any package or test. | Removed from the merge and ignored. |
| `frontend/dashboard/dist/` | Generated Vite output, reproducible by the dashboard build. | Removed from the merge and ignored. |
| `Resilience-Dashboard-1` | Gitlink with no `.gitmodules` mapping and no resolvable object. | Removed as a broken repository entry. |

`git fsck --full --no-reflogs` completed without dangling or corrupt objects.
