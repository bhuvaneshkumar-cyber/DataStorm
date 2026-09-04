"""API boundary tests for the Python FastAPI application."""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


class TransactionEndpointTests(unittest.TestCase):
    def setUp(self):
        main.app.dependency_overrides[main.get_db] = lambda: object()
        self.client = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    @patch("main.db_service.add_transaction")
    def test_payout_input_is_stored_as_platform_payout(self, add_transaction):
        add_transaction.return_value = {
            "transaction_type": "platform_payout",
            "sweep_decision": {"amount": 100.0, "eligible": True, "reason": "threshold reached"},
        }

        response = self.client.post(
            "/api/transactions",
            json={
                "user_id": "c666bc75-751c-4e4b-866b-af5b0393d131",
                "amount": 2000,
                "transaction_type": "payout",
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(add_transaction.call_args.kwargs["transaction_type"], "platform_payout")

    def test_internal_platform_payout_is_not_accepted_as_external_input(self):
        response = self.client.post(
            "/api/transactions",
            json={
                "user_id": "c666bc75-751c-4e4b-866b-af5b0393d131",
                "amount": 2000,
                "transaction_type": "platform_payout",
            },
        )

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()