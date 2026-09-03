'use strict';

const express = require('express');
const {
  verifySignatureMiddleware,
  handleTransactionRequest,
  handleSweepWebhook,
} = require('../listeners/webhookListener');

const router = express.Router();

router.post('/transaction', verifySignatureMiddleware, handleTransactionRequest);
router.post('/sweep', verifySignatureMiddleware, handleSweepWebhook);

module.exports = router;
