'use strict';
/**
 * IncomeProfile.js – Mongoose schema for a user's income history and rolling average.
 *
 * Used exclusively by the income-smoothing branch of savingsEngine.js.
 * Answers the core question from savings.py:
 *   "Is this payout above the worker's recent average? If so, save a % of the excess."
 *
 * ── Design choice: store the raw payout window, not just the running average ──
 *
 * Option A  Store only { currentRollingAverage: Number } and update it incrementally.
 *   Pro:  O(1) storage, O(1) update.
 *   Con:  Incremental averages are sensitive to payout frequency and gaps; they
 *         don't faithfully implement savings.py's `mean(history[-30:])` semantics.
 *         Replaying or auditing becomes impossible.
 *
 * Option B  Store the last 30 raw payout records (this file).
 *   Pro:  Exactly mirrors moving_average() in savings.py.
 *         webhookListener can re-derive the average at any time for audit/replay.
 *         The window is naturally bounded to 30 entries – storage is O(1) in practice.
 *   Con:  Slightly more bytes per document; array ops instead of a scalar update.
 *
 * Choice: Option B.
 * Rationale: correctness and auditability outweigh the marginal storage cost.
 * Each payout record is ~32 bytes (Number + Date); 30 records ≈ 1 KB per user.
 * The currentRollingAverage field is kept as a cached scalar so the UI and
 * savingsEngine can read it without recomputing the average on every request.
 * It must be recomputed and persisted each time a new payout is appended.
 */

const mongoose = require('mongoose');

const { Schema, model } = mongoose;

// ---------------------------------------------------------------------------
// Sub-schema: one entry in the rolling payout window
// ---------------------------------------------------------------------------
const PayoutRecordSchema = new Schema(
  {
    /** Gross payout amount received from the gig platform, in INR. */
    amount: {
      type: Number,
      required: true,
      min: [0, 'Payout amount must be non-negative'],
    },

    /**
     * Date/time the payout was received.
     * Used to display "income over time" charts and for TTL / pruning if needed.
     */
    date: {
      type: Date,
      required: true,
      default: Date.now,
    },
  },
  { _id: false } // no sub-doc _id – these are anonymous window entries
);

// ---------------------------------------------------------------------------
// Main IncomeProfile schema
// ---------------------------------------------------------------------------
const IncomeProfileSchema = new Schema(
  {
    /**
     * Reference to the owning user (mirrors User.userId string UUID).
     * One income profile per user.
     */
    userId: {
      type: String,
      ref: 'User',
      required: [true, 'userId is required'],
      unique: true,
      index: true,
    },

    /**
     * Sliding window of the last 30 platform payouts (most recent last).
     * savingsEngine appends a new entry and trims the array to 30 items
     * after every platform_payout event – exactly mirrors:
     *   self.income_history.append(transaction.amount)
     *   moving_average(self.income_history, 30)
     * from savings.py.
     *
     * Max length enforced in application code (savingsEngine), not by Mongoose,
     * because MongoDB array $push + $slice is cheaper than schema-level validation.
     */
    rolling30DayPayouts: {
      type: [PayoutRecordSchema],
      default: [],
    },

    /**
     * Pre-computed mean of rolling30DayPayouts[*].amount.
     * Cached here so webhookListener can evaluate
     *   incomeSurplus = max(0, currentPayout - currentRollingAverage) * 0.10
     * in O(1) without re-summing the array on every webhook.
     *
     * MUST be updated atomically with rolling30DayPayouts on every payout event.
     * Null when no payout history exists yet (engine treats as 0, matching
     * savings.py's `mean(values[-window:]) if values else 0.0`).
     */
    currentRollingAverage: {
      type: Number,
      default: null,
    },
  },
  {
    timestamps: true, // createdAt, updatedAt
    collection: 'income_profiles',
  }
);

module.exports = model('IncomeProfile', IncomeProfileSchema);
