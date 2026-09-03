const { handleTransactionWebhook, handleSweepWebhook } = require('../src/listeners/webhookListener');

function mockRes() {
  const res = {};
  res.status = jest.fn().mockReturnValue(res);
  res.json = jest.fn().mockReturnValue(res);
  return res;
}

describe('webhook payload validation (no DB required — rejected before any query)', () => {
  test('rejects a NoSQL-injection userId on the transaction route', async () => {
    const res = mockRes();
    await handleTransactionWebhook(
      { body: { userId: { $ne: null }, transactionId: 'tx1', type: 'debit', amount: 132 } },
      res
    );
    expect(res.status).toHaveBeenCalledWith(400);
  });

  test('rejects a NoSQL-injection transactionId on the transaction route', async () => {
    const res = mockRes();
    await handleTransactionWebhook(
      { body: { userId: 'u1', transactionId: { $gt: '' }, type: 'debit', amount: 132 } },
      res
    );
    expect(res.status).toHaveBeenCalledWith(400);
  });

  test('rejects an unknown transaction type', async () => {
    const res = mockRes();
    await handleTransactionWebhook(
      { body: { userId: 'u1', transactionId: 'tx1', type: 'transfer', amount: 132 } },
      res
    );
    expect(res.status).toHaveBeenCalledWith(400);
  });

  test('rejects a NoSQL-injection userId on the sweep route', async () => {
    const res = mockRes();
    await handleSweepWebhook({ body: { userId: { $ne: null } } }, res);
    expect(res.status).toHaveBeenCalledWith(400);
  });
});
