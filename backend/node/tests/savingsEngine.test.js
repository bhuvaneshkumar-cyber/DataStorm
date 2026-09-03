const {
  calculateRoundUp,
  calculateIncomeSmoothing,
  _computeMovingAverage,
  enforceMandateCap,
  meetsMinimumThreshold,
} = require('../src/services/savingsEngine');

describe('savings engine', () => {
  test('rounds a debit up to the nearest fifty', () => {
    expect(calculateRoundUp(132)).toBe(18);
    expect(calculateRoundUp(150)).toBe(0);
  });

  test('calculates surplus over the rolling average', () => {
    expect(_computeMovingAverage([1000, 1000, 1000])).toBe(1000);
    expect(calculateIncomeSmoothing(2000, 1000, 0.1)).toBe(100);
    expect(calculateIncomeSmoothing(900, 1000, 0.1)).toBe(0);
  });

  test('enforces the savings threshold and mandate cap', () => {
    expect(meetsMinimumThreshold(100)).toBe(true);
    expect(meetsMinimumThreshold(99.99)).toBe(false);
    expect(enforceMandateCap(1200, 1000).wasCapped).toBe(true);
    expect(enforceMandateCap(800, 1000).wasCapped).toBe(false);
  });
});
