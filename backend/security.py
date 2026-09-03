"""Password hashing and JWT issue/verify.

Kept apart from the routers so the two things worth getting exactly right —
how a password is stored and how a token is trusted — live in one readable
file rather than being spread across request handlers.

Hashing is PBKDF2-HMAC-SHA256 from the standard library rather than bcrypt:
it is FIPS-approved, needs no build toolchain on Windows, and at this
iteration count is the same order of work for an attacker.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 600_000  # OWASP 2023 floor for PBKDF2-HMAC-SHA256
_SALT_BYTES = 16

MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    """Returns `pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>`.

    The parameters travel with the hash so raising _ITERATIONS later does not
    lock out every account created before the change.
    """
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGORITHM}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: Optional[str]) -> bool:
    """Constant-time check. A malformed or absent hash is a failed login, not a crash."""
    if not encoded:
        return False
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$")
        if algorithm != _ALGORITHM:
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
    except (ValueError, TypeError):
        logger.warning("Stored password hash is malformed; treating as a failed login.")
        return False
    return hmac.compare_digest(expected, actual)


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_HOURS = int(os.getenv("JWT_TTL_HOURS", "12"))


def _load_secret() -> str:
    """JWT_SECRET from the environment, or an ephemeral one for local dev.

    Falling back to a *random* secret rather than a hardcoded one matters: a
    checked-in default would let anyone mint a valid token against a deployment
    that forgot to set the variable. The cost is that tokens do not survive a
    restart, which is loud enough to get noticed in development and is why the
    warning is an error-level log.
    """
    secret = os.getenv("JWT_SECRET")
    if secret:
        return secret
    logger.error(
        "JWT_SECRET is not set. Using a random per-process secret: every restart "
        "invalidates all sessions. Set JWT_SECRET before deploying."
    )
    return secrets.token_urlsafe(48)


JWT_SECRET = _load_secret()


class TokenError(Exception):
    """The token was missing, malformed, expired, or signed with another key."""


def create_access_token(user_id: uuid.UUID | str, role: str) -> str:
    """Signs a short-lived access token carrying the subject and its role."""
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "role": role,
            "iat": now,
            "exp": now + timedelta(hours=ACCESS_TOKEN_TTL_HOURS),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Verifies signature and expiry, returning the claims.

    Every PyJWT failure mode collapses to one TokenError so callers cannot
    accidentally handle "expired" and forget "bad signature".
    """
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Your session has expired. Please sign in again.") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("Invalid authentication token.") from exc


def demo() -> None:
    """Self-check: the parts where a silent bug becomes a security hole."""
    encoded = hash_password("correct horse battery")
    assert verify_password("correct horse battery", encoded)
    assert not verify_password("wrong password", encoded)
    assert not verify_password("correct horse battery", None)
    assert not verify_password("correct horse battery", "garbage")
    # Same password, different salt -> different stored hash.
    assert encoded != hash_password("correct horse battery")

    uid = uuid.uuid4()
    claims = decode_access_token(create_access_token(uid, "lender"))
    assert claims["sub"] == str(uid) and claims["role"] == "lender"

    forged = jwt.encode({"sub": "attacker", "role": "lender"}, "not-the-secret", algorithm="HS256")
    try:
        decode_access_token(forged)
        raise AssertionError("a token signed with the wrong key must not verify")
    except TokenError:
        pass
    print("security.py self-check passed")


if __name__ == "__main__":
    demo()
