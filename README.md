# GigSave

Prototype implementation for the gig-worker resilience savings workflow. AltCred is used as a structural baseline for modular auth, API boundaries, validation, health checks, and deployment practices, while this MVP keeps the financial rules dependency-light.

## Current vertical slice

- `frontend/`: editable architecture/workflow prototype
- `backend/savings.py`: deterministic financial functions plus `SavingsEngine` event orchestration
- `backend/test_savings.py`: unit tests for calculations, event processing, thresholds, and authorization
- `backend/requirements.txt`: explicit no-dependency Python service baseline

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
```

## Test

```powershell
python -m unittest discover -s backend -p "test_*.py"
```

The prototype deliberately leaves provider adapters, NestJS HTTP endpoints, PostgreSQL persistence, signed webhook verification, mTLS termination, encrypted secrets, and native mobile screens as the next integration layer. The calculation and event-orchestration boundary is tested and ready to be called by those adapters.
