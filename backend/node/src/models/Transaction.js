'use strict';
/**
 * Transaction.js – Mongoose schema for every bank debit or platform payout
 * event received via webhook.
 *
 * Each document represents one raw event from the bank adapter or gig platform.
 * The savingsEngine reads these to compute round-ups and income-smoothing surplus.
 *
 * Index strategy
 * ──────────────
 * webhookListener.js will frequently run this query:
 *   "fetch the last 30 platform_payout transactions for userId, ordered by timestamp DESC"
 * → Compound index on { userId, type, timestamp } covers this perfectly (prefix on userId
 *   also covers simple "all transactions for user" lookups).
 *
 * A secondary index on { transactionId } enforces idempotency for duplicate webhooks.
 */

const mongoose = require('mongoose');

const { Schema, model } = mongoose;

const TransactionSchema = new Schema(
  {
    /**
     * Stable, externally-issued transaction reference (from bank / platform).
     * Used as idempotency key – if the same webhook fires twice, the second
     * insert will fail on the unique constraint and can be safely ignored.
     */
    transactionId: {
      type: String,
      required: [true, 'transactionId is required'],
      unique: true,
      index: true,
    },

    /**
     * Reference to the User who owns this transaction.
     * Matches User.userId (String UUID), NOT the Mongo _id, so that queries
     * across services stay decoupled from ObjectId internals.
     */
    userId: {
      type: String,
      ref: 'User',
      required: [true, 'userId is required'],
      index: true,
    },

    /**
     * Transaction type – maps directly to Transaction.kind in savings.py.
     *   "debit"   → a spend on the worker's linked account; triggers round-up.
     *   "payout"  → a platform payout (Uber, Swiggy, etc.); triggers income smoothing.
     */
    type: {
      type: String,
      enum: {
        values: ['debit', 'payout'],
        message: 'type must be "debit" or "payout"',
      },
      required: [true, 'type is required'],
    },

    /** Transaction amount in INR (always positive). */
    amount: {
      type: Number,
      required: [true, 'amount is required'],
      min: [0, 'amount must be non-negative'],
    },

    /**
     * Human-readable origin of the event, e.g. "HDFC Bank", "Swiggy",
     * "Uber Eats". Useful for display in the frontend dashboard.
     */
    source: {
      type: String,
      default: 'unknown',
      trim: true,
    },

    /**
     * When the transaction occurred on the bank / platform side.
     * Stored separately from Mongoose's auto-createdAt so we can query
     * "payouts in the last 30 days" by the actual event time, not ingestion time.
     */
    timestamp: {
      type: Date,
      required: [true, 'timestamp is required'],
      index: true,
    },

    /**
     * Processing state of this transaction within GigSave:
     *   "pending"   → received, not yet processed by savingsEngine.
     *   "processed" → savingsEngine ran successfully; contribution recorded.
     *   "failed"    → savingsEngine or downstream step threw an error.
     */
    status: {
      type: String,
      enum: ['pending', 'processed', 'failed'],
      default: 'pending',
    },

    /**
     * Complete raw payload from the inbound webhook, stored as a schemaless
     * Mixed field for audit and debug purposes.
     * Allows replaying events if savingsEngine logic is updated.
     */
    rawPayload: {
      type: Schema.Types.Mixed,
      default: null,
    },

    /**
     * Guard flag: true once this transaction has been consumed by savingsEngine
     * (either for round-up or income-smoothing calculation).
     * webhookListener checks this before processing to prevent double-counting
     * if a webhook is retried or replayed.
     */
    isProcessed: {
      type: Boolean,
      default: false,
      index: true,
    },
  },
  {
    timestamps: true, // createdAt = ingestion time; timestamp = event time
    collection: 'transactions',
  }
);

// ---------------------------------------------------------------------------
// Compound indexes
// ---------------------------------------------------------------------------

/**
 * Primary query pattern for income smoothing:
 *   db.transactions.find({ userId, type: 'payout' }).sort({ timestamp: -1 }).limit(30)
 * This compound index is a covering index for that query.
 */
TransactionSchema.index({ userId: 1, type: 1, timestamp: -1 });

/**
 * Pattern for fetching all pending transactions for a user (processing queue):
 *   db.transactions.find({ userId, isProcessed: false })
 */
TransactionSchema.index({ userId: 1, isProcessed: 1 });

module.exports = model('Transaction', TransactionSchema);
