"""End-to-end API tests: authentication, ownership, roles, and the money routes.

Runs the real application against in-memory SQLite with the scoring service
stubbed out. That combination is what makes these worth having: they exercise
the actual dependency graph and the actual authorization rules, but need neither
a Postgres instance nor a second process to be running.

The scoring stub is deliberate rather than lazy. What is under test here is
"does a worker's own score reach the loan gate", not "is the model accurate" --
that belongs to the scoring service's own suite.
"""

import logging
import os
import unittest
import uuid
from datetime import date
from unittest.mock import patch

# Must be set before `database` is imported, since the engine is built at import
# time from whatever DATABASE_URL then holds.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-outside-this-suite")

# httpx logs every TestClient call at INFO, which buries the actual results.
logging.getLogger("httpx").setLevel(logging.WARNING)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import main  # noqa: E402
from database import Base, get_db  # noqa: E402
from models import ROLE_LENDER, ROLE_WORKER  # noqa: E402

# StaticPool with a shared in-memory URL: without it every connection gets its
# own empty database and nothing written in a request survives to the next one.
_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    db = _Session()
    try:
        yield db
    finally:
        db.close()


# A representative scored applicant: comfortably approvable, so tests that are
# about authorization are not accidentally about being declined.
GOOD_SCORE = {
    "final_score": 690.0,
    "category": "Good",
    "confidence": 0.82,
    "rule_score": 640.0,
    "ml_score": 720.0,
    "ml_available": True,
    "explanation": [],
    "latency_ms": 4.2,
    "risk_assessment": {
        "risk_grade": {"code": "GS-1", "label": "Minimal Risk"},
        "risk_tier": "LOW",
        "decision": "APPROVE",
        "indicative_interest_rate_pct": 15.5,
        "risk_premium_bps": 150,
        "max_credit_limit_inr": 120_000.0,
        "recommended_tenor_months": 24,
        "conditions": [],
        "early_warning_signals": [],
    },
}

POOR_SCORE = {
    **GOOD_SCORE,
    "final_score": 310.0,
    "category": "Poor",
    "risk_assessment": {
        **GOOD_SCORE["risk_assessment"],
        "risk_grade": {"code": "GS-6", "label": "Substandard"},
        "risk_tier": "VERY_HIGH",
        "decision": "DECLINE",
        "max_credit_limit_inr": 0.0,
        "recommended_tenor_months": 0,
    },
}


class ApiTestCase(unittest.TestCase):
    """Shared fixture: a fresh schema and a signed-in worker per test."""

    @classmethod
    def setUpClass(cls):
        main.app.dependency_overrides[get_db] = _override_get_db
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        main.app.dependency_overrides.clear()
        cls.client.close()
        _engine.dispose()

    def setUp(self):
        # Dropped and recreated per test so one test's rows cannot decide
        # another's outcome through ordering.
        Base.metadata.drop_all(bind=_engine)
        Base.metadata.create_all(bind=_engine)

    # -- helpers ----------------------------------------------------------- #

    def register(self, role=ROLE_WORKER, email=None, **extra):
        payload = {
            "name": "Test Person",
            "email": email or f"{uuid.uuid4().hex[:10]}@example.com",
            "password": "a-good-password",
            "role": role,
            **extra,
        }
        response = self.client.post("/api/auth/register", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json(), payload

    def auth(self, body):
        return {"Authorization": f"Bearer {body['access_token']}"}

    def log(self, headers, amount, kind, **extra):
        response = self.client.post(
            "/api/transactions",
            json={"amount": amount, "transaction_type": kind, **extra},
            headers=headers,
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()


class AuthenticationTests(ApiTestCase):
    def test_register_then_read_own_profile(self):
        body, payload = self.register(language="ta", employment_type="Delivery rider")
        self.assertEqual(body["user"]["email"], payload["email"])
        self.assertEqual(body["user"]["role"], ROLE_WORKER)
        self.assertEqual(body["user"]["language"], "ta")

        me = self.client.get("/api/auth/me", headers=self.auth(body))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["employment_type"], "Delivery rider")

    def test_password_is_never_returned_or_stored_in_clear(self):
        body, payload = self.register()
        self.assertNotIn("password", body["user"])
        self.assertNotIn("password_hash", body["user"])

        with _Session() as db:
            from models import User

            stored = db.query(User).filter(User.email == payload["email"]).one()
        self.assertIsNotNone(stored.password_hash)
        self.assertNotIn(payload["password"], stored.password_hash)

    def test_duplicate_email_is_rejected(self):
        _, payload = self.register()
        again = self.client.post("/api/auth/register", json={**payload, "name": "Someone else"})
        self.assertEqual(again.status_code, 409)

    def test_short_password_is_rejected(self):
        response = self.client.post(
            "/api/auth/register",
            json={"name": "X", "email": "short@example.com", "password": "abc"},
        )
        self.assertEqual(response.status_code, 422)

    def test_login_succeeds_and_wrong_password_fails_identically_to_unknown_email(self):
        _, payload = self.register()

        ok = self.client.post(
            "/api/auth/login", json={"email": payload["email"], "password": payload["password"]}
        )
        self.assertEqual(ok.status_code, 200)

        wrong = self.client.post(
            "/api/auth/login", json={"email": payload["email"], "password": "not-the-password"}
        )
        unknown = self.client.post(
            "/api/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
        )
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(unknown.status_code, 401)
        # Identical wording: differing messages would let the form enumerate accounts.
        self.assertEqual(wrong.json()["detail"], unknown.json()["detail"])

    def test_login_at_the_wrong_door_is_refused(self):
        _, payload = self.register(role=ROLE_WORKER)
        response = self.client.post(
            "/api/auth/login",
            json={
                "email": payload["email"],
                "password": payload["password"],
                "expected_role": ROLE_LENDER,
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_protected_routes_reject_missing_and_forged_tokens(self):
        self.assertEqual(self.client.get("/api/dashboard").status_code, 401)
        self.assertEqual(
            self.client.get(
                "/api/dashboard", headers={"Authorization": "Bearer not-a-real-token"}
            ).status_code,
            401,
        )

    def test_profile_patch_updates_only_what_was_sent(self):
        body, _ = self.register(employment_type="Rider")
        headers = self.auth(body)

        response = self.client.patch("/api/auth/me", json={"language": "hi"}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["language"], "hi")
        # Untouched field survives the patch.
        self.assertEqual(response.json()["employment_type"], "Rider")

    def test_role_cannot_be_escalated_through_the_profile_patch(self):
        body, _ = self.register(role=ROLE_WORKER)
        headers = self.auth(body)

        self.client.patch("/api/auth/me", json={"role": ROLE_LENDER}, headers=headers)
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).json()["role"], ROLE_WORKER)
        self.assertEqual(self.client.get("/api/loans/queue", headers=headers).status_code, 403)


class OwnershipTests(ApiTestCase):
    def test_a_worker_sees_only_their_own_transactions(self):
        first, _ = self.register()
        second, _ = self.register()

        self.log(self.auth(first), 500.0, "platform_payout", merchant="Swiggy")

        mine = self.client.get("/api/transactions", headers=self.auth(first)).json()
        theirs = self.client.get("/api/transactions", headers=self.auth(second)).json()
        self.assertEqual(len(mine), 1)
        self.assertEqual(theirs, [])

    def test_a_worker_cannot_touch_another_workers_platform(self):
        owner, _ = self.register()
        stranger, _ = self.register()

        created = self.client.post(
            "/api/platforms", json={"platform": "Swiggy"}, headers=self.auth(owner)
        )
        self.assertEqual(created.status_code, 201, created.text)
        account_id = created.json()["id"]

        # 404, not 403: confirming the id exists would itself be a leak.
        self.assertEqual(
            self.client.delete(
                f"/api/platforms/{account_id}", headers=self.auth(stranger)
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/platforms/{account_id}", headers=self.auth(owner)
            ).status_code,
            204,
        )

    def test_lender_routes_are_closed_to_workers_and_worker_routes_to_lenders(self):
        worker, _ = self.register(role=ROLE_WORKER)
        lender, _ = self.register(role=ROLE_LENDER)

        self.assertEqual(self.client.get("/api/loans/queue", headers=self.auth(worker)).status_code, 403)
        self.assertEqual(self.client.get("/api/loans/queue", headers=self.auth(lender)).status_code, 200)
        self.assertEqual(self.client.get("/api/dashboard", headers=self.auth(lender)).status_code, 403)
        self.assertEqual(self.client.get("/api/tax/summary", headers=self.auth(lender)).status_code, 403)


class MoneyTests(ApiTestCase):
    def test_logging_a_debit_returns_the_sweep_it_would_trigger(self):
        body, _ = self.register()
        headers = self.auth(body)

        result = self.log(headers, 132.0, "debit", merchant="Fuel", category="Fuel")
        # 132 rounds up to 150, so 18 is pending -- under the 100 threshold.
        self.assertEqual(result["sweep_decision"]["amount"], 18.0)
        self.assertFalse(result["sweep_decision"]["eligible"])

    def test_expense_summary_splits_income_from_spend(self):
        body, _ = self.register()
        headers = self.auth(body)

        self.log(headers, 9000.0, "platform_payout", category="Swiggy")
        self.log(headers, 1200.0, "debit", category="Fuel")
        self.log(headers, 300.0, "debit", category="Food")

        summary = self.client.get("/api/expenses/summary", headers=headers).json()
        self.assertEqual(summary["total_income"], 9000.0)
        self.assertEqual(summary["total_expense"], 1500.0)
        self.assertEqual(summary["net"], 7500.0)
        self.assertEqual(summary["expense_categories"][0]["category"], "Fuel")
        self.assertEqual(len(summary["daily"]), 1)

    def test_authorized_sweep_lands_in_the_stash_and_the_dashboard(self):
        body, _ = self.register()
        headers = self.auth(body)

        created = self.client.post("/api/sweeps", json={"sweep_amount": 250.0}, headers=headers)
        self.assertEqual(created.status_code, 201, created.text)

        dashboard = self.client.get("/api/dashboard", headers=headers).json()
        self.assertEqual(dashboard["total_stash_balance"], 250.0)
        self.assertEqual(len(dashboard["recent_sweeps"]), 1)

    def test_invalid_transaction_type_and_amount_are_rejected(self):
        body, _ = self.register()
        headers = self.auth(body)

        for payload in (
            {"amount": 100.0, "transaction_type": "gift"},
            {"amount": -5.0, "transaction_type": "debit"},
            {"amount": 0.0, "transaction_type": "debit"},
        ):
            self.assertEqual(
                self.client.post("/api/transactions", json=payload, headers=headers).status_code,
                422,
                payload,
            )


class PlatformTests(ApiTestCase):
    def test_connecting_the_same_platform_twice_is_refused(self):
        body, _ = self.register()
        headers = self.auth(body)

        self.assertEqual(
            self.client.post("/api/platforms", json={"platform": "Uber"}, headers=headers).status_code,
            201,
        )
        # Case-insensitive: "uber" and "Uber" are the same connection.
        self.assertEqual(
            self.client.post("/api/platforms", json={"platform": "uber"}, headers=headers).status_code,
            409,
        )

    def test_income_profile_prefers_the_ledger_over_the_declared_figures(self):
        # An exact calendar birthday: 365*30 days lands a day short of 30 years
        # once leap days are counted, and would assert against an age of 29.
        today = date.today()
        thirtieth_birthday = today.replace(year=today.year - 30)
        body, _ = self.register(date_of_birth=str(thirtieth_birthday))
        headers = self.auth(body)

        self.client.post(
            "/api/platforms",
            json={
                "platform": "Swiggy",
                "customer_rating": 4.8,
                "weekly_payout": 3000,
                "gigs_per_week": 40,
                "hours_per_week": 35,
            },
            headers=headers,
        )
        self.log(headers, 9000.0, "platform_payout")

        profile = self.client.get("/api/platforms/income-profile", headers=headers).json()
        self.assertEqual(profile["primary_gig_platform"], "Food Delivery")
        self.assertEqual(profile["platform_customer_rating"], 4.8)
        # Measured 9000 wins over the 3000 declared on the connection form.
        self.assertEqual(profile["average_weekly_payout"], 9000.0)
        self.assertEqual(profile["connected_platforms"], 1)
        self.assertEqual(profile["verified_platforms"], 0)
        self.assertEqual(profile["age"], 30)

    def test_a_bare_profile_names_every_assumption_it_had_to_make(self):
        body, _ = self.register()
        profile = self.client.get(
            "/api/platforms/income-profile", headers=self.auth(body)
        ).json()
        self.assertEqual(profile["primary_gig_platform"], "Other")
        self.assertGreaterEqual(len(profile["assumptions"]), 4)


@patch("scoring_client.score_applicant", return_value=GOOD_SCORE)
class LoanTests(ApiTestCase):
    def test_eligibility_reports_the_ceiling_from_the_risk_assessment(self, _score):
        body, _ = self.register()
        verdict = self.client.get("/api/loans/eligibility", headers=self.auth(body)).json()
        self.assertTrue(verdict["eligible"])
        self.assertEqual(verdict["max_amount_inr"], 120_000.0)
        self.assertEqual(verdict["max_tenor_months"], 24)

    def test_applying_freezes_the_server_derived_score_onto_the_row(self, _score):
        body, _ = self.register()
        headers = self.auth(body)

        created = self.client.post(
            "/api/loans", json={"amount": 20_000, "tenor_months": 12, "purpose": "Repair"}, headers=headers
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["credit_score"], 690.0)
        self.assertEqual(created.json()["risk_grade"], "GS-1")
        self.assertEqual(created.json()["status"], "pending")

    def test_a_request_above_the_ceiling_is_refused(self, _score):
        body, _ = self.register()
        response = self.client.post(
            "/api/loans", json={"amount": 900_000, "tenor_months": 12}, headers=self.auth(body)
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("ceiling", response.json()["detail"])

    def test_only_one_application_may_be_open_at_a_time(self, _score):
        body, _ = self.register()
        headers = self.auth(body)
        payload = {"amount": 10_000, "tenor_months": 6}

        self.assertEqual(self.client.post("/api/loans", json=payload, headers=headers).status_code, 201)
        self.assertEqual(self.client.post("/api/loans", json=payload, headers=headers).status_code, 409)

    def test_a_low_score_cannot_apply_at_all(self, score):
        score.return_value = POOR_SCORE
        body, _ = self.register()
        headers = self.auth(body)

        verdict = self.client.get("/api/loans/eligibility", headers=headers).json()
        self.assertFalse(verdict["eligible"])

        response = self.client.post(
            "/api/loans", json={"amount": 5_000, "tenor_months": 6}, headers=headers
        )
        self.assertEqual(response.status_code, 422)

    def test_a_lender_decides_once_and_the_worker_sees_the_outcome(self, _score):
        worker, _ = self.register(role=ROLE_WORKER)
        lender, _ = self.register(role=ROLE_LENDER)
        worker_headers, lender_headers = self.auth(worker), self.auth(lender)

        created = self.client.post(
            "/api/loans", json={"amount": 15_000, "tenor_months": 12}, headers=worker_headers
        ).json()

        queue = self.client.get("/api/loans/queue", headers=lender_headers).json()
        self.assertEqual(len(queue), 1)
        # The lender sees who applied; the worker's own view does not repeat it.
        self.assertEqual(queue[0]["applicant_email"], worker["user"]["email"])
        self.assertEqual(queue[0]["credit_score"], 690.0)

        decision = self.client.patch(
            f"/api/loans/{created['id']}",
            json={"status": "approved", "lender_note": "Stable payouts."},
            headers=lender_headers,
        )
        self.assertEqual(decision.status_code, 200, decision.text)
        self.assertEqual(decision.json()["status"], "approved")
        self.assertIsNotNone(decision.json()["decided_at"])

        # Deciding twice is a conflict, not a silent overwrite.
        self.assertEqual(
            self.client.patch(
                f"/api/loans/{created['id']}", json={"status": "rejected"}, headers=lender_headers
            ).status_code,
            409,
        )

        mine = self.client.get("/api/loans", headers=worker_headers).json()
        self.assertEqual(mine[0]["status"], "approved")
        self.assertEqual(mine[0]["lender_note"], "Stable payouts.")

    def test_a_worker_cannot_decide_their_own_application(self, _score):
        body, _ = self.register()
        headers = self.auth(body)
        created = self.client.post(
            "/api/loans", json={"amount": 10_000, "tenor_months": 6}, headers=headers
        ).json()

        self.assertEqual(
            self.client.patch(
                f"/api/loans/{created['id']}", json={"status": "approved"}, headers=headers
            ).status_code,
            403,
        )

    def test_a_scoring_outage_is_a_503_rather_than_an_invented_score(self, score):
        import scoring_client

        score.side_effect = scoring_client.ScoringUnavailable("scorer down")
        body, _ = self.register()
        response = self.client.get("/api/loans/eligibility", headers=self.auth(body))
        self.assertEqual(response.status_code, 503)


class TaxAndBotTests(ApiTestCase):
    def test_tax_summary_annualises_the_logged_income(self):
        body, _ = self.register()
        headers = self.auth(body)
        self.log(headers, 20_000.0, "platform_payout")

        summary = self.client.get("/api/tax/summary", headers=headers).json()
        self.assertEqual(summary["gross_income_observed"], 20_000.0)
        self.assertGreater(summary["annualised_gross_income"], 20_000.0)
        self.assertIn("New regime", summary["regime"])
        self.assertTrue(summary["notes"])

    def test_tax_summary_of_an_empty_ledger_is_zero_rather_than_an_error(self):
        body, _ = self.register()
        summary = self.client.get("/api/tax/summary", headers=self.auth(body)).json()
        self.assertEqual(summary["gross_income_observed"], 0.0)
        self.assertEqual(summary["total_tax"], 0.0)

    def test_the_policy_bot_answers_on_topic_and_declines_off_topic(self):
        body, _ = self.register()
        headers = self.auth(body)

        on_topic = self.client.post(
            "/api/policy-bot/ask", json={"question": "can I get an emergency loan"}, headers=headers
        ).json()
        self.assertTrue(on_topic["confident"])
        self.assertIn("emergency loan", on_topic["answer"])
        self.assertEqual(on_topic["sources"][0]["topic"], "Emergency loan eligibility")

        off_topic = self.client.post(
            "/api/policy-bot/ask",
            json={"question": "what is the weather in Chennai"},
            headers=headers,
        ).json()
        self.assertFalse(off_topic["confident"])
        self.assertTrue(off_topic["suggestions"])

    def test_the_policy_bot_answers_in_the_requested_language(self):
        body, _ = self.register()
        headers = self.auth(body)

        english = self.client.post(
            "/api/policy-bot/ask", json={"question": "emergency loan"}, headers=headers
        ).json()["answer"]
        tamil = self.client.post(
            "/api/policy-bot/ask",
            json={"question": "emergency loan", "language": "ta"},
            headers=headers,
        ).json()["answer"]
        self.assertNotEqual(english, tamil)

    def test_the_policy_bot_is_behind_authentication(self):
        self.assertEqual(
            self.client.post("/api/policy-bot/ask", json={"question": "hello"}).status_code, 401
        )


if __name__ == "__main__":
    unittest.main()
