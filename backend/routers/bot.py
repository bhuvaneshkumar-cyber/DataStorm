"""The credit-policy bot, available on any signed-in route.

Behind authentication even though it holds no personal data: it is embedded on
protected pages, and leaving it open would make it a free question-answering
endpoint for anyone who found the URL.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

import policy_kb
from deps import current_user
from models import User
from schemas import BotAnswer, BotQuery

router = APIRouter(prefix="/api/policy-bot", tags=["policy bot"])


@router.get("/topics", response_model=list[str])
def topics(_: User = Depends(current_user)) -> list[str]:
    """Everything the bot can answer, so the UI can offer starting points."""
    return policy_kb.topics()


@router.post("/ask", response_model=BotAnswer)
def ask(payload: BotQuery, user: User = Depends(current_user)) -> dict:
    """Answers a policy question, or says plainly that it cannot.

    Falls back to the account's stored language when the request does not name
    one, so a Tamil-speaking worker does not get English answers under a Tamil UI.
    """
    return policy_kb.answer(payload.question, language=payload.language or user.language)
