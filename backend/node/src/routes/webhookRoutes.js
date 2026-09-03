'use strict';
/**
 * webhookRoutes.js – Express router for bank/platform webhook endpoints (stub)
 *
 * Planned routes:
 *   POST /webhooks/transaction  – bank debit / platform_payout events
 *   POST /webhooks/sweep        – trigger authorizeAndReset() manually (admin/test)
 *
 * TODO (Phase 3):
 *   - Mount webhookListener as middleware.
 *   - Add request validation middleware.
 *   - Wire into app.js.
 */

const express = require('express');

const router = express.Router();

// Stub – routes will be added in Phase 3.

module.exports = router;
