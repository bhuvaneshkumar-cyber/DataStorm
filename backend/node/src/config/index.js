'use strict';
/**
 * config/index.js – environment loader and constants.
 * Every value has a sane local-dev default so `node src/server.js` runs
 * without requiring a populated .env (matches .env.example).
 */

require('dotenv').config();

module.exports = {
  port: Number(process.env.PORT) || 3001,
  nodeEnv: process.env.NODE_ENV || 'development',
  mongoUri: process.env.MONGO_URI || 'mongodb://localhost:27017/gigsave',

  // Read live rather than snapshotted at import: this is the only value that can
  // legitimately change while the process runs (secret rotation), and freezing it
  // means whichever module loads first decides the secret for everyone else.
  get webhookSecret() {
    return process.env.WEBHOOK_SECRET || '';
  },

  // Mirrors the SavingsEngine defaults in savings.py / savingsEngine.js.
  savings: {
    threshold: Number(process.env.SAVINGS_THRESHOLD) || 100,
    mandateLimit: Number(process.env.SAVINGS_MANDATE_LIMIT) || 1000,
    roundUpMultiple: Number(process.env.SAVINGS_ROUND_UP_MULTIPLE) || 50,
    surplusPercentage: Number(process.env.SAVINGS_SURPLUS_PERCENTAGE) || 0.1,
    rollingWindow: Number(process.env.SAVINGS_ROLLING_WINDOW) || 30,
  },
};
