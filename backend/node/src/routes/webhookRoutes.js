'use strict';
/**
 * webhookRoutes.js
 * ────────────────
 * Express router that exposes the GigSave webhook endpoints.
 *
 * All routes in this file are mounted at /webhooks by app.js, so the full
 * paths are:
 *   POST /webhooks/transaction   – bank debit or platform payout event
 *   POST /webhooks/sweep         – manual sweep trigger (admin / QA use only)
 *
 * Authentication
 * ──────────────
 * Every request must carry the header:
 *   x-webhook-secret: <value matching process.env.WEBHOOK_SECRET>
 * Requests with a missing or incorrect secret are rejected with 401 before
 * any payload parsing or DB work is attempted.
 *
 * Transport / application separation
 * ────────────────────────────────────
 * Business logic lives entirely in webhookListener.handleTransactionWebhook().
 * These route handlers are thin: authenticate → delegate → respond. This
 * keeps the listener independently testable without HTTP.
 */

const express = require('express');
const { handleTransactionWebhook } = require('../listeners/webhookListener');
const SavingsStash = require('../models/SavingsStash');
const { meetsMinimumThreshold, enforceMandateCap } = require('../services/savingsEngine');

const router = express.Router();

// ---------------------------------------------------------------------------
// Shared middleware: webhook secret authentication
// ---------------------------------------------------------------------------

/**
 * Rejects requests that do not present the correct WEBHOOK_SECRET header.
 *
 * Uses a constant-time string comparison (timingSafeEqual) to prevent
 * timing-based secret enumeration attacks.
 *
 * Responds 401 if:
 *   - The x-webhook-secret header is absent.
 *   - The header value does not match process.env.WEBHOOK_SECRET.
 *   - process.env.WEBHOOK_SECRET is not configured (server misconfiguration).
 *
 * @param {import('express').Request}  req
 * @param {import('express').Response} res
 * @param {import('express').NextFunction} next
 */
function requireWebhookSecret(req, res, next) {
  const expectedSecret = process.env.WEBHOOK_SECRET;

  if (!expectedSecret) {
    // Misconfigured server — log loudly and refuse all requests.
    console.error('[webhookRoutes] WEBHOOK_SECRET is not set in environment. Refusing request.');
    return res.status(401).json({ error: 'Webhook authentication is not configured.' });
  }

  const incomingSecret = req.headers['x-webhook-secret'];

  if (!incomingSecret) {
    return res.status(401).json({ error: 'Missing x-webhook-secret header.' });
  }

  // Constant-time comparison to prevent timing attacks.
  // Both buffers must be the same length for timingSafeEqual; if lengths
  // differ the secret is already wrong, but we still run the comparison to
  // avoid leaking length information via response time.
  const expected = Buffer.from(expectedSecret);
  const incoming = Buffer.from(incomingSecret);
  const match =
    expected.length === incoming.length &&
    require('crypto').timingSafeEqual(expected, incoming);

  if (!match) {
    return res.status(401).json({ error: 'Invalid webhook secret.' });
  }

  next();
}

// ---------------------------------------------------------------------------
// POST /webhooks/transaction
// ---------------------------------------------------------------------------

/**
 * Receives a bank debit or platform payout event and runs it through the
 * savings engine.
 *
 * Expected JSON body:
 * {
 *   "userId":         "uuid-v4-string",
 *   "type":           "debit" | "payout",
 *   "amount":         1320.50,
 *   "source":         "HDFC Bank" | "Swiggy" | …,
 *   "timestamp":      "2026-09-03T12:00:00.000Z",
 *   "transactionId":  "optional-external-id",   // generated if absent
 *   "rawPayload":     { …full upstream event… }  // optional, stored for audit
 * }
 *
 * Responses:
 *   200 – Event processed successfully (or already processed — idempotent).
 *   400 – Payload validation failed.
 *   401 – Missing or invalid webhook secret.
 *   500 – Internal processing error (transaction marked "failed" for replay).
 */
router.post(
  '/transaction',
  requireWebhookSecret,
  async (req, res) => {
    try {
      const result = await handleTransactionWebhook(req.body);
      return res.status(result.statusCode).json(result.body);
    } catch (err) {
      console.error('[webhookRoutes] /transaction error:', err);
      return res.status(500).json({ error: 'Internal processing error.' });
    }
  }
);

// ---------------------------------------------------------------------------
// POST /webhooks/sweep
// ---------------------------------------------------------------------------

/**
 * Manual sweep trigger — for QA, admin tooling, and hackathon demos.
 *
 * Forces a sweep attempt for a given userId regardless of how the pending
 * total was accumulated. Useful when testing the full UPI-payout flow without
 * waiting for organic round-up accumulation.
 *
 * Expected JSON body:
 * {
 *   "userId": "uuid-v4-string"
 * }
 *
 * Responses:
 *   200 – Sweep attempted; body contains { swept, sweptAmount, newBalance, reason }.
 *   400 – userId missing.
 *   401 – Missing or invalid webhook secret.
 *   404 – No SavingsStash found for this user.
 *   500 – Unexpected server error.
 */
router.post(
  '/sweep',
  requireWebhookSecret,
  async (req, res) => {
    const { userId } = req.body || {};

    if (!userId) {
      return res.status(400).json({ error: 'userId is required.' });
    }

    try {
      const stash = await SavingsStash.findOne({ userId });
      if (!stash) {
        return res.status(404).json({
          error: `No SavingsStash found for userId=${userId}. The user must be registered first.`,
        });
      }

      const pending = stash.pendingContributions;
      const thresholdMet = meetsMinimumThreshold(pending, stash.minimumThreshold);
      const { approvedAmount, wasCapped } = enforceMandateCap(pending, stash.mandateCap);
      const sweepAuthorised = thresholdMet && !wasCapped;

      if (!sweepAuthorised) {
        const reason = !thresholdMet
          ? `Pending total ₹${pending} has not reached the ₹${stash.minimumThreshold} minimum threshold.`
          : `Pending total ₹${pending} exceeds the mandate cap of ₹${stash.mandateCap}.`;

        return res.status(200).json({
          swept:        false,
          sweptAmount:  0,
          newBalance:   stash.currentBalance,
          pendingAfter: pending,
          reason,
          wasCapped,
        });
      }

      // Execute the sweep: move approvedAmount from pending to confirmed balance.
      const newBalance = Math.round((stash.currentBalance + approvedAmount) * 100) / 100;

      await SavingsStash.findOneAndUpdate(
        { userId },
        {
          $set: {
            pendingContributions: 0,
            currentBalance:       newBalance,
            lastSweepDate:        new Date(),
          },
          $push: {
            sweepHistory: {
              amount:                  approvedAmount,
              date:                    new Date(),
              type:                    'combined',
              triggeringTransactionId: null, // manual trigger — no single transaction
            },
          },
        },
        { new: true }
      );

      return res.status(200).json({
        swept:        true,
        sweptAmount:  approvedAmount,
        newBalance,
        pendingAfter: 0,
        reason:       'Manual sweep authorised via admin endpoint.',
        wasCapped,
      });

    } catch (err) {
      console.error('[webhookRoutes] /sweep error:', err);
      return res.status(500).json({ error: 'Sweep failed due to an internal error.' });
    }
  }
);

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

module.exports = router;
