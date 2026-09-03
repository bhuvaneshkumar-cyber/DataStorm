'use strict';
/**
 * utils/index.js – shared helpers: webhook HMAC verification and INR rounding.
 */

const crypto = require('crypto');

/**
 * Verifies an inbound webhook's HMAC-SHA256 signature against the raw request
 * body, using a timing-safe comparison so response latency can't leak
 * information about how many signature bytes matched.
 *
 * @param {Buffer} rawBody   Exact bytes received on the wire (not the parsed JSON).
 * @param {string} signature Hex-encoded HMAC-SHA256 from the X-Webhook-Signature header.
 * @param {string} secret    Shared webhook secret (WEBHOOK_SECRET).
 * @returns {boolean}
 */
function verifyWebhookSignature(rawBody, signature, secret) {
  if (!signature || !secret || !rawBody || !rawBody.length) return false;

  const expected = crypto.createHmac('sha256', secret).update(rawBody).digest('hex');
  const expectedBuf = Buffer.from(expected, 'utf8');
  const givenBuf = Buffer.from(String(signature), 'utf8');

  // Lengths must match before timingSafeEqual (it throws on mismatched lengths).
  if (expectedBuf.length !== givenBuf.length) return false;
  return crypto.timingSafeEqual(expectedBuf, givenBuf);
}

/** Rounds to 2 decimal places (paise), matching savings.py's round(x, 2). */
function roundInr(amount) {
  return Math.round(amount * 100) / 100;
}

module.exports = { verifyWebhookSignature, roundInr };
