'use strict';

const crypto = require('crypto');
const Transaction = require('../models/Transaction');
const SavingsStash = require('../models/SavingsStash');
const { processContribution, authorizeManualSweep } = require('../services/savingsEngine');
const { verifyWebhookSignature } = require('../utils');
const config = require('../config');

const REQUIRED_FIELDS = ['userId', 'type', 'amount', 'source', 'timestamp'];
const VALID_TYPES = ['debit', 'payout'];

function verifySignatureMiddleware(req, res, next) {
  const signature = req.get('X-Webhook-Signature');
  if (signature) {
    if (!verifyWebhookSignature(req.rawBody, signature, config.webhookSecret)) {
      return res.status(401).json({ error: 'Invalid or missing webhook signature.' });
    }
    return next();
  }

  const expectedSecret = process.env.WEBHOOK_SECRET;
  const incomingSecret = req.headers['x-webhook-secret'];
  if (!expectedSecret) {
    console.error('[webhookListener] WEBHOOK_SECRET is not set. Refusing request.');
    return res.status(401).json({ error: 'Webhook authentication is not configured.' });
  }
  if (!incomingSecret) return res.status(401).json({ error: 'Missing x-webhook-secret header.' });
  const expected = Buffer.from(expectedSecret);
  const incoming = Buffer.from(String(incomingSecret));
  const match = expected.length === incoming.length && crypto.timingSafeEqual(expected, incoming);
  if (!match) return res.status(401).json({ error: 'Invalid webhook secret.' });
  return next();
}

async function handleTransactionPayload(payload) {
  payload = payload && typeof payload === 'object' ? payload : {};
  const missing = REQUIRED_FIELDS.filter((field) => payload[field] === undefined || payload[field] === null || payload[field] === '');
  if (missing.length) return { statusCode: 400, body: { error: `Missing required fields: ${missing.join(', ')}` } };
  if (!VALID_TYPES.includes(payload.type)) return { statusCode: 400, body: { error: `Invalid type "${payload.type}". Must be one of: ${VALID_TYPES.join(', ')}` } };

  const amount = Number(payload.amount);
  if (!Number.isFinite(amount) || amount < 0) {
    return { statusCode: 400, body: { error: `Invalid amount "${payload.amount}". Must be a non-negative number.` } };
  }
  const eventTimestamp = new Date(payload.timestamp);
  if (Number.isNaN(eventTimestamp.getTime())) {
    return { statusCode: 400, body: { error: `Invalid timestamp "${payload.timestamp}". Must be a valid ISO 8601 date-time.` } };
  }

  const transactionId = payload.transactionId ? String(payload.transactionId) : crypto.createHash('sha256')
    .update(`${payload.userId}|${payload.source}|${payload.timestamp}|${amount}`).digest('hex');

  try {
    const existingTx = await Transaction.findOne({ transactionId });
    if (existingTx && (existingTx.status === 'processed' || existingTx.isProcessed)) {
      return { statusCode: 200, body: { message: 'already processed', transactionId } };
    }
  } catch (err) {
    console.error('[webhookListener] DB error during idempotency check:', err);
    return { statusCode: 500, body: { error: 'Database error during idempotency check.' } };
  }

  try {
    await Transaction.findOneAndUpdate(
      { transactionId },
      { $setOnInsert: { transactionId, userId: payload.userId, type: payload.type, amount, source: payload.source, timestamp: eventTimestamp, status: 'pending', isProcessed: false, rawPayload: payload.rawPayload ?? payload } },
      { upsert: true, new: true, setDefaultsOnInsert: true }
    );
  } catch (err) {
    console.error('[webhookListener] DB error saving pending transaction:', err);
    return { statusCode: 500, body: { error: 'Failed to save transaction record.' } };
  }

  try {
    const engineResult = await processContribution({ userId: payload.userId, transaction: { transactionId } });
    if (!engineResult.success) {
      await markFailed(transactionId, engineResult.reason);
      return { statusCode: 500, body: { error: engineResult.reason } };
    }
    return {
      statusCode: 200,
      body: { transactionId, swept: engineResult.swept, sweptAmount: engineResult.sweptAmount, newBalance: engineResult.newBalance, pendingAfter: engineResult.pendingAfter, reason: engineResult.reason, wasCapped: engineResult.wasCapped },
    };
  } catch (err) {
    console.error('[webhookListener] Unexpected error in processContribution:', err);
    await markFailed(transactionId, err.message);
    return { statusCode: 500, body: { error: 'Internal processing error. Transaction marked failed for replay.' } };
  }
}

async function markFailed(transactionId, reason) {
  try {
    await Transaction.findOneAndUpdate({ transactionId }, { $set: { status: 'failed', isProcessed: false } });
  } catch (err) {
    console.error(`[webhookListener] Could not mark transaction ${transactionId} as failed:`, err.message, '| Original failure reason:', reason);
  }
}

async function handleTransactionRequest(req, res) {
  try {
    const result = await handleTransactionPayload(req.body);
    return res.status(result.statusCode).json(result.body);
  } catch (err) {
    console.error('[webhookListener] request handler error:', err);
    return res.status(500).json({ error: 'Internal processing error.' });
  }
}

async function handleTransactionWebhook(payloadOrRequest, response) {
  if (response) return handleTransactionRequest(payloadOrRequest, response);
  return handleTransactionPayload(payloadOrRequest);
}

async function handleSweepWebhook(req, res) {
  const { userId } = req.body || {};
  if (typeof userId !== 'string' || !userId) return res.status(400).json({ error: 'userId is required.' });
  try {
    const result = await authorizeManualSweep(userId);
    return res.status(result.success ? 200 : 500).json(result);
  } catch (err) {
    console.error('[webhookListener] handleSweepWebhook error:', err);
    return res.status(500).json({ error: 'Sweep failed due to an internal error.' });
  }
}

module.exports = { verifySignatureMiddleware, handleTransactionWebhook, handleTransactionRequest, handleSweepWebhook };
