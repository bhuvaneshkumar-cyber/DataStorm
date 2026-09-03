'use strict';
/**
 * app.js – Express application factory.
 */

const express = require('express');

const webhookRoutes = require('./routes/webhookRoutes');

const app = express();

// Capture the raw body alongside the parsed JSON so webhook signature
// verification can HMAC the exact bytes the sender signed.
app.use(
  express.json({
    verify: (req, _res, buf) => {
      req.rawBody = buf;
    },
  })
);

app.get('/health', (_req, res) => res.json({ status: 'ok', service: 'gigsave-backend-node' }));

app.use('/webhooks', webhookRoutes);

// Global error handler – catches JSON parse errors and anything a route forgot to catch.
app.use((err, _req, res, _next) => {
  console.error('[app] unhandled error:', err);
  res.status(err.status || 500).json({ success: false, reason: err.message || 'Internal server error.' });
});

module.exports = app;
