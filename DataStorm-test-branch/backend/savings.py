from dataclasses import dataclass
from statistics import mean
from typing import Iterable


@dataclass(frozen=True)
class SweepDecision:
    amount: float
    eligible: bool
    reason: str


@dataclass(frozen=True)
class Transaction:
    amount: float
    kind: str


class SavingsEngine:
    """Small orchestration boundary for bank events and savings sweeps."""

    def __init__(self, income_history: Iterable[float], threshold: float = 100, mandate_limit: float = 1000):
        self.income_history = list(income_history)
        self.pending_roundups = 0.0
        self.pending_surplus = 0.0
        self.threshold = threshold
        self.mandate_limit = mandate_limit

    def process(self, transaction: Transaction, surplus_percentage: float = 0.10) -> SweepDecision:
        if transaction.kind == "debit":
            self.pending_roundups += round_up(transaction.amount)
        elif transaction.kind == "platform_payout":
            self.pending_surplus += income_surplus(transaction.amount, self.income_history, surplus_percentage)
            self.income_history.append(transaction.amount)
        else:
            raise ValueError("kind must be debit or platform_payout")
        return sweep_decision(self.pending_roundups, self.pending_surplus, self.threshold, self.mandate_limit)

    def authorize_sweep(self) -> SweepDecision:
        decision = sweep_decision(self.pending_roundups, self.pending_surplus, self.threshold, self.mandate_limit)
        if decision.eligible:
            self.pending_roundups = 0.0
            self.pending_surplus = 0.0
        return decision


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
