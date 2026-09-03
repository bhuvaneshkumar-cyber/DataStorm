'use strict';
/**
 * app.js – Express application factory
 *
 * Loads environment variables, configures middleware, mounts all routes.
 * Does NOT call app.listen() — that lives in server.js so this module
 * can be imported by tests without binding a port.
 */

require('dotenv').config();

const express        = require('express');
const bodyParser     = require('body-parser');
const webhookRoutes  = require('./routes/webhookRoutes');

const app = express();

// ---------------------------------------------------------------------------
// Global middleware
// ---------------------------------------------------------------------------

// Parse incoming JSON bodies (replaces the old body-parser .json() call).
// limit set to 1mb to accommodate rawPayload audit blobs.
app.use(express.json({ limit: '1mb' }));

// Parse URL-encoded bodies for any form-style partners that send that way.
app.use(bodyParser.urlencoded({ extended: false }));

// ---------------------------------------------------------------------------
// Routes
// ---------------------------------------------------------------------------

// Health check — unauthenticated, used by load balancers and teammates.
app.get('/health', (_req, res) =>
  res.json({ status: 'ok', service: 'gigsave-backend-node', ts: new Date().toISOString() })
);

// All webhook endpoints live under /webhooks.
// Authentication (x-webhook-secret header) is enforced inside the router.
app.use('/webhooks', webhookRoutes);

// ---------------------------------------------------------------------------
// Global error handler
// Must have exactly four arguments so Express recognises it as an error handler.
// ---------------------------------------------------------------------------
// eslint-disable-next-line no-unused-vars
app.use((err, _req, res, _next) => {
  console.error('[app] Unhandled error:', err);
  res.status(500).json({ error: 'Internal server error.' });
});

module.exports = app;
