"""Pure savings calculations for the GigSave engine.

Every function here is deterministic and side-effect free: no database, no I/O,
no shared state. The accumulation of pending contributions lives in
``db_service.get_pending_contributions``, which replays the ledger - there is no
in-memory counter to fall out of sync with the rows.
"""

from dataclasses import dataclass
from statistics import mean
from typing import Iterable

DEFAULT_THRESHOLD = 100.0
DEFAULT_MANDATE_LIMIT = 1000.0
DEFAULT_ROUND_UP_MULTIPLE = 50
DEFAULT_SURPLUS_PERCENTAGE = 0.10
DEFAULT_WINDOW = 30


@dataclass(frozen=True)
class SweepDecision:
    amount: float
    eligible: bool
    reason: str


def round_up(amount: float, multiple: int = 50) -> float:
    """Contribution that lifts ``amount`` to the next multiple.

    The outer modulo matters: an amount already on a boundary contributes 0,
    not a whole extra increment.
    """
    if amount < 0 or multiple <= 0:
        raise ValueError("amount must be non-negative and multiple must be positive")
    return float((multiple - amount % multiple) % multiple)


def moving_average(values: Iterable[float], window: int = 30) -> float:
    """Mean of the last ``window`` values; 0.0 for an empty history."""
    values = list(values)
    if window <= 0:
        raise ValueError("window must be positive")
    return mean(values[-window:]) if values else 0.0


def income_surplus(current: float, history: Iterable[float], percentage: float = 0.10) -> float:
    """Share of a payout that exceeds the worker's rolling average.

    Only the above-average portion is saved, on the principle that you do not
    miss what you were not used to having.
    """
    if current < 0 or not 0 <= percentage <= 1:
        raise ValueError("current must be non-negative and percentage must be between 0 and 1")
    surplus = max(0.0, current - moving_average(history, window))
    return round(surplus * percentage, 2)


def sweep_decision(roundups: float, surplus: float, threshold: float = 100, mandate_limit: float = 1000) -> SweepDecision:
    """Whether the accumulated total may be swept under the UPI AutoPay mandate."""
    amount = round(roundups + surplus, 2)
    if amount < threshold:
        return SweepDecision(amount, False, "minimum threshold not reached")
    if amount > mandate_limit:
        return SweepDecision(amount, False, "mandate limit exceeded")
    return SweepDecision(amount, True, "UPI AutoPay sweep authorized")
