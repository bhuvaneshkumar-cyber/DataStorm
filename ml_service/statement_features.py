"""Derives gig-worker scoring features from a parsed bank or payout statement.

This is the IntelliCredit derived-metrics engine retargeted from MSME balance
sheets to individual gig income. IntelliCredit estimated Revenue/PAT/EBITDA when
no annual report existed; here the same idea produces the payout signals that
CreditScoreRequest needs when the applicant has no filed accounts at all - which
is every gig worker.

What carries over unchanged is the hard part: reading Indian money formats
(lakh/crore words, 1,23,456 grouping, parenthesised negatives, Rs/INR prefixes)
and identifying columns from the wildly inconsistent headers Indian banks export.

Features that a statement genuinely cannot evidence - age, platform rating,
hours worked - are reported as unresolved rather than invented. The caller
supplies those, and the response says which came from where.
"""

from __future__ import annotations

import logging
import math
import re
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

import config

logger = logging.getLogger(__name__)


class StatementParseError(Exception):
    """The statement parsed, but carries no usable payout data."""


# --------------------------------------------------------------------------- #
# Indian money parsing
# --------------------------------------------------------------------------- #

# Multipliers for amounts written in words rather than digits.
_SCALE_WORDS = {
    "thousand": 1_000.0,
    "k": 1_000.0,
    "lakh": 100_000.0,
    "lakhs": 100_000.0,
    "lac": 100_000.0,
    "lacs": 100_000.0,
    "million": 1_000_000.0,
    "mn": 1_000_000.0,
    "crore": 10_000_000.0,
    "crores": 10_000_000.0,
    "cr": 10_000_000.0,
    "billion": 1_000_000_000.0,
}

# Currency markers and trailing Dr/Cr suffixes that are not part of the number.
_CURRENCY_NOISE = re.compile(r"(?:₹|rs\.?|inr|\bdr\b|\bcr\b(?!\s*ore))", re.IGNORECASE)

# A number, optionally followed by a scale word. Handles Indian grouping.
_AMOUNT_RE = re.compile(
    r"(?P<open>\()?\s*(?P<digits>\d[\d,]*(?:\.\d+)?)\s*\)?\s*(?P<scale>[a-z]+)?",
    re.IGNORECASE,
)

# Cells that mean "no value" rather than zero.
_NULL_TOKENS = frozenset({"", "-", "--", "—", "–", "n/a", "na", "nil", "none", "nan"})


def parse_indian_amount(value: Any) -> Optional[float]:
    """Parses one statement cell into a float, or None if it holds no amount.

    Handles the formats an Indian statement actually contains:
      "1,23,456.78" -> 123456.78   (lakh-crore digit grouping)
      "(1,234.56)"  -> -1234.56    (accounting negative)
      "Rs. 2.5 Lakh" -> 250000.0   (scale word)
      "5,000.00 Cr"  -> 5000.0     ("Cr" here is Credit, not Crore)
      "-", "N/A"     -> None       (absent, which is not the same as zero)

    The Cr ambiguity is why the currency-noise strip runs before scale matching:
    a bare trailing "Cr" on a statement line is a credit marker, and only the
    spelled-out "crore" is treated as a multiplier.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return None if isinstance(value, float) and math.isnan(value) else float(value)

    text = str(value).strip()
    if text.lower() in _NULL_TOKENS:
        return None

    negative = text.startswith("(") and text.endswith(")")
    cleaned = _CURRENCY_NOISE.sub(" ", text).strip()

    match = _AMOUNT_RE.search(cleaned)
    if not match:
        return None

    try:
        amount = float(match.group("digits").replace(",", ""))
    except ValueError:
        return None

    scale = (match.group("scale") or "").lower()
    if scale in _SCALE_WORDS:
        amount *= _SCALE_WORDS[scale]

    if negative or match.group("open") or text.lstrip().startswith("-"):
        amount = -amount
    return amount


# --------------------------------------------------------------------------- #
# Column identification
# --------------------------------------------------------------------------- #

# Ordered most-specific first, so "credit amount" wins over a bare "amount".
_COLUMN_KEYWORDS: Dict[str, Sequence[str]] = {
    "credit": ("credit amount", "deposit amount", "cr amount", "credit", "deposit", "inflow",
               "received", "payout", "earnings", "income"),
    "debit": ("debit amount", "withdrawal amount", "dr amount", "debit", "withdrawal",
              "outflow", "paid", "spent"),
    "balance": ("closing balance", "running balance", "available balance", "balance"),
    "date": ("transaction date", "value date", "txn date", "posting date", "date"),
    "narration": ("narration", "description", "particulars", "remarks", "details",
                  "transaction remarks", "merchant"),
}


def _find_column(columns: Sequence[Any], keywords: Sequence[str]) -> Optional[str]:
    """First column whose header contains one of the keywords, most specific first."""
    normalized = [(str(c), str(c).lower().strip()) for c in columns]
    for keyword in keywords:
        for original, lowered in normalized:
            if keyword in lowered:
                return original
    return None


def identify_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    """Maps the roles this module needs onto whatever the bank named its columns."""
    return {role: _find_column(df.columns, kws) for role, kws in _COLUMN_KEYWORDS.items()}


# --------------------------------------------------------------------------- #
# Platform inference
# --------------------------------------------------------------------------- #

# Narration keywords for the platforms CreditScoreRequest recognises.
_PLATFORM_KEYWORDS: Dict[str, Sequence[str]] = {
    "Ride-Hailing": ("uber", "ola", "rapido", "blusmart", "meru", "namma yatri"),
    "Food Delivery": ("swiggy", "zomato", "zepto", "blinkit", "dunzo", "bigbasket",
                      "instamart", "eternal"),
    "Freelance": ("upwork", "fiverr", "freelancer", "toptal", "contra", "payoneer"),
}


def infer_primary_platform(narrations: Sequence[str]) -> Optional[str]:
    """Picks the platform crediting this account most often.

    Returns None rather than guessing "Other" when nothing matches, so the caller
    can tell "no evidence" apart from "evidence says Other".
    """
    counts: Dict[str, int] = {}
    for text in narrations:
        lowered = str(text).lower()
        for platform, keywords in _PLATFORM_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                counts[platform] = counts.get(platform, 0) + 1

    return max(counts, key=counts.get) if counts else None


# --------------------------------------------------------------------------- #
# Result
# --------------------------------------------------------------------------- #


@dataclass
class StatementInsights:
    """What a statement could and could not establish."""

    derived: Dict[str, Any] = field(default_factory=dict)
    unresolved: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "derived_features": self.derived,
            "unresolved_features": self.unresolved,
            "evidence": self.evidence,
            "warnings": self.warnings,
        }


# Features no bank statement can evidence; the caller must supply them.
_NON_DERIVABLE = ("age", "platform_customer_rating", "active_platform_hours_per_week")

_DAYS_PER_WEEK = 7


def derive_features(df: pd.DataFrame) -> StatementInsights:
    """Turns a statement table into as much of CreditScoreRequest as it supports.

    Derives average_weekly_payout, payout_volatility_index, completed_gigs_per_week,
    resilience_stash_balance and primary_gig_platform from credit rows. Raises
    StatementParseError only when there is no credit column or no parseable
    credit at all - anything softer is reported as a warning.
    """
    insights = StatementInsights()

    if df is None or df.empty:
        raise StatementParseError("The statement contains no rows.")

    columns = identify_columns(df)
    insights.evidence["columns_detected"] = columns

    if not columns["credit"]:
        raise StatementParseError(
            "No credit/deposit/payout column found. Detected headers: "
            f"{[str(c) for c in df.columns][:15]}"
        )

    credits = df[columns["credit"]].map(parse_indian_amount)
    inflow_mask = credits.notna() & (credits > 0)
    payouts = credits[inflow_mask]

    if payouts.empty:
        raise StatementParseError(
            f"Column {columns['credit']!r} contains no positive amounts."
        )

    insights.evidence["payout_rows"] = int(payouts.size)
    insights.evidence["total_credited"] = round(float(payouts.sum()), 2)

    _derive_income(df, columns, payouts, inflow_mask, insights)
    _derive_stash(df, columns, credits, insights)
    _derive_platform(df, columns, inflow_mask, insights)

    insights.unresolved.extend(_NON_DERIVABLE)
    return insights


def _derive_income(
    df: pd.DataFrame,
    columns: Dict[str, Optional[str]],
    payouts: pd.Series,
    inflow_mask: pd.Series,
    insights: StatementInsights,
) -> None:
    """Weekly payout level, volatility, and gig count.

    Everything here needs dates: a weekly average without a time span is just a
    per-row average wearing a misleading name. With no usable date column we
    report the shortfall instead of producing one.
    """
    date_column = columns["date"]
    dates = None

    if date_column:
        # dayfirst: Indian statements are DD/MM/YYYY, and 03/09 must not become March.
        dates = pd.to_datetime(df.loc[inflow_mask, date_column], errors="coerce", dayfirst=True)
        dates = dates.dropna()

    if dates is None or dates.empty:
        insights.warnings.append(
            "No parseable transaction dates; weekly figures could not be derived."
        )
        insights.unresolved.extend(
            ["average_weekly_payout", "payout_volatility_index", "completed_gigs_per_week"]
        )
        return

    span_days = (dates.max() - dates.min()).days + 1
    insights.evidence["statement_days"] = int(span_days)
    insights.evidence["period_start"] = dates.min().date().isoformat()
    insights.evidence["period_end"] = dates.max().date().isoformat()

    if span_days < config.MIN_STATEMENT_DAYS:
        insights.warnings.append(
            f"Statement covers only {span_days} day(s); at least "
            f"{config.MIN_STATEMENT_DAYS} are needed for a stable weekly average."
        )

    weeks = max(span_days / _DAYS_PER_WEEK, 1.0)

    # Align the payout amounts to the rows whose dates actually parsed.
    dated_payouts = payouts.loc[dates.index]

    insights.derived["average_weekly_payout"] = round(float(dated_payouts.sum()) / weeks, 2)
    insights.derived["completed_gigs_per_week"] = max(1, round(dated_payouts.size / weeks))

    # Volatility from real calendar weeks, not from per-transaction spread: the
    # score cares whether a worker's *income* is steady, not whether individual
    # fares differ.
    weekly_totals = dated_payouts.groupby(dates.dt.to_period("W")).sum()
    insights.derived["payout_volatility_index"] = _volatility(weekly_totals.tolist())
    insights.evidence["weeks_observed"] = int(weekly_totals.size)

    if weekly_totals.size < 2:
        insights.warnings.append(
            "Only one week of payouts observed; volatility is an assumption, not a measurement."
        )


def _volatility(weekly_totals: Sequence[float]) -> float:
    """Coefficient of variation of weekly income, clipped to the schema's 0-1 range.

    A single observation has no measurable spread. Reporting 0.0 there would
    claim perfectly stable income and hand the applicant the maximum stability
    bonus on no evidence, so an unknown falls back to the mid-point instead.
    """
    if len(weekly_totals) < 2:
        return 0.5

    mean = statistics.fmean(weekly_totals)
    if mean <= 0:
        return 1.0

    return round(min(statistics.stdev(weekly_totals) / mean, 1.0), 3)


def _derive_stash(
    df: pd.DataFrame,
    columns: Dict[str, Optional[str]],
    credits: pd.Series,
    insights: StatementInsights,
) -> None:
    """Savings buffer: the closing balance if the statement carries one."""
    balance_column = columns["balance"]

    if balance_column:
        balances = df[balance_column].map(parse_indian_amount).dropna()
        if not balances.empty:
            insights.derived["resilience_stash_balance"] = round(max(float(balances.iloc[-1]), 0.0), 2)
            insights.evidence["stash_source"] = f"closing balance ({balance_column})"
            insights.evidence["opening_balance"] = _opening_balance(df, columns, balances)
            return

    # No balance column: net cash retained over the period is the closest honest
    # proxy. It is a floor, not the true buffer, so it is flagged as an estimate.
    debit_column = columns["debit"]
    outflow = 0.0
    if debit_column:
        debits = df[debit_column].map(parse_indian_amount).dropna()
        outflow = float(debits[debits > 0].sum())

    net = max(float(credits[credits > 0].sum()) - outflow, 0.0)
    insights.derived["resilience_stash_balance"] = round(net, 2)
    insights.evidence["stash_source"] = "estimated from net inflow minus outflow"
    insights.warnings.append(
        "No balance column found; resilience_stash_balance is a net-cashflow estimate."
    )


def _opening_balance(
    df: pd.DataFrame, columns: Dict[str, Optional[str]], balances: pd.Series
) -> float:
    """Balance before the first transaction.

    The first row's balance is the balance *after* that transaction, so the
    opening is that figure with the first row's movement backed out. Needed by
    the liquidity metrics: starting a running balance at zero understates the
    cash cushion of anyone who began the period with money.
    """
    first_index = balances.index[0]
    movement = 0.0
    for role, sign in (("credit", 1.0), ("debit", -1.0)):
        column = columns[role]
        if not column:
            continue
        amount = parse_indian_amount(df[column].loc[first_index])
        if amount and amount > 0:
            movement += sign * float(amount)

    return round(max(float(balances.iloc[0]) - movement, 0.0), 2)


def _derive_platform(
    df: pd.DataFrame,
    columns: Dict[str, Optional[str]],
    inflow_mask: pd.Series,
    insights: StatementInsights,
) -> None:
    """Primary gig platform, inferred from credit narrations."""
    narration_column = columns["narration"]
    if not narration_column:
        insights.unresolved.append("primary_gig_platform")
        insights.warnings.append(
            "No narration/description column; the gig platform could not be inferred."
        )
        return

    narrations = df.loc[inflow_mask, narration_column].dropna().astype(str).tolist()
    platform = infer_primary_platform(narrations)

    if platform is None:
        insights.unresolved.append("primary_gig_platform")
        insights.warnings.append(
            "No known gig platform matched the credit narrations."
        )
        return

    insights.derived["primary_gig_platform"] = platform
    insights.evidence["platform_source"] = f"narration keywords in {narration_column!r}"


# --------------------------------------------------------------------------- #
# Ledger extraction
# --------------------------------------------------------------------------- #

# Narration keywords that categorise a debit. Enough to make the recurring-expense
# detection work on a real statement; unmatched rows fall back to "other".
_EXPENSE_KEYWORDS: Dict[str, Sequence[str]] = {
    "rent": ("rent", "landlord", "lease"),
    "fuel": ("petrol", "diesel", "fuel", "hpcl", "iocl", "bpcl", "indian oil"),
    "emi": ("emi", "loan", "instalment", "installment"),
    "insurance": ("insurance", "premium", "policy", "lic"),
    "utilities": ("electricity", "recharge", "broadband", "gas bill", "water", "mobile"),
    "food": ("grocery", "kirana", "supermarket", "bigbasket", "dmart"),
    "vehicle": ("service", "repair", "garage", "tyre", "spare"),
    "transfer": ("neft", "imps", "upi-", "atm", "withdrawal"),
}


def categorise_expense(narration: str) -> str:
    """Buckets a debit narration into a spend category.

    Recurring-expense detection groups by category, so an uncategorised ledger
    would report every applicant as having no fixed obligations at all.
    """
    lowered = str(narration).lower()
    for category, keywords in _EXPENSE_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    return "other"


def to_transaction_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Flattens a statement table into standardized ledger rows.

    Output matches the shape credit_metrics expects:
        {date, type: "credit"|"debit", amount, category, source, description}

    Rows without a parseable date or amount are skipped rather than guessed at -
    a transaction placed on the wrong day corrupts every monthly metric
    downstream. Raises StatementParseError only if nothing at all survives.
    """
    if df is None or df.empty:
        raise StatementParseError("The statement contains no rows.")

    columns = identify_columns(df)
    if not columns["date"]:
        raise StatementParseError(
            "No date column found; a transaction ledger cannot be built without dates."
        )
    if not (columns["credit"] or columns["debit"]):
        raise StatementParseError("No credit or debit column found.")

    dates = pd.to_datetime(df[columns["date"]], errors="coerce", dayfirst=True)
    narration_column = columns["narration"]

    records: List[Dict[str, Any]] = []
    for position, timestamp in enumerate(dates):
        if pd.isna(timestamp):
            continue

        narration = ""
        if narration_column:
            cell = df[narration_column].iloc[position]
            narration = "" if pd.isna(cell) else str(cell).strip()

        for role, kind in (("credit", "credit"), ("debit", "debit")):
            column = columns[role]
            if not column:
                continue
            amount = parse_indian_amount(df[column].iloc[position])
            if amount is None or amount <= 0:
                continue

            records.append(
                {
                    "date": timestamp.date().isoformat(),
                    "type": kind,
                    "amount": round(float(amount), 2),
                    "category": (
                        infer_primary_platform([narration]) or "gig_earning"
                        if kind == "credit"
                        else categorise_expense(narration)
                    ),
                    "source": "bank",
                    "description": narration or None,
                }
            )

    if not records:
        raise StatementParseError(
            "No rows had both a parseable date and a parseable amount."
        )
    return records
