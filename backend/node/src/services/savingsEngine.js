'use strict';
/**
 * savingsEngine.js
 * ─────────────────
 * Core savings calculation service for GigSave.
 *
 * Ports the EXACT business logic from backend/savings.py:
 *   round_up()        → calculateRoundUp()
 *   moving_average()  → (internal helper) computeMovingAverage()
 *   income_surplus()  → calculateIncomeSmoothing()
 *   sweep_decision()  → (used inside processContribution)
 *
 * Architecture rule enforced here
 * ────────────────────────────────
 * Every exported function except processContribution() is a PURE FUNCTION:
 *   - No imports from Mongoose or any DB driver.
 *   - No side effects (no writes, no reads, no global mutation).
 *   - Deterministic: same inputs → same outputs, always.
 *
 * This means the pure functions can be unit-tested in isolation (no DB mock needed)
 * and reviewed by judges/teammates without understanding the persistence layer.
 *
 * Only processContribution() coordinates DB writes, and it does so by calling
 * the pure functions first and persisting only their results.
 *
 * ── Rounding note ──────────────────────────────────────────────────────────
 * Python's round() uses "round half to even" (banker's rounding).
 * JavaScript's Math.round() uses "round half up".
 * The difference only appears when the third decimal digit is exactly 5
 * (e.g. 0.005). Gig payout amounts and round-up arithmetic never produce
 * sub-paise fractions in practice, so Math.round(x * 100) / 100 is a
 * faithful port for this domain.
 */

const SavingsStash   = require('../models/SavingsStash');
const IncomeProfile  = require('../models/IncomeProfile');
const Transaction    = require('../models/Transaction');

// ============================================================================
// Constants — mirrors defaults in savings.py
// ============================================================================

/** Default round-up multiple in INR. ₹132 debit → nearest ₹50 → ₹18 saved. */
const DEFAULT_ROUND_UP_INCREMENT = 50;

/** Portion of above-average payout to sweep into savings. */
const DEFAULT_SURPLUS_PERCENTAGE = 0.10;

/** Minimum pending total (INR) before a UPI sweep is authorised. */
const DEFAULT_MINIMUM_THRESHOLD = 100;

/** Maximum single-sweep amount (INR) allowed under a UPI AutoPay mandate. */
const DEFAULT_MANDATE_CAP = 1000;

/** Number of past payouts kept in the rolling income window. */
const DEFAULT_WINDOW_DAYS = 30;

// ============================================================================
// § 1  calculateRoundUp
// ============================================================================

/**
 * Calculates the round-up savings contribution for a single debit transaction.
 *
 * Ports `round_up(amount, multiple=50)` from savings.py exactly:
 *   contribution = (multiple - amount % multiple) % multiple
 *
 * The outer modulo is critical: it makes exact multiples (e.g. ₹150, ₹200)
 * return 0 instead of the full increment — ₹150 is already a round number,
 * nothing to top up.
 *
 * @param {number} transactionAmount   Gross debit amount in INR. Must be ≥ 0.
 * @param {number} [roundUpIncrement=50]  Nearest multiple to round up to.
 *                                        Must be a positive integer.
 *
 * @returns {number} Contribution amount in INR (always ≥ 0, < roundUpIncrement).
 *
 * @throws {RangeError} If transactionAmount < 0 or roundUpIncrement ≤ 0.
 *
 * @example
 *   calculateRoundUp(132)   // → 18   (132 + 18 = 150, next ₹50 boundary)
 *   calculateRoundUp(150)   // → 0    (already on a ₹50 boundary)
 *   calculateRoundUp(0)     // → 0    (₹0 transaction, nothing to round up)
 *   calculateRoundUp(1)     // → 49
 *   calculateRoundUp(132, 10) // → 8  (next ₹10 boundary above 132 is 140)
 */
function calculateRoundUp(transactionAmount, roundUpIncrement = DEFAULT_ROUND_UP_INCREMENT) {
  if (transactionAmount < 0) {
    throw new RangeError(
      `calculateRoundUp: transactionAmount must be non-negative, got ${transactionAmount}`
    );
  }
  if (roundUpIncrement <= 0 || !Number.isFinite(roundUpIncrement)) {
    throw new RangeError(
      `calculateRoundUp: roundUpIncrement must be a positive finite number, got ${roundUpIncrement}`
    );
  }

  return (roundUpIncrement - (transactionAmount % roundUpIncrement)) % roundUpIncrement;
}

// ============================================================================
// § 2a  computeMovingAverage  (internal helper, not exported)
// ============================================================================

/**
 * Computes the arithmetic mean of the last `windowSize` values in `amounts`.
 *
 * Ports `moving_average(values, window=30)` from savings.py:
 *   mean(values[-window:]) if values else 0.0
 *
 * Uses .slice(-windowSize) which, when the array has fewer than windowSize
 * elements, returns the whole array — same behaviour as Python's [-30:].
 *
 * @param {number[]} amounts     Array of payout amounts (oldest first).
 * @param {number}   windowSize  How many of the most recent values to average.
 *
 * @returns {number} Arithmetic mean, or 0 if the array is empty.
 */
function computeMovingAverage(amounts, windowSize = DEFAULT_WINDOW_DAYS) {
  if (!Array.isArray(amounts) || amounts.length === 0) return 0;
  const window = amounts.slice(-windowSize);
  const sum = window.reduce((acc, v) => acc + v, 0);
  return sum / window.length;
}

// ============================================================================
// § 2b  calculateIncomeSmoothing
// ============================================================================

/**
 * Calculates the income-smoothing savings contribution for a single platform payout.
 *
 * Ports `income_surplus(current, history, percentage=0.10)` from savings.py:
 *   surplus = max(0.0, current - moving_average(history, 30))
 *   return round(surplus * percentage, 2)
 *
 * Logic: only the portion of this payout that EXCEEDS the worker's rolling
 * average gets swept — the idea is "you won't miss what you're not used to having".
 * If the payout is at or below average, contribution is ₹0 (not an error).
 *
 * @param {number} payoutAmount          Gross payout received from the platform, in INR.
 *                                       Must be ≥ 0.
 * @param {number} rolling30DayAverage   Pre-computed rolling average from IncomeProfile.
 *                                       Pass 0 (or null/undefined) for a first-ever payout
 *                                       with no history — the entire payout counts as
 *                                       "above average" and surplusPercentage of it is swept.
 * @param {number} [surplusPercentage=0.10]  Fraction of the above-average portion to save.
 *                                            Must be in [0, 1].
 *
 * @returns {number} Contribution amount in INR, rounded to 2 decimal places. Always ≥ 0.
 *
 * @throws {RangeError} If payoutAmount < 0 or surplusPercentage is outside [0, 1].
 *
 * @example
 *   // 30-payout history of ₹1000 each → average = ₹1000
 *   calculateIncomeSmoothing(2000, 1000, 0.1)  // → 100.0  (1000 excess × 10%)
 *   calculateIncomeSmoothing(900,  1000, 0.1)  // →   0.0  (below average, no contribution)
 *   calculateIncomeSmoothing(1000, 1000, 0.1)  // →   0.0  (exactly at average)
 *
 *   // First-ever payout — no history yet, caller passes average = 0
 *   calculateIncomeSmoothing(1500, 0, 0.1)     // → 150.0  (₹1500 excess × 10%)
 */
function calculateIncomeSmoothing(
  payoutAmount,
  rolling30DayAverage,
  surplusPercentage = DEFAULT_SURPLUS_PERCENTAGE
) {
  if (payoutAmount < 0) {
    throw new RangeError(
      `calculateIncomeSmoothing: payoutAmount must be non-negative, got ${payoutAmount}`
    );
  }
  if (surplusPercentage < 0 || surplusPercentage > 1 || !Number.isFinite(surplusPercentage)) {
    throw new RangeError(
      `calculateIncomeSmoothing: surplusPercentage must be in [0, 1], got ${surplusPercentage}`
    );
  }

  // Treat null/undefined average (no history yet) as 0 — same as Python's
  // `mean([]) = 0.0` branch in moving_average().
  const average = rolling30DayAverage != null ? rolling30DayAverage : 0;

  const surplus = Math.max(0, payoutAmount - average);
  // Round to 2 decimal places — matches savings.py's round(..., 2).
  return Math.round(surplus * surplusPercentage * 100) / 100;
}

// ============================================================================
// § 3  updateRollingAverage
// ============================================================================

/**
 * Appends a new payout to the rolling window, prunes entries beyond windowDays,
 * recomputes the average, and returns both — without persisting anything.
 *
 * The caller (processContribution) decides what to write to IncomeProfile.
 * Keeping this pure means the rolling-window logic is independently testable.
 *
 * Mirrors the two-line pattern in savings.py's SavingsEngine.process():
 *   self.pending_surplus += income_surplus(transaction.amount, self.income_history, ...)
 *   self.income_history.append(transaction.amount)
 * Except here we append FIRST so the window always contains the new payout —
 * which is consistent with "update history, then compute next time's average".
 *
 * @param {{ amount: number, date: Date }[]} existingPayouts
 *   Current rolling30DayPayouts from IncomeProfile (oldest first).
 *   Each entry must have at least { amount: number }.
 *
 * @param {{ amount: number, date?: Date }} newPayout
 *   The payout to add. `date` defaults to now if omitted.
 *
 * @param {number} [windowDays=30]  Maximum number of payouts to retain.
 *
 * @returns {{ prunedPayouts: { amount: number, date: Date }[], newAverage: number }}
 *   prunedPayouts — the updated array, trimmed to windowDays entries (oldest first).
 *   newAverage    — arithmetic mean of prunedPayouts[*].amount.
 *
 * @example
 *   const result = updateRollingAverage([], { amount: 1000 });
 *   // result.prunedPayouts → [{ amount: 1000, date: <now> }]
 *   // result.newAverage    → 1000
 *
 *   // With 30 existing entries of ₹1000, adding ₹2000:
 *   // → prunes oldest entry, window stays at 30, average shifts slightly toward 1033.33
 */
function updateRollingAverage(existingPayouts, newPayout, windowDays = DEFAULT_WINDOW_DAYS) {
  const appended = [
    ...existingPayouts,
    { amount: newPayout.amount, date: newPayout.date || new Date() },
  ];

  // Keep only the most recent windowDays entries — mirrors Python's [-30:] slice.
  const prunedPayouts = appended.slice(-windowDays);

  const amounts = prunedPayouts.map((p) => p.amount);
  const newAverage = computeMovingAverage(amounts, windowDays);

  return { prunedPayouts, newAverage };
}

// ============================================================================
// § 4  enforceMandateCap
// ============================================================================

/**
 * Applies the UPI AutoPay mandate ceiling to a pending contribution total.
 *
 * Ports the mandate_limit check in sweep_decision() from savings.py:
 *   if amount > mandate_limit: return SweepDecision(amount, False, "mandate limit exceeded")
 *
 * Note: savings.py returns the UNCAPPED amount with eligible=False when exceeded.
 * This function instead returns the mandateCap as approvedAmount so the caller
 * can still display a meaningful "here's what we COULD have swept if your mandate
 * were higher" figure — the `wasCapped` flag makes the distinction clear.
 *
 * @param {number} pendingContributionTotal  Accumulated pending total in INR.
 * @param {number} [mandateCap=1000]         Maximum allowed single-sweep amount.
 *
 * @returns {{ approvedAmount: number, wasCapped: boolean }}
 *   approvedAmount — the amount that may proceed (≤ mandateCap).
 *   wasCapped      — true if the total was trimmed to the cap.
 *
 * @example
 *   enforceMandateCap(800, 1000)   // → { approvedAmount: 800,  wasCapped: false }
 *   enforceMandateCap(1200, 1000)  // → { approvedAmount: 1000, wasCapped: true  }
 *   enforceMandateCap(1000, 1000)  // → { approvedAmount: 1000, wasCapped: false } — exactly at cap is OK
 */
function enforceMandateCap(pendingContributionTotal, mandateCap = DEFAULT_MANDATE_CAP) {
  // savings.py: amount > mandate_limit is ineligible (strict greater-than).
  // ₹1000 exactly is WITHIN the mandate — matches Python's condition.
  if (pendingContributionTotal > mandateCap) {
    return { approvedAmount: mandateCap, wasCapped: true };
  }
  return { approvedAmount: pendingContributionTotal, wasCapped: false };
}

// ============================================================================
// § 5  meetsMinimumThreshold
// ============================================================================

/**
 * Returns true if the pending contribution total has reached the minimum
 * sweep threshold.
 *
 * Ports the threshold check in sweep_decision() from savings.py:
 *   if amount < threshold: return SweepDecision(amount, False, "minimum threshold not reached")
 *
 * Condition is strict less-than, so ₹100.00 EXACTLY is eligible.
 *
 * @param {number} pendingContributionTotal  Accumulated pending total in INR.
 * @param {number} [minimumThreshold=100]    Minimum required for a sweep (default ₹100).
 *
 * @returns {boolean} True if a sweep may proceed.
 *
 * @example
 *   meetsMinimumThreshold(100)  // → true  (exactly at threshold — eligible)
 *   meetsMinimumThreshold(99.99) // → false
 *   meetsMinimumThreshold(500)  // → true
 */
function meetsMinimumThreshold(pendingContributionTotal, minimumThreshold = DEFAULT_MINIMUM_THRESHOLD) {
  return pendingContributionTotal >= minimumThreshold;
}

// ============================================================================
// § 6  processContribution  — THE ONLY FUNCTION THAT TOUCHES THE DATABASE
// ============================================================================

/**
 * Orchestrates a single savings contribution event end-to-end.
 *
 * This is the integration point between pure math and persistence.
 * Call flow:
 *   1. Validate input.
 *   2. Guard against double-processing (Transaction.isProcessed check).
 *   3. Branch on transaction.type:
 *        "debit"   → calculateRoundUp()        → add to pendingContributions
 *        "payout"  → calculateIncomeSmoothing() → add to pendingContributions
 *                  → updateRollingAverage()     → persist new window + average
 *   4. Round total to 2 d.p. (mirrors savings.py's sweep_decision rounding).
 *   5. meetsMinimumThreshold() + enforceMandateCap() → decide whether to sweep.
 *   6. If sweep authorised:
 *        - Add sweptAmount to SavingsStash.currentBalance.
 *        - Reset SavingsStash.pendingContributions to 0.
 *        - Append to SavingsStash.sweepHistory.
 *        - Update SavingsStash.lastSweepDate.
 *   7. Mark Transaction.isProcessed = true, Transaction.status = "processed".
 *   8. Return a structured result object for webhookListener.js to respond with.
 *
 * @param {object} params
 * @param {string} params.userId
 *   The user's application-level UUID. Used to look up Stash + IncomeProfile.
 *
 * @param {object} params.transaction
 *   A plain object (or Mongoose Transaction document) with at minimum:
 *     { transactionId: string, type: "debit"|"payout", amount: number }
 *   Must NOT already have isProcessed=true.
 *
 * @param {object}  [params.surplusPercentage=0.10]  Override income smoothing %.
 * @param {number}  [params.roundUpIncrement=50]     Override round-up multiple.
 *
 * @returns {Promise<{
 *   success:      boolean,
 *   swept:        boolean,
 *   sweptAmount:  number,
 *   newBalance:   number,
 *   pendingAfter: number,
 *   reason:       string,
 *   wasCapped:    boolean
 * }>}
 *
 * Result fields:
 *   success      — false only if an unexpected error occurred (DB failure etc).
 *   swept        — true if a UPI sweep was triggered this call.
 *   sweptAmount  — INR amount swept (0 if no sweep).
 *   newBalance   — SavingsStash.currentBalance after this call.
 *   pendingAfter — SavingsStash.pendingContributions after this call.
 *   reason       — Human-readable explanation (surfaced to webhookListener for logging).
 *   wasCapped    — true if sweep was capped at mandateCap (informational).
 *
 * @throws Never throws — all errors are caught internally and surfaced via success=false.
 */
async function processContribution({
  userId,
  transaction,
  surplusPercentage = DEFAULT_SURPLUS_PERCENTAGE,
  roundUpIncrement  = DEFAULT_ROUND_UP_INCREMENT,
}) {
  try {
    // ── 1. Load required documents ─────────────────────────────────────────
    const [stash, incomeProfile, txDoc] = await Promise.all([
      SavingsStash.findOne({ userId }),
      IncomeProfile.findOne({ userId }),
      Transaction.findOne({ transactionId: transaction.transactionId }),
    ]);

    if (!stash) {
      return _fail(`No SavingsStash found for userId=${userId}. Create one on user registration.`);
    }
    if (!txDoc) {
      return _fail(`Transaction ${transaction.transactionId} not found in DB.`);
    }

    // ── 2. Idempotency guard ───────────────────────────────────────────────
    if (txDoc.isProcessed) {
      return {
        success:      true,
        swept:        false,
        sweptAmount:  0,
        newBalance:   stash.currentBalance,
        pendingAfter: stash.pendingContributions,
        reason:       'Transaction already processed — skipped (idempotent).',
        wasCapped:    false,
      };
    }

    // ── 3. Calculate contribution amount (pure, no DB) ────────────────────
    let contribution = 0;
    let sweepType    = null; // 'roundup' | 'smoothing' | 'combined'

    if (txDoc.type === 'debit') {
      // ── 3a. Round-up branch ────────────────────────────────────────────
      contribution = calculateRoundUp(txDoc.amount, roundUpIncrement);
      sweepType    = 'roundup';

    } else if (txDoc.type === 'payout') {
      // ── 3b. Income-smoothing branch ────────────────────────────────────
      // Determine the rolling average. If no IncomeProfile exists yet, treat
      // average as 0 (first-ever payout — mirrors savings.py's empty-history=0 branch).
      const currentAverage = incomeProfile?.currentRollingAverage ?? 0;

      contribution = calculateIncomeSmoothing(txDoc.amount, currentAverage, surplusPercentage);
      sweepType    = 'smoothing';

      // ── 3c. Update rolling window (pure) then persist ──────────────────
      const existingPayouts = incomeProfile?.rolling30DayPayouts ?? [];
      const { prunedPayouts, newAverage } = updateRollingAverage(
        existingPayouts,
        { amount: txDoc.amount, date: txDoc.timestamp || new Date() }
      );

      // Persist income profile — upsert so first-ever payout creates the document.
      await IncomeProfile.findOneAndUpdate(
        { userId },
        {
          $set: {
            rolling30DayPayouts: prunedPayouts,
            currentRollingAverage: newAverage,
          },
        },
        { upsert: true, new: true }
      );

    } else {
      // savings.py raises ValueError for unknown kind — we surface it cleanly.
      return _fail(`Unknown transaction type "${txDoc.type}". Must be "debit" or "payout".`);
    }

    // ── 4. Round total to 2 d.p. — mirrors sweep_decision() in savings.py ─
    const newPending = Math.round((stash.pendingContributions + contribution) * 100) / 100;

    // ── 5. Decide whether to sweep ─────────────────────────────────────────
    const thresholdMet              = meetsMinimumThreshold(newPending, stash.minimumThreshold);
    const { approvedAmount, wasCapped } = enforceMandateCap(newPending, stash.mandateCap);

    // A sweep is eligible iff threshold is met AND total ≤ mandateCap.
    // savings.py: amount < threshold → ineligible; amount > mandate_limit → ineligible.
    const sweepAuthorised = thresholdMet && !wasCapped;

    // ── 6. Persist stash changes ───────────────────────────────────────────
    let sweptAmount = 0;
    let newBalance  = stash.currentBalance;

    if (sweepAuthorised) {
      sweptAmount = approvedAmount;
      newBalance  = Math.round((stash.currentBalance + sweptAmount) * 100) / 100;

      // Determine sweep record type for the history log.
      // If BOTH roundups and smoothing contributed to this sweep, mark 'combined'.
      // For this transaction the type reflects this single event's contribution;
      // the broader combined case will be handled in a future multi-event sweep.
      const historyType = sweepType;

      await SavingsStash.findOneAndUpdate(
        { userId },
        {
          $set: {
            pendingContributions: 0,
            currentBalance:       newBalance,
            lastSweepDate:        new Date(),
          },
          $push: {
            sweepHistory: {
              amount:                  sweptAmount,
              date:                    new Date(),
              type:                    historyType,
              triggeringTransactionId: txDoc.transactionId,
            },
          },
        },
        { new: true }
      );
    } else {
      // No sweep — just accumulate the new pending total.
      await SavingsStash.findOneAndUpdate(
        { userId },
        { $set: { pendingContributions: newPending } },
        { new: true }
      );
    }

    // ── 7. Mark transaction as processed ──────────────────────────────────
    await Transaction.findOneAndUpdate(
      { transactionId: txDoc.transactionId },
      { $set: { isProcessed: true, status: 'processed' } }
    );

    // ── 8. Build and return result ─────────────────────────────────────────
    const reason = sweepAuthorised
      ? 'UPI AutoPay sweep authorized'
      : thresholdMet && wasCapped
        ? 'mandate limit exceeded'
        : 'minimum threshold not reached';

    return {
      success:      true,
      swept:        sweepAuthorised,
      sweptAmount,
      newBalance,
      pendingAfter: sweepAuthorised ? 0 : newPending,
      reason,
      wasCapped,
    };

  } catch (err) {
    // Catch-all: DB connection errors, validation failures, unexpected exceptions.
    // We log and return a structured failure so webhookListener can reply with 500
    // and the raw webhook payload can be replayed later.
    console.error('[savingsEngine] processContribution error:', err);
    return _fail(`Unexpected error: ${err.message}`);
  }
}

// ── Private helper ────────────────────────────────────────────────────────────

/**
 * Builds a standardised failure result object.
 * @param {string} reason
 * @returns {{ success: false, swept: false, sweptAmount: 0, newBalance: 0, pendingAfter: 0, reason: string, wasCapped: false }}
 */
function _fail(reason) {
  return {
    success:      false,
    swept:        false,
    sweptAmount:  0,
    newBalance:   0,
    pendingAfter: 0,
    reason,
    wasCapped:    false,
  };
}

// ============================================================================
// Exports
// ============================================================================

module.exports = {
  calculateRoundUp,
  calculateIncomeSmoothing,
  updateRollingAverage,
  enforceMandateCap,
  meetsMinimumThreshold,
  processContribution,

  // Export internal helper so it can be unit-tested directly.
  _computeMovingAverage: computeMovingAverage,

  // Export constants so tests and other modules can reference the same defaults.
  DEFAULTS: {
    ROUND_UP_INCREMENT:  DEFAULT_ROUND_UP_INCREMENT,
    SURPLUS_PERCENTAGE:  DEFAULT_SURPLUS_PERCENTAGE,
    MINIMUM_THRESHOLD:   DEFAULT_MINIMUM_THRESHOLD,
    MANDATE_CAP:         DEFAULT_MANDATE_CAP,
    WINDOW_DAYS:         DEFAULT_WINDOW_DAYS,
  },
};
