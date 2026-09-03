'use strict';
/**
 * webhookListener.js – inbound bank/platform webhook handlers.
 *
 * Flow for POST /webhooks/transaction:
 *   1. verifySignatureMiddleware checks X-Webhook-Signature (HMAC-SHA256 over
 *      the raw body, keyed with WEBHOOK_SECRET) before any handler runs.
 *   2. handleTransactionWebhook validates the payload, idempotently upserts
 *      the raw event as a Transaction, then delegates the financial decision
 *      to savingsEngine.processContribution().
 *
 * POST /webhooks/sweep is an admin/test route that force-checks a user's
 * already-accumulated pending contributions via savingsEngine.authorizeManualSweep().
 */

const Transaction = require('../models/Transaction');
const { processContribution, authorizeManualSweep } = require('../services/savingsEngine');
const { verifyWebhookSignature } = require('../utils');
const config = require('../config');

const VALID_TYPES = ['debit', 'payout'];

function verifySignatureMiddleware(req, res, next) {
  const signature = req.get('X-Webhook-Signature');
  if (!verifyWebhookSignature(req.rawBody, signature, config.webhookSecret)) {
    return res.status(401).json({ success: false, reason: 'Invalid or missing webhook signature.' });
  }
  return next();
}

async function handleTransactionWebhook(req, res) {
  const { userId, transactionId, type, amount, source, timestamp } = req.body || {};

  // userId/transactionId must be plain strings, not objects — otherwise a
  // payload like {"userId": {"$ne": null}} would reach Mongoose as a query
  // operator instead of a literal value (NoSQL injection).
  if (
    typeof userId !== 'string' ||
    !userId ||
    typeof transactionId !== 'string' ||
    !transactionId ||
    !VALID_TYPES.includes(type) ||
    typeof amount !== 'number' ||
    !Number.isFinite(amount) ||
    amount < 0
  ) {
    return res.status(400).json({
      success: false,
      reason: 'userId, transactionId, type ("debit"|"payout"), and a non-negative amount are required.',
    });
  }

  try {
    // Idempotent by transactionId: a retried webhook only inserts once.
    // processContribution() below independently guards against reprocessing
    // an already-processed transaction, so a duplicate delivery is a no-op.
    await Transaction.findOneAndUpdate(
      { transactionId },
      {
        $setOnInsert: {
          transactionId,
          userId,
          type,
          amount,
          source: source || 'unknown',
          timestamp: timestamp ? new Date(timestamp) : new Date(),
          rawPayload: req.body,
        },
      },
      { upsert: true, new: true }
    );

    const result = await processContribution({ userId, transaction: { transactionId } });
    return res.status(result.success ? 200 : 500).json(result);
  } catch (err) {
    console.error('[webhookListener] handleTransactionWebhook error:', err);
    return res.status(500).json({ success: false, reason: 'Internal error processing webhook.' });
  }
}

async function handleSweepWebhook(req, res) {
  const { userId } = req.body || {};
  if (typeof userId !== 'string' || !userId) {
    return res.status(400).json({ success: false, reason: 'userId is required.' });
  }

  try {
    const result = await authorizeManualSweep(userId);
    return res.status(result.success ? 200 : 500).json(result);
  } catch (err) {
    console.error('[webhookListener] handleSweepWebhook error:', err);
    return res.status(500).json({ success: false, reason: 'Internal error authorizing sweep.' });
  }
}

module.exports = { verifySignatureMiddleware, handleTransactionWebhook, handleSweepWebhook };
