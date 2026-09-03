# GigSave Node.js Backend

GigSave is an Express and Mongoose backend for a gig-worker resilience savings
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
│   ├── models/                   Mongoose models
│   ├── routes/webhookRoutes.js   Authenticated webhook routes
│   ├── services/savingsEngine.js Savings calculations and persistence flow
│   └── utils/
├── tests/                        Jest and Supertest tests
├── package.json
└── README.md
```

## Install and run

Prerequisites: Node.js 18 or newer and a local MongoDB instance.

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
MONGODB_URI=mongodb://127.0.0.1:27017/gigsave
```

`WEBHOOK_SECRET` is required for webhook requests. `MONGODB_URI` (or the
legacy alias `MONGO_URI`) identifies the database and enables database status
on `/health`. The current project uses local MongoDB; the database connection
helper is still being integrated into server startup.

## Tests

Tests mock Mongoose models and the savings engine where appropriate, so they do
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
ISO `timestamp`. When `MONGODB_URI` or `MONGO_URI` is configured it also
returns `db` as `connected` or `disconnected` without attempting a connection.

## Demo database note

This backend currently uses a local MongoDB setup. Before the demo, the team
must confirm a shared MongoDB Atlas connection string, credentials, network
access, and the final environment-variable name.
