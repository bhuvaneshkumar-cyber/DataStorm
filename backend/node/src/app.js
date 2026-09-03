'use strict';
/**
 * app.js – Express application factory.
 */

require('dotenv').config();

const express        = require('express');
const bodyParser     = require('body-parser');
const mongoose       = require('mongoose');
const webhookRoutes  = require('./routes/webhookRoutes');

const app = express();

// ---------------------------------------------------------------------------
// Global middleware
// ---------------------------------------------------------------------------

// Parse incoming JSON bodies (replaces the old body-parser .json() call).
// limit set to 1mb to accommodate rawPayload audit blobs.
app.use(express.json({
  limit: '1mb',
  verify: (req, _res, buffer) => {
    req.rawBody = buffer;
  },
}));

// Parse URL-encoded bodies for any form-style partners that send that way.
app.use(bodyParser.urlencoded({ extended: false }));

// ---------------------------------------------------------------------------
// Routes
// ---------------------------------------------------------------------------

// Health check — unauthenticated, used by load balancers and teammates.
app.get('/health', (_req, res) => {
  const health = {
    status: 'ok',
    uptime: process.uptime(),
    timestamp: new Date().toISOString(),
  };

  if (process.env.MONGODB_URI || process.env.MONGO_URI) {
    health.db = mongoose.connection.readyState === 1 ? 'connected' : 'disconnected';
  }

  return res.json(health);
});

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
  if (err instanceof SyntaxError && err.status === 400 && err.type === 'entity.parse.failed') {
    return res.status(400).json({ error: 'Malformed JSON request body.' });
  }
  res.status(500).json({ error: 'Internal server error.' });
});
app.use('/webhooks', webhookRoutes);

app.use((err, _req, res, _next) => {
  console.error('[app] Unhandled error:', err);
  if (err instanceof SyntaxError && err.status === 400 && err.type === 'entity.parse.failed') {
    return res.status(400).json({ error: 'Malformed JSON request body.' });
  }
  return res.status(500).json({ error: 'Internal server error.' });
});

module.exports = app;
