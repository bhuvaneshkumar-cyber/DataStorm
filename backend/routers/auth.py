"""Registration, sign-in, and the caller's own profile.

One credential store serves both audiences. `role` is chosen at registration and
is not editable afterwards through this API: a worker who could promote
themselves to lender would be able to read every applicant's file.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import security
from database import get_db
from deps import current_user
from models import User
from schemas import AuthResponse, LoginRequest, ProfileUpdate, RegisterRequest, UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["authentication"])

# One message for "no such account" and "wrong password" alike. Distinguishing
# them turns the login form into a way to enumerate who has an account here.
_BAD_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="That email and password do not match an account.",
    headers={"WWW-Authenticate": "Bearer"},
)


def _issue(user: User) -> AuthResponse:
    return AuthResponse(
        access_token=security.create_access_token(user.id, user.role),
        expires_in_hours=security.ACCESS_TOKEN_TTL_HOURS,
        user=UserProfile.model_validate(user),
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """Creates an account and signs it straight in."""
    email = payload.email.strip().lower()

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account already exists for that email address.",
        )

    user = User(
        name=payload.name.strip(),
        email=email,
        phone=payload.phone,
        password_hash=security.hash_password(payload.password),
        role=payload.role,
        language=payload.language,
        employment_type=payload.employment_type,
        date_of_birth=payload.date_of_birth,
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        # Two registrations racing on the same address: the unique index is the
        # real guard, the check above is only there to give a nicer message first.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account already exists for that email address.",
        ) from exc
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Registration failed for %s", email)
        raise

    return _issue(user)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """Signs in an existing account, optionally pinned to one role."""
    user = db.query(User).filter(User.email == payload.email.strip().lower()).first()

    if user is None or not security.verify_password(payload.password, user.password_hash):
        raise _BAD_CREDENTIALS

    if payload.expected_role and user.role != payload.expected_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This sign-in page is for {payload.expected_role} accounts.",
        )

    return _issue(user)


@router.get("/me", response_model=UserProfile)
def read_profile(user: User = Depends(current_user)) -> UserProfile:
    """The caller's own profile, as resolved from their token."""
    return UserProfile.model_validate(user)


@router.patch("/me", response_model=UserProfile)
def update_profile(
    payload: ProfileUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> UserProfile:
    """Updates the fields a person owns. Role and email are not among them."""
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return UserProfile.model_validate(user)

    for field, value in changes.items():
        setattr(user, field, value)

    try:
        db.commit()
        db.refresh(user)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Profile update failed for user %s", user.id)
        raise

    return UserProfile.model_validate(user)
