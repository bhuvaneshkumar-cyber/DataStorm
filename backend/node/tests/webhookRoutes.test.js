'use strict';

const request = require('supertest');

jest.mock('../src/models/Transaction', () => ({
  findOne: jest.fn(),
  findOneAndUpdate: jest.fn(),
}));

jest.mock('../src/models/SavingsStash', () => ({
  findOne: jest.fn(),
  findOneAndUpdate: jest.fn(),
}));

jest.mock('../src/services/savingsEngine', () => ({
  processContribution: jest.fn(),
  meetsMinimumThreshold: jest.fn(),
  enforceMandateCap: jest.fn(),
}));

const Transaction = require('../src/models/Transaction');
const { processContribution } = require('../src/services/savingsEngine');
const app = require('../src/app');

const validPayload = {
  userId: 'user-1',
  type: 'debit',
  amount: 132,
  source: 'HDFC Bank',
  timestamp: '2026-09-03T12:00:00.000Z',
  transactionId: 'tx-http-1',
};

beforeEach(() => {
  process.env.WEBHOOK_SECRET = 'test-secret';
  jest.clearAllMocks();
  Transaction.findOne.mockResolvedValue(null);
  Transaction.findOneAndUpdate.mockResolvedValue({ transactionId: validPayload.transactionId });
  processContribution.mockResolvedValue({
    success: true,
    swept: false,
    sweptAmount: 0,
    newBalance: 0,
    pendingAfter: 18,
    reason: 'minimum threshold not reached',
    wasCapped: false,
  });
});

describe('POST /webhooks/transaction', () => {
  test('returns the engine result for a valid debit webhook', async () => {
    const response = await request(app)
      .post('/webhooks/transaction')
      .set('x-webhook-secret', 'test-secret')
      .send(validPayload);

    expect(response.status).toBe(200);
    expect(response.body).toMatchObject({ transactionId: 'tx-http-1', swept: false, pendingAfter: 18 });
  });

  test('returns the engine result for a valid payout webhook', async () => {
    processContribution.mockResolvedValue({
      success: true,
      swept: true,
      sweptAmount: 100,
      newBalance: 100,
      pendingAfter: 0,
      reason: 'UPI AutoPay sweep authorized',
      wasCapped: false,
    });

    const response = await request(app)
      .post('/webhooks/transaction')
      .set('x-webhook-secret', 'test-secret')
      .send({ ...validPayload, type: 'payout', transactionId: 'tx-http-payout' });

    expect(response.status).toBe(200);
    expect(response.body).toMatchObject({ transactionId: 'tx-http-payout', swept: true, sweptAmount: 100 });
  });

  test('returns 400 for a malformed payload', async () => {
    const response = await request(app)
      .post('/webhooks/transaction')
      .set('x-webhook-secret', 'test-secret')
      .send({ userId: 'user-1', type: 'debit', amount: 'bad' });

    expect(response.status).toBe(400);
    expect(response.body.error).toContain('Missing required fields');
    expect(processContribution).not.toHaveBeenCalled();
  });

  test('returns 500 when processContribution throws', async () => {
    processContribution.mockRejectedValue(new Error('engine exploded'));
    const response = await request(app)
      .post('/webhooks/transaction')
      .set('x-webhook-secret', 'test-secret')
      .send(validPayload);

    expect(response.status).toBe(500);
    expect(response.body).toEqual({ error: 'Internal processing error. Transaction marked failed for replay.' });
  });

  test('returns 400 for malformed JSON instead of crashing', async () => {
    const response = await request(app)
      .post('/webhooks/transaction')
      .set('x-webhook-secret', 'test-secret')
      .set('content-type', 'application/json')
      .send('{"userId":');

    expect(response.status).toBe(400);
    expect(response.body).toEqual({ error: 'Malformed JSON request body.' });
  });
});

describe('GET /health', () => {
  const originalMongoUri = process.env.MONGODB_URI;
  const originalMongoAlias = process.env.MONGO_URI;

  afterEach(() => {
    if (originalMongoUri === undefined) delete process.env.MONGODB_URI;
    else process.env.MONGODB_URI = originalMongoUri;
    if (originalMongoAlias === undefined) delete process.env.MONGO_URI;
    else process.env.MONGO_URI = originalMongoAlias;
  });

  test('returns basic health data without a configured database', async () => {
    delete process.env.MONGODB_URI;
    delete process.env.MONGO_URI;

    const response = await request(app).get('/health');

    expect(response.status).toBe(200);
    expect(response.body).toMatchObject({ status: 'ok' });
    expect(typeof response.body.uptime).toBe('number');
    expect(Number.isNaN(Date.parse(response.body.timestamp))).toBe(false);
    expect(response.body.db).toBeUndefined();
  });

  test('reports a configured but disconnected database without throwing', async () => {
    process.env.MONGODB_URI = 'mongodb://127.0.0.1:27017/gigsave-test';
    delete process.env.MONGO_URI;

    const response = await request(app).get('/health');

    expect(response.status).toBe(200);
    expect(response.body).toMatchObject({ status: 'ok', db: 'disconnected' });
  });
});