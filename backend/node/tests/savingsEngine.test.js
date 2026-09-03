'use strict';

jest.mock('../src/models/SavingsStash', () => ({
  findOne: jest.fn(),
  findOneAndUpdate: jest.fn(),
}));

jest.mock('../src/models/IncomeProfile', () => ({
  findOne: jest.fn(),
  findOneAndUpdate: jest.fn(),
}));

jest.mock('../src/models/Transaction', () => ({
  findOne: jest.fn(),
  findOneAndUpdate: jest.fn(),
}));

const SavingsStash = require('../src/models/SavingsStash');
const IncomeProfile = require('../src/models/IncomeProfile');
const Transaction = require('../src/models/Transaction');
const {
  calculateRoundUp,
  calculateIncomeSmoothing,
  updateRollingAverage,
  enforceMandateCap,
  meetsMinimumThreshold,
  processContribution,
  _computeMovingAverage,
} = require('../src/services/savingsEngine');

const userId = 'user-1';

function makeStash(overrides = {}) {
  return {
    currentBalance: 0,
    pendingContributions: 0,
    minimumThreshold: 100,
    mandateCap: 1000,
    sweepHistory: [],
    ...overrides,
  };
}

function makeTransaction(overrides = {}) {
  return {
    transactionId: 'tx-1',
    type: 'debit',
    amount: 132,
    timestamp: new Date('2026-01-01T00:00:00.000Z'),
    isProcessed: false,
    ...overrides,
  };
}

function arrangeDatabase({ stash = makeStash(), incomeProfile = null, tx = makeTransaction() } = {}) {
  SavingsStash.findOne.mockResolvedValue(stash);
  IncomeProfile.findOne.mockResolvedValue(incomeProfile);
  Transaction.findOne.mockResolvedValue(tx);
  SavingsStash.findOneAndUpdate.mockResolvedValue(stash);
  IncomeProfile.findOneAndUpdate.mockResolvedValue(incomeProfile);
  Transaction.findOneAndUpdate.mockResolvedValue(tx);
  return { stash, incomeProfile, tx };
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('pure savings calculations', () => {
  describe('calculateRoundUp', () => {
    test.each([
      [0, 0],
      [150, 0],
      [132, 18],
      [1, 49],
    ])('calculates %p as %p', (amount, expected) => {
      expect(calculateRoundUp(amount)).toBe(expected);
    });

    test('supports a custom increment', () => {
      expect(calculateRoundUp(132, 10)).toBe(8);
      expect(calculateRoundUp(100, 25)).toBe(0);
    });

    test('throws for negative amounts and non-positive increments', () => {
      expect(() => calculateRoundUp(-0.01)).toThrow(RangeError);
      expect(() => calculateRoundUp(10, 0)).toThrow(RangeError);
      expect(() => calculateRoundUp(10, -5)).toThrow(RangeError);
      expect(() => calculateRoundUp(10, Infinity)).toThrow(RangeError);
    });

    test('coerces null amount as zero, matching the implementation', () => {
      expect(calculateRoundUp(null)).toBe(0);
    });
  });

  describe('_computeMovingAverage', () => {
    test('averages the latest window and handles empty or null input', () => {
      expect(_computeMovingAverage([10, 20, 30], 2)).toBe(25);
      expect(_computeMovingAverage([10, 20], 30)).toBe(15);
      expect(_computeMovingAverage([])).toBe(0);
      expect(_computeMovingAverage(null)).toBe(0);
    });

    test('supports zero and negative window sizes as slice semantics dictate', () => {
      expect(_computeMovingAverage([10, 20], 0)).toBe(15);
      expect(_computeMovingAverage([10, 20, 30], -1)).toBe(25);
    });
  });

  describe('calculateIncomeSmoothing', () => {
    test.each([
      [2000, 1000, 0.1, 100],
      [1000, 1000, 0.1, 0],
      [900, 1000, 0.1, 0],
      [1500, 0, 0.1, 150],
      [1500, null, 0.1, 150],
      [0, 0, 0.1, 0],
    ])('calculates smoothing for %p, %p, %p', (payout, average, percentage, expected) => {
      expect(calculateIncomeSmoothing(payout, average, percentage)).toBe(expected);
    });

    test('supports custom percentages and rounds to two decimals', () => {
      expect(calculateIncomeSmoothing(150, 100, 0.25)).toBe(12.5);
      expect(calculateIncomeSmoothing(100.01, 100, 0.333)).toBe(0);
      expect(calculateIncomeSmoothing(100.04, 100, 0.333)).toBe(0.01);
    });

    test('throws for negative payouts and percentages outside [0, 1]', () => {
      expect(() => calculateIncomeSmoothing(-1, 0)).toThrow(RangeError);
      expect(() => calculateIncomeSmoothing(1, 0, -0.01)).toThrow(RangeError);
      expect(() => calculateIncomeSmoothing(1, 0, 1.01)).toThrow(RangeError);
      expect(() => calculateIncomeSmoothing(1, 0, NaN)).toThrow(RangeError);
    });
  });

  describe('updateRollingAverage', () => {
    test('appends, prunes to a custom window, and averages the result', () => {
      const date = new Date('2026-02-01T00:00:00.000Z');
      const result = updateRollingAverage(
        [{ amount: 100, date: new Date('2026-01-01T00:00:00.000Z') }, { amount: 200 }],
        { amount: 300, date },
        2
      );

      expect(result.prunedPayouts).toEqual([{ amount: 200 }, { amount: 300, date }]);
      expect(result.newAverage).toBe(250);
    });

    test('uses zero and negative window sizes according to slice behavior', () => {
      expect(updateRollingAverage([], { amount: 100 }, 0).newAverage).toBe(100);
      expect(updateRollingAverage([{ amount: 100 }, { amount: 200 }], { amount: 300 }, -1).newAverage).toBe(300);
    });
  });

  describe('mandate and threshold decisions', () => {
    test('allows the exact mandate cap and caps values above it', () => {
      expect(enforceMandateCap(1000)).toEqual({ approvedAmount: 1000, wasCapped: false });
      expect(enforceMandateCap(1001)).toEqual({ approvedAmount: 1000, wasCapped: true });
      expect(enforceMandateCap(120, 100)).toEqual({ approvedAmount: 100, wasCapped: true });
      expect(enforceMandateCap(null)).toEqual({ approvedAmount: null, wasCapped: false });
    });

    test('allows the exact minimum threshold and rejects values below it', () => {
      expect(meetsMinimumThreshold(100)).toBe(true);
      expect(meetsMinimumThreshold(99.99)).toBe(false);
      expect(meetsMinimumThreshold(100, 150)).toBe(false);
      expect(meetsMinimumThreshold(null)).toBe(false);
      expect(meetsMinimumThreshold(-1)).toBe(false);
    });
  });
});

describe('processContribution', () => {
  test('returns failure when the SavingsStash is missing', async () => {
    arrangeDatabase({ stash: null });
    const result = await processContribution({ userId, transaction: makeTransaction() });
    expect(result).toEqual({
      success: false,
      swept: false,
      sweptAmount: 0,
      newBalance: 0,
      pendingAfter: 0,
      reason: `No SavingsStash found for userId=${userId}. Create one on user registration.`,
      wasCapped: false,
    });
  });

  test('returns failure when the Transaction is missing', async () => {
    arrangeDatabase({ tx: null });
    const result = await processContribution({ userId, transaction: makeTransaction({ transactionId: 'missing' }) });
    expect(result.success).toBe(false);
    expect(result.reason).toBe('Transaction missing not found in DB.');
  });

  test('skips an already-processed transaction idempotently', async () => {
    const stash = makeStash({ currentBalance: 25, pendingContributions: 10 });
    arrangeDatabase({ stash, tx: makeTransaction({ isProcessed: true }) });
    const result = await processContribution({ userId, transaction: makeTransaction() });
    expect(result).toEqual({
      success: true,
      swept: false,
      sweptAmount: 0,
      newBalance: 25,
      pendingAfter: 10,
      reason: 'Transaction already processed — skipped (idempotent).',
      wasCapped: false,
    });
    expect(SavingsStash.findOneAndUpdate).not.toHaveBeenCalled();
  });

  test('accumulates a debit round-up without sweeping', async () => {
    const stash = makeStash({ pendingContributions: 80 });
    arrangeDatabase({ stash, tx: makeTransaction({ amount: 132 }) });
    const result = await processContribution({ userId, transaction: makeTransaction() });
    expect(result).toMatchObject({ success: true, swept: false, sweptAmount: 0, pendingAfter: 98, reason: 'minimum threshold not reached', wasCapped: false });
    expect(SavingsStash.findOneAndUpdate).toHaveBeenCalledWith(
      { userId },
      { $set: { pendingContributions: 98 } },
      { new: true }
    );
  });

  test('sweeps a debit that reaches the threshold', async () => {
    const stash = makeStash({ pendingContributions: 90, currentBalance: 20 });
    arrangeDatabase({ stash, tx: makeTransaction({ amount: 132 }) });
    const result = await processContribution({ userId, transaction: makeTransaction() });
    expect(result).toMatchObject({ success: true, swept: true, sweptAmount: 108, newBalance: 128, pendingAfter: 0, reason: 'UPI AutoPay sweep authorized', wasCapped: false });
    expect(SavingsStash.findOneAndUpdate).toHaveBeenCalledWith(
      { userId },
      expect.objectContaining({ $set: expect.objectContaining({ pendingContributions: 0, currentBalance: 128 }), $push: expect.objectContaining({ sweepHistory: expect.objectContaining({ amount: 108, type: 'roundup', triggeringTransactionId: 'tx-1' }) }) }),
      { new: true }
    );
  });

  test('does not sweep a payout above the mandate cap', async () => {
    const stash = makeStash({ pendingContributions: 950 });
    arrangeDatabase({ stash, tx: makeTransaction({ type: 'payout', amount: 600 }) });
    const result = await processContribution({ userId, transaction: makeTransaction() });
    expect(result).toMatchObject({ success: true, swept: false, sweptAmount: 0, pendingAfter: 1010, reason: 'mandate limit exceeded', wasCapped: true });
    expect(SavingsStash.findOneAndUpdate).toHaveBeenCalledWith({ userId }, { $set: { pendingContributions: 1010 } }, { new: true });
  });

  test('persists the updated rolling average for a payout', async () => {
    const incomeProfile = { currentRollingAverage: 1000, rolling30DayPayouts: [{ amount: 1000 }] };
    arrangeDatabase({ incomeProfile, tx: makeTransaction({ type: 'payout', amount: 2000 }) });
    const result = await processContribution({ userId, transaction: makeTransaction(), surplusPercentage: 0.1 });
    expect(result).toMatchObject({ success: true, swept: true, sweptAmount: 100, newBalance: 100, pendingAfter: 0 });
    expect(IncomeProfile.findOneAndUpdate).toHaveBeenCalledWith(
      { userId },
      { $set: { rolling30DayPayouts: [{ amount: 1000 }, { amount: 2000, date: expect.any(Date) }], currentRollingAverage: 1500 } },
      { upsert: true, new: true }
    );
  });

  test('returns failure for an unknown transaction type', async () => {
    arrangeDatabase({ tx: makeTransaction({ type: 'refund' }) });
    const result = await processContribution({ userId, transaction: makeTransaction() });
    expect(result.success).toBe(false);
    expect(result.reason).toBe('Unknown transaction type "refund". Must be "debit" or "payout".');
  });

  test('catches database errors and returns success false', async () => {
    SavingsStash.findOne.mockRejectedValue(new Error('database unavailable'));
    IncomeProfile.findOne.mockResolvedValue(null);
    Transaction.findOne.mockResolvedValue(makeTransaction());
    const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    const result = await processContribution({ userId, transaction: makeTransaction() });
    expect(result).toMatchObject({ success: false, reason: 'Unexpected error: database unavailable' });
    expect(errorSpy).toHaveBeenCalled();
    errorSpy.mockRestore();
  });
});
