const crypto = require('crypto');
const { verifyWebhookSignature, roundInr } = require('../src/utils');

describe('webhook signature verification', () => {
  const secret = 'test-secret';
  const body = Buffer.from(JSON.stringify({ userId: 'u1', amount: 132 }));
  const validSignature = crypto.createHmac('sha256', secret).update(body).digest('hex');

  test('accepts a correctly signed payload', () => {
    expect(verifyWebhookSignature(body, validSignature, secret)).toBe(true);
  });

  test('rejects a tampered payload', () => {
    const tampered = Buffer.from(JSON.stringify({ userId: 'u1', amount: 999999 }));
    expect(verifyWebhookSignature(tampered, validSignature, secret)).toBe(false);
  });

  test('rejects a wrong secret', () => {
    expect(verifyWebhookSignature(body, validSignature, 'wrong-secret')).toBe(false);
  });

  test('rejects a missing signature or secret', () => {
    expect(verifyWebhookSignature(body, '', secret)).toBe(false);
    expect(verifyWebhookSignature(body, validSignature, '')).toBe(false);
    expect(verifyWebhookSignature(null, validSignature, secret)).toBe(false);
  });

  test('rejects a signature of a different length without throwing', () => {
    expect(verifyWebhookSignature(body, 'short', secret)).toBe(false);
  });
});

describe('roundInr', () => {
  test('rounds to 2 decimal places', () => {
    expect(roundInr(18.005)).toBe(18.01);
    expect(roundInr(18)).toBe(18);
  });
});
