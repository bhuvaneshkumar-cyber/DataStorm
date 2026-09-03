"""Webhook ingestion boundary for bank / gig-platform transaction events.

Ports the Node/Express `src/listeners/webhookListener.js` + `src/utils/index.js`
onto FastAPI. Everything here is pure: parsing, validation, HMAC verification and
deterministic id derivation. Persistence lives in db_service.process_webhook_event.

Authentication mirrors the Node contract exactly:
  * `X-Webhook-Signature` — hex HMAC-SHA256 over the *raw* request body, or
  * `X-Webhook-Secret`    — the shared secret compared verbatim.
Both comparisons are timing-safe. A request with neither header is rejected, and
so is any request at all when WEBHOOK_SECRET is unset (fail closed).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

# The external webhook vocabulary ("payout") differs from the internal ledger
# vocabulary ("platform_payout"); this is the single translation point.
WEBHOOK_TYPE_TO_LEDGER = {"debit": "debit", "payout": "platform_payout"}
REQUIRED_FIELDS = ("userId", "type", "amount", "source", "timestamp")

# Stable namespace so a replayed payload always derives the same transaction id.
TRANSACTION_NAMESPACE = uuid.UUID("6f2b5a1c-9f42-4f2a-9a4e-3c0d6f1b7e55")


class WebhookAuthError(Exception):
    """Raised when a webhook cannot be authenticated."""


class WebhookValidationError(Exception):
    """Raised when a webhook payload is structurally invalid."""


@dataclass(frozen=True)
class WebhookEvent:
    """A validated transaction webhook, normalised to ledger vocabulary."""

    transaction_id: uuid.UUID
    user_id: uuid.UUID
    amount: float
    transaction_type: str
    source: str
    timestamp: datetime


def webhook_secret() -> Optional[str]:
    """Shared secret for inbound webhooks. None means webhooks are disabled."""
    return os.getenv("WEBHOOK_SECRET") or None


def verify_webhook_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """Timing-safe hex HMAC-SHA256 check over the exact bytes received."""
    if not raw_body or not signature or not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, str(signature))


def authenticate(raw_body: bytes, signature: Optional[str], shared_secret: Optional[str]) -> None:
    """Raises WebhookAuthError unless one of the two auth headers checks out."""
    secret = webhook_secret()
    if not secret:
        raise WebhookAuthError("Webhook authentication is not configured.")
    if signature:
        if not verify_webhook_signature(raw_body, signature, secret):
            raise WebhookAuthError("Invalid or missing webhook signature.")
        return
    if not shared_secret:
        raise WebhookAuthError("Missing x-webhook-secret header.")
    if not hmac.compare_digest(secret, str(shared_secret)):
        raise WebhookAuthError("Invalid webhook secret.")


def _coerce_uuid(value: Any, *, seed: str) -> uuid.UUID:
    """Use the caller's id when it is a UUID, else derive one deterministically."""
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return uuid.uuid5(TRANSACTION_NAMESPACE, seed)


def parse_event(payload: Any) -> WebhookEvent:
    """Validate a raw webhook body and normalise it into a WebhookEvent.

    Mirrors handleTransactionPayload's validation order so the same bad payloads
    produce the same rejections they did under Express.
    """
    if not isinstance(payload, dict):
        raise WebhookValidationError("Request body must be a JSON object.")

    missing = [f for f in REQUIRED_FIELDS if payload.get(f) in (None, "")]
    if missing:
        raise WebhookValidationError(f"Missing required fields: {', '.join(missing)}")

    event_type = payload["type"]
    if event_type not in WEBHOOK_TYPE_TO_LEDGER:
        valid = ", ".join(WEBHOOK_TYPE_TO_LEDGER)
        raise WebhookValidationError(f'Invalid type "{event_type}". Must be one of: {valid}')

    try:
        amount = float(payload["amount"])
    except (TypeError, ValueError):
        raise WebhookValidationError(
            f'Invalid amount "{payload["amount"]}". Must be a non-negative number.'
        ) from None
    if amount < 0 or amount != amount or amount in (float("inf"), float("-inf")):
        raise WebhookValidationError(
            f'Invalid amount "{payload["amount"]}". Must be a non-negative number.'
        )

    raw_timestamp = str(payload["timestamp"])
    try:
        timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
    except ValueError:
        raise WebhookValidationError(
            f'Invalid timestamp "{raw_timestamp}". Must be a valid ISO 8601 date-time.'
        ) from None
    # The ledger column is timestamp-without-timezone and every other row is
    # written with datetime.utcnow(), so an aware timestamp must be converted to
    # UTC - not to local time, which would offset webhook rows against the rest
    # of the ledger and scramble the chronological replay.
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)

    try:
        user_id = uuid.UUID(str(payload["userId"]))
    except (ValueError, AttributeError, TypeError):
        raise WebhookValidationError(f'Invalid userId "{payload["userId"]}". Must be a UUID.') from None

    seed = f'{payload["userId"]}|{payload["source"]}|{raw_timestamp}|{amount}'
    transaction_id = _coerce_uuid(payload.get("transactionId"), seed=seed)

    return WebhookEvent(
        transaction_id=transaction_id,
        user_id=user_id,
        amount=amount,
        transaction_type=WEBHOOK_TYPE_TO_LEDGER[event_type],
        source=str(payload["source"]),
        timestamp=timestamp,
    )
