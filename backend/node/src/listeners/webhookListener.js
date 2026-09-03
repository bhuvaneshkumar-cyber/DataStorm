'use strict';
/**
 * webhookListener.js
 * ──────────────────
 * Processes inbound bank-adapter and gig-platform webhook payloads.
 *
 * This module is intentionally kept transport-agnostic: it receives a plain
 * payload object and returns a plain { statusCode, body } result. The Express
 * route (webhookRoutes.js) owns the HTTP layer and calls this function — that
 * separation makes the logic testable without spinning up an HTTP server.
 *
 * Exported:
 *   handleTransactionWebhook(payload) → Promise<{ statusCode, body }>
 */

const crypto      = require('crypto');
const Transaction = require('../models/Transaction');
const { processContribution } = require('../services/savingsEngine');

// ---------------------------------------------------------------------------
// Required payload fields — checked on every inbound webhook.
// ---------------------------------------------------------------------------
const REQUIRED_FIELDS = ['userId', 'type', 'amount', 'source', 'timestamp'];

// Valid transaction types — must match Transaction schema enum.
const VALID_TYPES = ['debit', 'payout'];

// ---------------------------------------------------------------------------
// handleTransactionWebhook
// ---------------------------------------------------------------------------

/**
 * Processes a single inbound webhook payload end-to-end.
 *
 * Steps:
 *   1. Validate required fields and value constraints.
 *   2. Derive a stable transactionId (use payload.transactionId if provided,
 *      otherwise generate a deterministic SHA-256 hash from userId + source +
 *      timestamp so the same real-world event always maps to the same ID).
 *   3. Idempotency check — if this transactionId already exists in DB with
 *      status "processed", return 200 immediately without re-processing.
 *   4. Upsert the Transaction document with status "pending" (upsert guards
 *      against a race condition where two concurrent webhook deliveries for
 *      the same event both pass the idempotency check before either saves).
 *   5. Call processContribution() from savingsEngine — it handles the math
 *      (round-up for debits, income smoothing for payouts), updates
 *      SavingsStash, and marks the Transaction processed internally.
 *   6. On engine success  → return 200 with the engine result.
 *      On engine failure  → mark Transaction "failed", return 500.
 *   7. On unexpected throw → mark Transaction "failed" (best-effort), log,
 *      return 500. Never lets an exception escape this function.
 *
 * @param {object} payload  Raw parsed request body from the webhook POST.
 * @param {string}  payload.userId        Application user UUID.
 * @param {string}  payload.type          "debit" | "payout".
 * @param {number}  payload.amount        Transaction amount in INR (must be >= 0).
 * @param {string}  payload.source        Human-readable origin, e.g. "HDFC Bank".
 * @param {string}  payload.timestamp     ISO 8601 date-time string of the event.
 * @param {string}  [payload.transactionId]  External stable ID; generated if absent.
 * @param {object}  [payload.rawPayload]  Forwarded verbatim for audit storage.
 *
 * @returns {Promise<{ statusCode: number, body: object }>}
 */
async function handleTransactionWebhook(payload) {
  // ── Step 1: Validate required fields ──────────────────────────────────────
  const missing = REQUIRED_FIELDS.filter(
    (f) => payload[f] === undefined || payload[f] === null || payload[f] === ''
  );
  if (missing.length > 0) {
    return {
      statusCode: 400,
      body: { error: `Missing required fields: ${missing.join(', ')}` },
    };
  }

  if (!VALID_TYPES.includes(payload.type)) {
    return {
      statusCode: 400,
      body: { error: `Invalid type "${payload.type}". Must be one of: ${VALID_TYPES.join(', ')}` },
    };
  }

  const amount = Number(payload.amount);
  if (!Number.isFinite(amount) || amount < 0) {
    return {
      statusCode: 400,
      body: { error: `Invalid amount "${payload.amount}". Must be a non-negative number.` },
    };
  }

  const eventTimestamp = new Date(payload.timestamp);
  if (isNaN(eventTimestamp.getTime())) {
    return {
      statusCode: 400,
      body: { error: `Invalid timestamp "${payload.timestamp}". Must be a valid ISO 8601 date-time.` },
    };
  }

  // ── Step 2: Derive a stable transactionId ─────────────────────────────────
  // If the upstream system provides a transaction ID, use it as-is.
  // Otherwise generate a deterministic SHA-256 digest from the fields that
  // uniquely identify the real-world event — so retried webhook deliveries
  // for the same bank event always produce the same ID and are deduplicated.
  const transactionId = payload.transactionId
    ? String(payload.transactionId)
    : crypto
        .createHash('sha256')
        .update(`${payload.userId}|${payload.source}|${payload.timestamp}|${amount}`)
        .digest('hex');

  // ── Step 3: Idempotency check ─────────────────────────────────────────────
  // If this transaction was already fully processed, return early without
  // touching the savings engine or writing any new DB documents.
  let existingTx = null;
  try {
    existingTx = await Transaction.findOne({ transactionId });
  } catch (dbErr) {
    console.error('[webhookListener] DB error during idempotency check:', dbErr);
    return {
      statusCode: 500,
      body: { error: 'Database error during idempotency check.' },
    };
  }

  if (existingTx && existingTx.status === 'processed') {
    return {
      statusCode: 200,
      body: { message: 'already processed', transactionId },
    };
  }

  // ── Step 4: Upsert Transaction with status "pending" ──────────────────────
  // Using findOneAndUpdate with upsert:true so that if two concurrent webhook
  // deliveries race past the idempotency check above, only one will win the
  // upsert (MongoDB's atomicity guarantee on findOneAndUpdate).
  let txDoc;
  try {
    txDoc = await Transaction.findOneAndUpdate(
      { transactionId },
      {
        $setOnInsert: {
          transactionId,
          userId:     payload.userId,
          type:       payload.type,
          amount,
          source:     payload.source,
          timestamp:  eventTimestamp,
          status:     'pending',
          isProcessed: false,
          rawPayload: payload.rawPayload ?? payload,
        },
      },
      { upsert: true, new: true, setDefaultsOnInsert: true }
    );
  } catch (dbErr) {
    console.error('[webhookListener] DB error saving pending transaction:', dbErr);
    return {
      statusCode: 500,
      body: { error: 'Failed to save transaction record.' },
    };
  }

  // ── Step 5 & 6: Call savingsEngine.processContribution ───────────────────
  // processContribution handles all savings math (round-up for debits,
  // income smoothing for payouts), SavingsStash updates, IncomeProfile
  // updates, and marks the Transaction document processed — all in one call.
  // It never throws; it always returns { success, swept, sweptAmount,
  // newBalance, pendingAfter, reason, wasCapped }.
  try {
    const engineResult = await processContribution({
      userId:      payload.userId,
      transaction: { transactionId }, // engine re-fetches the full doc by transactionId
    });

    if (!engineResult.success) {
      // The engine returned a structured failure (e.g. no SavingsStash for user).
      // Mark the DB record "failed" so ops/support can identify it.
      await _markFailed(transactionId, engineResult.reason);
      console.error(
        `[webhookListener] Engine failure for ${transactionId}:`,
        engineResult.reason
      );
      return {
        statusCode: 500,
        body: { error: engineResult.reason },
      };
    }

    // Engine succeeded — Transaction is already marked "processed" by the engine.
    return {
      statusCode: 200,
      body: {
        transactionId,
        swept:        engineResult.swept,
        sweptAmount:  engineResult.sweptAmount,
        newBalance:   engineResult.newBalance,
        pendingAfter: engineResult.pendingAfter,
        reason:       engineResult.reason,
        wasCapped:    engineResult.wasCapped,
      },
    };

  } catch (unexpectedErr) {
    // This catch exists purely as a safety net — processContribution is
    // documented to never throw. If it ever does (e.g. Mongoose version
    // incompatibility), we catch it here, record the failure, and return 500.
    console.error('[webhookListener] Unexpected error in processContribution:', unexpectedErr);
    await _markFailed(transactionId, unexpectedErr.message);
    return {
      statusCode: 500,
      body: { error: 'Internal processing error. Transaction marked failed for replay.' },
    };
  }
}

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------

/**
 * Marks a Transaction document as failed in the database.
 * Best-effort: logs but does not throw if the update itself fails.
 *
 * @param {string} transactionId
 * @param {string} reason  Error message for logging/debugging.
 */
async function _markFailed(transactionId, reason) {
  try {
    await Transaction.findOneAndUpdate(
      { transactionId },
      { $set: { status: 'failed', isProcessed: false } }
    );
  } catch (err) {
    console.error(
      `[webhookListener] Could not mark transaction ${transactionId} as failed:`,
      err.message,
      '| Original failure reason:',
      reason
    );
  }
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

module.exports = { handleTransactionWebhook };
