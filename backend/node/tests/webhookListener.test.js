'use strict';

jest.mock('../src/models/Transaction', () => ({
  findOne: jest.fn(),
  findOneAndUpdate: jest.fn(),
}));

jest.mock('../src/services/savingsEngine', () => ({
  processContribution: jest.fn(),
}));

const Transaction = require('../src/models/Transaction');
const { processContribution } = require('../src/services/savingsEngine');
const { handleTransactionWebhook } = require('../src/listeners/webhookListener');

const payload = {
  userId: 'user-1',
  type: 'debit',
  amount: 132,
  source: 'HDFC Bank',
  timestamp: '2026-09-03T12:00:00.000Z',
  transactionId: 'tx-1',
};

const engineResult = {
  success: true,
  swept: false,
  sweptAmount: 0,
  newBalance: 20,
  pendingAfter: 18,
  reason: 'minimum threshold not reached',
  wasCapped: false,
};

beforeEach(() => {
  jest.clearAllMocks();
  Transaction.findOne.mockResolvedValue(null);
  Transaction.findOneAndUpdate.mockResolvedValue({ transactionId: 'tx-1' });
  processContribution.mockResolvedValue(engineResult);
});

describe('handleTransactionWebhook', () => {
  test('validates and processes a debit webhook', async () => {
    const result = await handleTransactionWebhook(payload);

    expect(result).toEqual({
      statusCode: 200,
      body: { transactionId: 'tx-1', ...engineResult, success: undefined },
    });
    expect(Transaction.findOne).toHaveBeenCalledWith({ transactionId: 'tx-1' });
    expect(Transaction.findOneAndUpdate).toHaveBeenCalledWith(
      { transactionId: 'tx-1' },
      expect.objectContaining({ $setOnInsert: expect.objectContaining({ type: 'debit', amount: 132 }) }),
      { upsert: true, new: true, setDefaultsOnInsert: true }
    );
    expect(processContribution).toHaveBeenCalledWith({
      userId: 'user-1',
      transaction: { transactionId: 'tx-1' },
    });
  });

  test('processes a valid payout webhook', async () => {
    processContribution.mockResolvedValue({ ...engineResult, swept: true, sweptAmount: 100 });
    const result = await handleTransactionWebhook({ ...payload, type: 'payout', transactionId: 'payout-1' });

    expect(result.statusCode).toBe(200);
    expect(result.body).toMatchObject({ transactionId: 'payout-1', swept: true, sweptAmount: 100 });
    expect(Transaction.findOneAndUpdate).toHaveBeenCalledWith(
      { transactionId: 'payout-1' },
      expect.objectContaining({ $setOnInsert: expect.objectContaining({ type: 'payout' }) }),
      expect.any(Object)
    );
  });

  test('returns 400 for missing and malformed fields without database work', async () => {
    const result = await handleTransactionWebhook({ ...payload, amount: -1, source: '' });

    expect(result).toEqual({ statusCode: 400, body: { error: 'Missing required fields: source' } });
    expect(Transaction.findOne).not.toHaveBeenCalled();

    const malformed = await handleTransactionWebhook({ ...payload, amount: 'not-a-number' });
    expect(malformed).toEqual({
      statusCode: 400,
      body: { error: 'Invalid amount "not-a-number". Must be a non-negative number.' },
    });

    const emptyPayload = await handleTransactionWebhook();
    expect(emptyPayload.statusCode).toBe(400);
    expect(emptyPayload.body.error).toContain('Missing required fields');
  });

  test('returns 500 and marks the transaction failed when the engine throws', async () => {
    processContribution.mockRejectedValue(new Error('engine unavailable'));
    const result = await handleTransactionWebhook(payload);

    expect(result).toEqual({
      statusCode: 500,
      body: { error: 'Internal processing error. Transaction marked failed for replay.' },
    });
    expect(Transaction.findOneAndUpdate).toHaveBeenLastCalledWith(
      { transactionId: 'tx-1' },
      { $set: { status: 'failed', isProcessed: false } }
    );
  });
});