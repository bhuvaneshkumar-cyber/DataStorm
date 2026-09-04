"""Coverage for the webhook boundary ported off the retired Node service.

Split in two: the parsing/auth layer is pure and tested directly, while the
pending-contribution replay is tested against a stub session so the suite runs
without a live Supabase connection.
"""

import hashlib
import hmac
import os
import unittest
import uuid

# database.py refuses to import without DATABASE_URL (by design - the service must
# never silently fall back to a local database). SQLAlchemy resolves the URL
# lazily, so a placeholder is enough to import the module under test; nothing
# here opens a connection.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

import webhooks  # noqa: E402
from db_service import STATUS_PENDING, STATUS_SWEPT, get_pending_contributions  # noqa: E402

SECRET = "test-secret"
USER_ID = "c666bc75-751c-4e4b-866b-af5b0393d131"


def payload(**overrides):
    base = {
        "userId": USER_ID,
        "type": "debit",
        "amount": 132,
        "source": "Swiggy",
        "timestamp": "2026-09-03T10:00:00Z",
    }
    base.update(overrides)
    return base


class SignatureTests(unittest.TestCase):
    def setUp(self):
        os.environ["WEBHOOK_SECRET"] = SECRET

    def tearDown(self):
        os.environ.pop("WEBHOOK_SECRET", None)

    def _sign(self, body: bytes) -> str:
        return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()

    def test_valid_signature_passes(self):
        body = b'{"userId":"x"}'
        webhooks.authenticate(body, self._sign(body), None)

    def test_signature_over_different_bytes_fails(self):
        body = b'{"userId":"x"}'
        with self.assertRaises(webhooks.WebhookAuthError):
            webhooks.authenticate(b'{"userId":"y"}', self._sign(body), None)

    def test_shared_secret_header_passes(self):
        webhooks.authenticate(b"{}", None, SECRET)

    def test_wrong_shared_secret_fails(self):
        with self.assertRaises(webhooks.WebhookAuthError):
            webhooks.authenticate(b"{}", None, "nope")

    def test_no_credentials_fails(self):
        with self.assertRaises(webhooks.WebhookAuthError):
            webhooks.authenticate(b"{}", None, None)

    def test_fails_closed_when_secret_unset(self):
        os.environ.pop("WEBHOOK_SECRET")
        with self.assertRaises(webhooks.WebhookAuthError):
            webhooks.authenticate(b"{}", None, SECRET)


class ParseEventTests(unittest.TestCase):
    def test_debit_normalises_to_ledger_vocabulary(self):
        event = webhooks.parse_event(payload())
        self.assertEqual(event.transaction_type, "debit")
        self.assertEqual(event.amount, 132.0)
        self.assertEqual(event.user_id, uuid.UUID(USER_ID))

    def test_payout_is_renamed_to_platform_payout(self):
        event = webhooks.parse_event(payload(type="payout", amount=2000))
        self.assertEqual(event.transaction_type, "platform_payout")

    def test_missing_fields_are_reported_together(self):
        body = payload()
        del body["source"]
        del body["timestamp"]
        with self.assertRaises(webhooks.WebhookValidationError) as ctx:
            webhooks.parse_event(body)
        self.assertIn("source", str(ctx.exception))
        self.assertIn("timestamp", str(ctx.exception))

    def test_unknown_type_rejected(self):
        with self.assertRaises(webhooks.WebhookValidationError):
            webhooks.parse_event(payload(type="transfer"))

    def test_negative_amount_rejected(self):
        with self.assertRaises(webhooks.WebhookValidationError):
            webhooks.parse_event(payload(amount=-1))

    def test_unparseable_timestamp_rejected(self):
        with self.assertRaises(webhooks.WebhookValidationError):
            webhooks.parse_event(payload(timestamp="last tuesday"))

    def test_non_uuid_user_rejected(self):
        with self.assertRaises(webhooks.WebhookValidationError):
            webhooks.parse_event(payload(userId="mira"))

    def test_derived_id_is_stable_for_a_replayed_payload(self):
        first = webhooks.parse_event(payload())
        second = webhooks.parse_event(payload())
        self.assertEqual(first.transaction_id, second.transaction_id)

    def test_derived_id_changes_with_the_payload(self):
        first = webhooks.parse_event(payload())
        second = webhooks.parse_event(payload(amount=133))
        self.assertNotEqual(first.transaction_id, second.transaction_id)

    def test_aware_timestamp_is_normalised_to_naive_utc(self):
        """Ledger rows are naive UTC; a webhook offset must convert, not shift."""
        event = webhooks.parse_event(payload(timestamp="2026-09-03T15:30:00+05:30"))
        self.assertIsNone(event.timestamp.tzinfo)
        self.assertEqual(event.timestamp.isoformat(), "2026-09-03T10:00:00")

    def test_naive_timestamp_is_taken_as_utc(self):
        event = webhooks.parse_event(payload(timestamp="2026-09-03T10:00:00"))
        self.assertEqual(event.timestamp.isoformat(), "2026-09-03T10:00:00")

    def test_caller_supplied_transaction_id_wins(self):
        explicit = uuid.uuid4()
        event = webhooks.parse_event(payload(transactionId=str(explicit)))
        self.assertEqual(event.transaction_id, explicit)


class StubRecord:
    """Stands in for a TransactionRecord row."""

    def __init__(self, amount, transaction_type, status=STATUS_PENDING, timestamp=0):
        self.id = uuid.uuid4()
        self.amount = amount
        self.transaction_type = transaction_type
        self.status = status
        self.timestamp = timestamp


class StubQuery:
    def __init__(self, records):
        self._records = records

    def filter(self, *_args):
        return self

    def order_by(self, *_args):
        # Callers order newest-first and reverse; hand back the reverse of the
        # chronological fixture so the replay sees it oldest-first.
        return StubQuery(list(reversed(self._records)))

    def limit(self, _n):
        return self

    def all(self):
        return self._records


class StubSession:
    def __init__(self, records):
        self._records = records

    def query(self, *_args):
        return StubQuery(self._records)


class PendingContributionTests(unittest.TestCase):
    def test_debits_accumulate_round_ups(self):
        session = StubSession([StubRecord(132, "debit"), StubRecord(97, "debit")])
        roundups, surplus, pending = get_pending_contributions(session, USER_ID)
        self.assertEqual(roundups, 21.0)  # 18 + 3
        self.assertEqual(surplus, 0.0)
        self.assertEqual(len(pending), 2)

    def test_payout_surplus_uses_history_at_the_time_it_landed(self):
        history = [StubRecord(1000, "platform_payout", status=STATUS_SWEPT) for _ in range(30)]
        session = StubSession(history + [StubRecord(2000, "platform_payout")])
        roundups, surplus, pending = get_pending_contributions(session, USER_ID)
        self.assertEqual(roundups, 0.0)
        self.assertEqual(surplus, 100.0)  # 10% of the 1000 above average
        self.assertEqual(len(pending), 1)

    def test_swept_rows_no_longer_count_as_pending(self):
        session = StubSession(
            [StubRecord(132, "debit", status=STATUS_SWEPT), StubRecord(132, "debit")]
        )
        roundups, _surplus, pending = get_pending_contributions(session, USER_ID)
        self.assertEqual(roundups, 18.0)
        self.assertEqual(len(pending), 1)

    def test_accumulation_crosses_the_sweep_threshold(self):
        """The behaviour the Node stash existed to provide: many small
        round-ups eventually add up to a sweepable total."""
        from savings import sweep_decision

        session = StubSession([StubRecord(1, "debit") for _ in range(3)])
        roundups, surplus, _ = get_pending_contributions(session, USER_ID)
        self.assertEqual(roundups, 147.0)  # 49 x 3
        self.assertTrue(sweep_decision(roundups, surplus).eligible)


if __name__ == "__main__":
    unittest.main()
