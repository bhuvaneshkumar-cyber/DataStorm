'use strict';
/**
 * SavingsStash.js – Mongoose schema for a user's "Resilience Stash" savings pot.
 *
 * One document per user. Tracks:
 *   - Current redeemable balance (post-sweep funds).
 *   - Pending contributions that have accumulated but not yet been swept.
 *   - Full sweep history for the frontend dashboard / audit trail.
 *   - Engine configuration (threshold, mandateCap) scoped to this user.
 *
 * "Sweep" = a UPI AutoPay debit that moves pending contributions into the stash.
 */

const mongoose = require('mongoose');

const { Schema, model } = mongoose;

// ---------------------------------------------------------------------------
// Sub-schema: individual sweep history entry
// ---------------------------------------------------------------------------
const SweepRecordSchema = new Schema(
  {
    /** Total INR amount moved in this sweep (roundups + smoothing combined). */
    amount: {
      type: Number,
      required: true,
      min: [0, 'Sweep amount must be non-negative'],
    },

    /** Wall-clock time the sweep was authorised and executed. */
    date: {
      type: Date,
      required: true,
      default: Date.now,
    },

    /**
     * Breakdown of what drove this sweep:
     *   "roundup"    → triggered purely by accumulated round-ups.
     *   "smoothing"  → triggered purely by income-smoothing surplus.
     *   "combined"   → both round-up and smoothing contributed.
     */
    type: {
      type: String,
      enum: ['roundup', 'smoothing', 'combined'],
      required: true,
    },

    /**
     * The Transaction._id (or transactionId string) of the event that pushed
     * the pending total over the ₹100 threshold and triggered this sweep.
     * Useful for tracing "which payout caused this save?".
     */
    triggeringTransactionId: {
      type: String,
      default: null,
    },
  },
  { _id: true } // keep sub-doc _id so frontend can reference individual sweep records
);

// ---------------------------------------------------------------------------
// Main SavingsStash schema
// ---------------------------------------------------------------------------
const SavingsStashSchema = new Schema(
  {
    /**
     * Reference to the owning user (mirrors User.userId string UUID).
     * One stash per user – enforced by the unique index below.
     */
    userId: {
      type: String,
      ref: 'User',
      required: [true, 'userId is required'],
      unique: true,
      index: true,
    },

    /**
     * Confirmed, redeemable balance in INR.
     * Increases after each successful sweep; decreases on withdrawal.
     * This is the number shown as "Your Resilience Stash" in the UI.
     */
    currentBalance: {
      type: Number,
      default: 0,
      min: [0, 'Balance cannot go negative'],
    },

    /**
     * Running total of contributions that have accumulated since the last sweep
     * but have NOT yet been swept (pending_roundups + pending_surplus from savings.py).
     * savingsEngine adds to this on every processed transaction.
     * Resets to 0 after a successful authorizeAndReset() call.
     */
    pendingContributions: {
      type: Number,
      default: 0,
      min: [0, 'Pending contributions cannot go negative'],
    },

    /**
     * Timestamp of the most recent successful sweep.
     * Used by the frontend to display "Last saved on …".
     * Null if no sweep has ever occurred.
     */
    lastSweepDate: {
      type: Date,
      default: null,
    },

    /**
     * Append-only log of every completed sweep.
     * Stored embedded (not as a separate collection) because:
     *   - Sweep frequency is low (maybe a few times per month per user).
     *   - The frontend almost always wants the full history alongside the balance.
     *   - Avoids an extra collection + JOIN on every dashboard load.
     * If history grows very large (edge case), we can cap with a $slice or paginate.
     */
    sweepHistory: {
      type: [SweepRecordSchema],
      default: [],
    },

    /**
     * Minimum pending total (in INR) required before a sweep is authorised.
     * Mirrors threshold in savings.py. Default ₹100.
     * Stored per-user so it can be personalised later without a code deploy.
     */
    minimumThreshold: {
      type: Number,
      default: 100,
      min: [1, 'Minimum threshold must be at least ₹1'],
    },

    /**
     * Maximum single-sweep amount allowed under the user's UPI AutoPay mandate.
     * Should be kept in sync with User.mandate.capAmount.
     * Denormalised here so savingsEngine can read it in a single query
     * without joining User – performance matters for webhook latency.
     */
    mandateCap: {
      type: Number,
      default: 1000,
      min: [1, 'Mandate cap must be at least ₹1'],
    },
  },
  {
    timestamps: true, // createdAt, updatedAt
    collection: 'savings_stashes',
  }
);

module.exports = model('SavingsStash', SavingsStashSchema);
