'use strict';
/**
 * webhookRoutes.js – Express router for bank/platform webhook endpoints.
 *
 *   POST /webhooks/transaction  – bank debit / platform payout events
 *   POST /webhooks/sweep        – trigger a manual sweep check (admin/test)
 *
 * Both routes require a valid X-Webhook-Signature header (see webhookListener).
 */

const express = require('express');

const {
  verifySignatureMiddleware,
  handleTransactionWebhook,
  handleSweepWebhook,
} = require('../listeners/webhookListener');

const router = express.Router();

router.post('/transaction', verifySignatureMiddleware, handleTransactionWebhook);
router.post('/sweep', verifySignatureMiddleware, handleSweepWebhook);

module.exports = router;
