'use strict';
/**
 * app.js – Express application factory (stub)
 *
 * TODO (Phase 3):
 *   - Load config (dotenv).
 *   - Connect to MongoDB via config/db.js.
 *   - Mount body-parser / express.json middleware.
 *   - Mount webhookRoutes at /webhooks.
 *   - Add global error handler middleware.
 */

const express = require('express');

const app = express();

// Stub health-check so the server is startable now.
app.get('/health', (_req, res) => res.json({ status: 'ok', service: 'gigsave-backend-node' }));

module.exports = app;
