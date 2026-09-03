# GigSave

Implementation baseline for the gig-worker resilience savings workflow. The repository uses the AltCred project structure as a reference for modular auth, API boundaries, validation, health checks, and deployment practices, while keeping this MVP dependency-light.

## Current vertical slice

- `frontend/`: editable architecture/workflow prototype
- `backend/savings.py`: deterministic round-up, 30-day income smoothing, and sweep authorization functions
- `backend/test_savings.py`: unit tests for the financial rules
- `backend/requirements.txt`: explicit no-dependency Python service baseline

## Workflow

1. Onboard with regulated Account Aggregator consent and a capped UPI AutoPay mandate.
2. Receive read-only bank debit and platform-income events through a secure gateway.
3. Calculate expense round-ups and income surplus buffers.
4. Aggregate savings and authorize sweeps only after threshold and mandate-limit checks.
5. Move funds to the Resilience Stash and support instant withdrawal to the primary account.

## Test

```powershell
python -m unittest discover -s backend -p "test_*.py"
```

The next production slice should add NestJS APIs, PostgreSQL persistence, provider sandbox adapters, signed webhook validation, mTLS termination, encrypted secrets, and React Native screens around these tested calculation functions.
