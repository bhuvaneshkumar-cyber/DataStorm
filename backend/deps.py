"""Shared FastAPI dependencies: who is calling, and may they.

Every protected route resolves its caller through `current_user`, so there is
exactly one place that decides what a bearer token means. Role checks build on
that rather than re-reading the token, which is why a lender can never reach a
worker route by crafting a request that skips a check.
"""

from __future__ import annotations

import uuid
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

import security
from database import get_db
from models import ROLE_LENDER, ROLE_WORKER, User

# auto_error=False so a missing header reaches our handler and produces the same
# shaped 401 as a bad one, instead of FastAPI's terser default.
_bearer = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Sign in to continue.",
    headers={"WWW-Authenticate": "Bearer"},
)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Resolves the bearer token to a live user row.

    The row is re-read rather than trusted from the token: a deleted account
    must stop working immediately, not when its token happens to expire.
    """
    if credentials is None or not credentials.credentials:
        raise _UNAUTHENTICATED

    try:
        claims = security.decode_access_token(credentials.credentials)
        user_id = uuid.UUID(claims["sub"])
    except (security.TokenError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc) if isinstance(exc, security.TokenError) else "Invalid token subject.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise _UNAUTHENTICATED
    return user


def require_role(role: str) -> Callable[[User], User]:
    """Dependency factory gating a router on one role.

    403 rather than 404: the caller is authenticated and the route exists, they
    are simply on the wrong side of the product.
    """

    def _guard(user: User = Depends(current_user)) -> User:
        if user.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This area is for {role} accounts.",
            )
        return user

    return _guard


current_worker = require_role(ROLE_WORKER)
current_lender = require_role(ROLE_LENDER)
