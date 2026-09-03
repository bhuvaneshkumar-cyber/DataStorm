from dataclasses import dataclass
from statistics import mean
from typing import Iterable


@dataclass(frozen=True)
class SweepDecision:
    amount: float
    eligible: bool
    reason: str


def round_up(amount: float, multiple: int = 50) -> float:
    if amount < 0 or multiple <= 0:
        raise ValueError("amount must be non-negative and multiple must be positive")
    return float((multiple - amount % multiple) % multiple)


def moving_average(values: Iterable[float], window: int = 30) -> float:
    values = list(values)
    if window <= 0:
        raise ValueError("window must be positive")
    return mean(values[-window:]) if values else 0.0


def income_surplus(current: float, history: Iterable[float], percentage: float = 0.10) -> float:
    if current < 0 or not 0 <= percentage <= 1:
        raise ValueError("current must be non-negative and percentage must be between 0 and 1")
    surplus = max(0.0, current - moving_average(history, 30))
    return round(surplus * percentage, 2)


def sweep_decision(roundups: float, surplus: float, threshold: float = 100, mandate_limit: float = 1000) -> SweepDecision:
    amount = round(roundups + surplus, 2)
    if amount < threshold:
        return SweepDecision(amount, False, "minimum threshold not reached")
    if amount > mandate_limit:
        return SweepDecision(amount, False, "mandate limit exceeded")
    return SweepDecision(amount, True, "UPI AutoPay sweep authorized")
