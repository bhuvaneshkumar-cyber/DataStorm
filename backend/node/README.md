# GigSave Node.js Backend

GigSave is an Express and Supabase backend for a gig-worker resilience savings
workflow. It accepts bank debit and platform payout webhooks, calculates
round-up or income-smoothing contributions, accumulates pending savings, and
authorizes a sweep when the minimum threshold and mandate cap allow it.

## Folder structure

```text
backend/node/
├── src/
│   ├── app.js                    Express app factory and health endpoint
│   ├── server.js                 HTTP server entry point
│   ├── config/                   Configuration and database placeholders
│   ├── listeners/webhookListener.js
│   ├── models/                   Supabase persistence adapters
│   ├── routes/webhookRoutes.js   Authenticated webhook routes
│   ├── services/savingsEngine.js Savings calculations and persistence flow
│   └── utils/
├── tests/                        Jest and Supertest tests
├── package.json
└── README.md
```

## Install and run

Prerequisites: Node.js 18 or newer and a Supabase project.

```powershell
cd backend/node
npm install
npm run dev
```

The development server listens on `http://localhost:3001` by default. Set
`PORT` to use another port. Use `npm start` for a non-watch start.

## Environment variables

Create `backend/node/.env` with:

```dotenv
PORT=3001
WEBHOOK_SECRET=replace-with-a-long-random-secret
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=replace-with-your-server-only-key
```

`WEBHOOK_SECRET` is required for webhook requests. `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY` enable the server-side Supabase client and report
`supabase: "configured"` on `/health`. Never expose the service-role key in
browser code. Run `supabase/001_node_savings_schema.sql` in the Supabase SQL
editor before using the Node webhook routes.

## Tests

Tests mock persistence adapters and the savings engine where appropriate, so they do
not require a running database.

```powershell
cd backend/node
npm test
```

## Webhook endpoint

`POST /webhooks/transaction` requires the `x-webhook-secret` header and a JSON
body containing `userId`, `type` (`debit` or `payout`), `amount`, `source`, and
an ISO 8601 `timestamp`. `transactionId` is optional; when omitted, the
listener derives a deterministic ID for idempotent retries.

Example request:

```http
POST /webhooks/transaction HTTP/1.1
Host: localhost:3001
Content-Type: application/json
x-webhook-secret: replace-with-a-long-random-secret

{
  "userId": "user-123",
  "type": "debit",
  "amount": 132,
  "source": "HDFC Bank",
  "timestamp": "2026-09-03T12:00:00.000Z",
  "transactionId": "bank-tx-456"
}
```

Example successful response:

```json
{
  "transactionId": "bank-tx-456",
  "swept": false,
  "sweptAmount": 0,
  "newBalance": 0,
  "pendingAfter": 18,
  "reason": "minimum threshold not reached",
  "wasCapped": false
}
```

Malformed payloads return `400`. Authentication failures return `401`, and
processing or database failures return `500` with an error message.

## Health check

`GET /health` is unauthenticated and returns `status`, process `uptime`, and an
ISO `timestamp`. It also returns `supabase` as `configured` or `not configured`.

## Demo database note

The Node savings workflow now targets Supabase PostgreSQL. Before the demo,
the team should confirm the shared Supabase project, PostgreSQL tables, service
credentials, row-level-security policy, and that the schema migration is applied.
