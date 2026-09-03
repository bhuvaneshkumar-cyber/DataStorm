"""Corporate financial-statement analysis: Revenue, PAT, EBITDA, Net Worth, D/E, DSCR.

A different question from the rest of this service. The gig-worker path scores a
person from a payout ledger; this scores a *business* from its filed accounts,
which is what a lender needs when the applicant is a small enterprise rather
than an individual rider.

Three engines, in falling order of confidence, so an answer is always available
and always labelled with how it was reached:

1. **Reported** -- the regex analyzer finds a line item stated outright in the
   document ("Profit after tax  1,240.55").
2. **Derived** -- the metrics engine reconstructs a figure from ones that were
   found (EBITDA from PAT, tax, finance cost and depreciation).
3. **Estimated** -- no annual report exists at all, so the figure is inferred
   from raw GSTR-3B turnover and bank-statement flows.

Everything is offline: regexes and arithmetic, no model and no network. That is
deliberate, not a shortcut. A number a credit file is built on has to be
explicable line by line, and "the model said so" is not an explanation an
underwriter can file.

ponytail: label-and-line-scan parsing, not a statement taxonomy. Reach for a
proper XBRL reader the day these need to come from filed digital accounts
rather than from PDFs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from statement_features import parse_indian_amount

# --------------------------------------------------------------------------- #
# Reporting scale
# --------------------------------------------------------------------------- #

# Indian statements state their unit once, in a header like "(Rs. in lakhs)",
# and then print bare numbers. Missing that line means reading 1,240 as 1,240
# rupees when the accounts mean 1,240 lakh -- an error of five orders of
# magnitude, which is why this runs before anything else.
_SCALE_PATTERNS: Sequence[Tuple[str, float, str]] = (
    (r"\bin\s+crores?\b|\bcrores?\b\s*\)|\(\s*(?:rs\.?|inr|₹)?\s*in\s+crores?", 10_000_000.0, "crore"),
    (r"\bin\s+la(?:kh|c)s?\b|\bla(?:kh|c)s?\b\s*\)|\(\s*(?:rs\.?|inr|₹)?\s*in\s+la(?:kh|c)s?", 100_000.0, "lakh"),
    (r"\bin\s+millions?\b|\(\s*(?:rs\.?|inr|usd|₹|\$)?\s*in\s+millions?", 1_000_000.0, "million"),
    (r"\bin\s+thousands?\b|\(\s*(?:rs\.?|inr|₹)?\s*in\s+thousands?", 1_000.0, "thousand"),
)

# Only the first page or so declares the unit; scanning further picks up stray
# mentions inside notes that do not govern the statements.
_SCALE_SCAN_CHARS = 4_000


def detect_reporting_scale(text: str) -> Tuple[float, str]:
    """The multiplier the document's numbers are stated in, and its name.

    Defaults to 1.0 ("rupees") rather than guessing: a wrong multiplier is far
    worse than an un-multiplied figure, because the second is obviously wrong to
    a human reader and the first is not.
    """
    head = (text or "")[:_SCALE_SCAN_CHARS].lower()
    for pattern, multiplier, label in _SCALE_PATTERNS:
        if re.search(pattern, head):
            return multiplier, label
    return 1.0, "rupees"


# --------------------------------------------------------------------------- #
# Regex analyzer
# --------------------------------------------------------------------------- #

# Canonical line item -> the labels Indian accounts actually print for it.
# Ordered most specific first within each entry, because "total revenue" and
# "revenue" both match a line saying "total revenue" and the specific one must
# be tried first or the label recorded as evidence will be the wrong one.
_LINE_ITEM_LABELS: Dict[str, Sequence[str]] = {
    "revenue": (
        "revenue from operations",
        "total revenue",
        "total income",
        "net sales",
        "gross sales",
        "sales turnover",
        "turnover",
    ),
    "other_income": ("other income",),
    "profit_after_tax": (
        "profit after tax",
        "profit for the year",
        "profit for the period",
        "net profit after tax",
        "net profit",
        "pat",
    ),
    "profit_before_tax": ("profit before tax", "profit before taxation", "pbt"),
    "tax_expense": ("total tax expense", "tax expense", "provision for tax", "current tax"),
    "ebitda": ("ebitda", "earnings before interest tax depreciation"),
    "operating_profit": ("operating profit", "ebit", "earnings before interest and tax"),
    "depreciation": (
        "depreciation and amortisation",
        "depreciation and amortization",
        "depreciation & amortisation",
        "depreciation",
        "amortisation",
    ),
    "finance_cost": ("finance costs", "finance cost", "interest expense", "interest paid", "interest"),
    "share_capital": ("equity share capital", "share capital", "paid up capital"),
    "reserves": ("reserves and surplus", "reserves & surplus", "other equity", "retained earnings"),
    "net_worth": ("net worth", "total equity", "shareholders funds", "shareholders' funds"),
    "long_term_debt": (
        "long term borrowings",
        "long-term borrowings",
        "non current borrowings",
        "non-current borrowings",
        "term loan",
    ),
    "short_term_debt": (
        "short term borrowings",
        "short-term borrowings",
        "current borrowings",
        "working capital loan",
    ),
    "total_debt": ("total debt", "total borrowings", "total loan funds"),
    "current_portion_debt": (
        "current maturities of long term debt",
        "current maturities of long-term debt",
        "current maturities",
        "principal repayment",
    ),
}

# A number on a statement line: Indian digit grouping, optional decimals,
# optional accounting parentheses, optional leading minus.
_NUMBER_ON_LINE = re.compile(r"\(?-?\s*\d[\d,]*(?:\.\d+)?\s*\)?")

# Labels are matched with word boundaries so "pat" does not fire inside
# "patent" and "interest" does not fire inside "interested".
_WORD_CHARS = re.compile(r"[a-z]")

# Comparative-period headings: "2025-26", "2024 - 2025", "FY2025/26". Stripped
# before amounts are read, or the "-26" tail parses as an amount of minus 26.
_PERIOD_RANGE = re.compile(r"\b(?:19|20)\d{2}\s*[-–—/]\s*\d{2,4}\b")


@dataclass
class LineItem:
    """One figure found in the document, with the line it came from."""

    value: float
    label: str
    source_line: str


def _normalise(line: str) -> str:
    """Collapses punctuation and whitespace so labels match across layouts.

    Used for matching labels only, never for reading amounts: it drops the digit
    grouping commas, which would split "4,500.00" into two separate numbers.
    """
    return re.sub(r"[^a-z0-9%&'\s.-]", " ", line.lower()).strip()


def _numbers_on(line: str) -> List[float]:
    """Every amount on a line, left to right, with nothing that is a year.

    Four-digit values between 1990 and 2099 are dropped: Indian statements put
    the comparative years in the column headers and often repeat them mid-table,
    and a stray 2024 read as revenue is worse than one missing figure.
    """
    values: List[float] = []
    for token in _NUMBER_ON_LINE.findall(_PERIOD_RANGE.sub(" ", line)):
        amount = parse_indian_amount(token.strip())
        if amount is None:
            continue
        if amount == int(amount) and 1990 <= abs(amount) <= 2099 and "," not in token:
            continue
        values.append(amount)
    return values


def extract_line_items(text: str, scale: float = 1.0) -> Dict[str, LineItem]:
    """Scans the document for every line item it knows how to name.

    Takes the first amount on a matching line. In an Indian annual report the
    leftmost figure column is the current reporting period and the ones after it
    are comparatives, so the first number is the year being assessed.

    The first match for a canonical item wins: statements repeat their headline
    figures in the summary, the notes and the cash-flow statement, and the
    earliest occurrence is the one on the face of the accounts.
    """
    found: Dict[str, LineItem] = {}

    for raw_line in (text or "").splitlines():
        line = _normalise(raw_line)
        if not line or not _WORD_CHARS.search(line):
            continue

        # Amounts come from the raw line, labels from the normalised one.
        numbers = _numbers_on(raw_line)
        if not numbers:
            continue

        for canonical, labels in _LINE_ITEM_LABELS.items():
            if canonical in found:
                continue
            for label in labels:
                if re.search(rf"(?<![a-z]){re.escape(label)}(?![a-z])", line):
                    found[canonical] = LineItem(
                        value=numbers[0] * scale,
                        label=label,
                        source_line=raw_line.strip()[:160],
                    )
                    break

    return found


def _tables_to_text(tables: Sequence[dict]) -> str:
    """Flattens extracted PDF tables into scannable lines.

    A ruled table loses its row structure in plain text extraction, so the
    tables the PDF parser recovered are re-joined here and scanned alongside the
    prose. Without this, a bordered balance sheet contributes nothing.
    """
    lines: List[str] = []
    for table in tables or []:
        for row in table.get("data") or []:
            cells = [str(cell) for cell in row if cell not in (None, "")]
            if cells:
                lines.append("  ".join(cells))
    return "\n".join(lines)


def _frame_to_text(frame: Optional[pd.DataFrame]) -> str:
    """Same idea for a CSV or Excel export, which arrives as a DataFrame."""
    if frame is None or frame.empty:
        return ""
    lines = ["  ".join(str(column) for column in frame.columns)]
    for row in frame.itertuples(index=False):
        lines.append("  ".join("" if value is None else str(value) for value in row))
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Derived metrics engine
# --------------------------------------------------------------------------- #


@dataclass
class Metric:
    """One output figure: its value, where it came from, and how it was reached."""

    name: str
    value: Optional[float]
    source: str  # reported | derived | estimated | unavailable
    basis: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": round(self.value, 2) if self.value is not None else None,
            "source": self.source,
            "basis": self.basis,
        }


def _reported(items: Dict[str, LineItem], key: str) -> Optional[float]:
    entry = items.get(key)
    return entry.value if entry else None


def _sum_present(*values: Optional[float]) -> Optional[float]:
    """Sums the values that exist, or None if none of them do.

    None means "not found", which is not zero: treating an absent depreciation
    line as zero would silently understate EBITDA rather than admit it is
    unknown.
    """
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def derive_metrics(items: Dict[str, LineItem]) -> Dict[str, Metric]:
    """Builds the seven headline figures, reconstructing what was not stated."""
    metrics: Dict[str, Metric] = {}

    def record(name: str, key: str, fallback: Optional[float], basis: str) -> Optional[float]:
        stated = _reported(items, key)
        if stated is not None:
            metrics[name] = Metric(name, stated, "reported", f"Stated as '{items[key].label}'.")
            return stated
        if fallback is not None:
            metrics[name] = Metric(name, fallback, "derived", basis)
            return fallback
        metrics[name] = Metric(name, None, "unavailable", basis)
        return None

    revenue = record("revenue", "revenue", None, "No revenue or turnover line was found.")
    pat = record("profit_after_tax", "profit_after_tax", _pat_from_pbt(items),
                 "Derived as profit before tax less tax expense.")

    depreciation = _reported(items, "depreciation")
    finance_cost = _reported(items, "finance_cost")
    tax = _reported(items, "tax_expense")

    record(
        "ebitda",
        "ebitda",
        _ebitda_from(items, pat, tax, finance_cost, depreciation),
        "Derived by adding back tax, finance cost and depreciation to profit.",
    )

    net_worth = record(
        "net_worth",
        "net_worth",
        _sum_present(_reported(items, "share_capital"), _reported(items, "reserves")),
        "Derived as share capital plus reserves and surplus.",
    )

    total_debt = record(
        "total_debt",
        "total_debt",
        _sum_present(_reported(items, "long_term_debt"), _reported(items, "short_term_debt")),
        "Derived as long-term plus short-term borrowings.",
    )

    metrics["depreciation"] = Metric(
        "depreciation",
        depreciation,
        "reported" if depreciation is not None else "unavailable",
        "Stated depreciation and amortisation." if depreciation is not None
        else "No depreciation line was found.",
    )
    metrics["finance_cost"] = Metric(
        "finance_cost",
        finance_cost,
        "reported" if finance_cost is not None else "unavailable",
        "Stated finance cost." if finance_cost is not None else "No finance cost line was found.",
    )

    del revenue, net_worth, total_debt  # recorded above; the locals were only for clarity
    return metrics


def _pat_from_pbt(items: Dict[str, LineItem]) -> Optional[float]:
    pbt, tax = _reported(items, "profit_before_tax"), _reported(items, "tax_expense")
    return None if pbt is None else pbt - (tax or 0.0)


def _ebitda_from(
    items: Dict[str, LineItem],
    pat: Optional[float],
    tax: Optional[float],
    finance_cost: Optional[float],
    depreciation: Optional[float],
) -> Optional[float]:
    """EBITDA from whichever rung of the income statement is available.

    Operating profit plus depreciation is preferred over building up from PAT:
    it needs two figures instead of four, so it is right more often.
    """
    operating_profit = _reported(items, "operating_profit")
    if operating_profit is not None and depreciation is not None:
        return operating_profit + depreciation

    base = pat if pat is not None else _reported(items, "profit_before_tax")
    if base is None:
        return None

    add_backs = [finance_cost, depreciation]
    if pat is not None:
        add_backs.append(tax)
    if not any(value is not None for value in add_backs):
        return None
    return base + sum(value for value in add_backs if value is not None)


def compute_ratios(metrics: Dict[str, Metric]) -> Dict[str, Metric]:
    """Debt-to-equity and debt service coverage, with their inputs stated.

    Both are returned as unavailable rather than as zero when an input is
    missing. A DSCR of 0.0 reads as "cannot service its debt"; a DSCR of None
    reads as "we do not know", and those must not be confused.
    """
    ratios: Dict[str, Metric] = {}

    debt = metrics["total_debt"].value
    equity = metrics["net_worth"].value
    if debt is not None and equity is not None and equity > 0:
        ratios["debt_to_equity"] = Metric(
            "debt_to_equity",
            debt / equity,
            "derived",
            "Total debt divided by net worth.",
        )
    elif equity is not None and equity <= 0:
        ratios["debt_to_equity"] = Metric(
            "debt_to_equity",
            None,
            "unavailable",
            "Net worth is zero or negative, so the ratio is not meaningful.",
        )
    else:
        ratios["debt_to_equity"] = Metric(
            "debt_to_equity", None, "unavailable", "Total debt or net worth is unknown."
        )

    ebitda = metrics["ebitda"].value
    interest = metrics["finance_cost"].value
    principal = metrics.get("current_portion_debt")
    principal_value = principal.value if principal else None

    if ebitda is not None and interest:
        service = interest + (principal_value or 0.0)
        ratios["dscr"] = Metric(
            "dscr",
            ebitda / service if service else None,
            "derived",
            "EBITDA over interest plus current maturities of long-term debt."
            if principal_value
            else (
                "EBITDA over interest only; no current maturities of long-term debt were "
                "found, so this overstates true debt service coverage."
            ),
        )
    else:
        ratios["dscr"] = Metric(
            "dscr", None, "unavailable", "EBITDA or finance cost is unknown."
        )

    revenue = metrics["revenue"].value
    pat = metrics["profit_after_tax"].value
    if revenue and pat is not None:
        ratios["pat_margin_pct"] = Metric(
            "pat_margin_pct", pat / revenue * 100, "derived", "Profit after tax over revenue."
        )
    else:
        ratios["pat_margin_pct"] = Metric(
            "pat_margin_pct", None, "unavailable", "Revenue or profit after tax is unknown."
        )

    if revenue and ebitda is not None:
        ratios["ebitda_margin_pct"] = Metric(
            "ebitda_margin_pct", ebitda / revenue * 100, "derived", "EBITDA over revenue."
        )
    else:
        ratios["ebitda_margin_pct"] = Metric(
            "ebitda_margin_pct", None, "unavailable", "Revenue or EBITDA is unknown."
        )

    return ratios


# --------------------------------------------------------------------------- #
# Document analysis
# --------------------------------------------------------------------------- #


@dataclass
class FinancialAnalysis:
    """The full result: figures, ratios, and an audit trail for both."""

    reporting_scale: str
    scale_multiplier: float
    metrics: Dict[str, Metric]
    ratios: Dict[str, Metric]
    evidence: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "reporting_scale": self.reporting_scale,
            "scale_multiplier": self.scale_multiplier,
            "metrics": {name: metric.as_dict() for name, metric in self.metrics.items()},
            "ratios": {name: metric.as_dict() for name, metric in self.ratios.items()},
            "unresolved": sorted(
                name for name, metric in {**self.metrics, **self.ratios}.items()
                if metric.value is None
            ),
            "evidence": self.evidence,
            "warnings": self.warnings,
        }


def analyze_document(
    text: str,
    tables: Optional[Sequence[dict]] = None,
    dataframe: Optional[pd.DataFrame] = None,
) -> FinancialAnalysis:
    """Runs the regex analyzer and the metrics engine over one parsed document."""
    corpus = "\n".join(
        part for part in (text or "", _tables_to_text(tables or []), _frame_to_text(dataframe))
        if part.strip()
    )

    multiplier, scale_label = detect_reporting_scale(corpus)
    items = extract_line_items(corpus, scale=multiplier)
    metrics = derive_metrics(items)

    # Current maturities feed DSCR but are not a headline figure, so they are
    # attached after the main set rather than reported alongside EBITDA.
    current_portion = _reported(items, "current_portion_debt")
    metrics["current_portion_debt"] = Metric(
        "current_portion_debt",
        current_portion,
        "reported" if current_portion is not None else "unavailable",
        "Stated current maturities of long-term debt." if current_portion is not None
        else "No current maturities line was found.",
    )

    ratios = compute_ratios(metrics)

    warnings: List[str] = []
    if multiplier == 1.0:
        warnings.append(
            "No reporting unit was declared in the document, so figures are read as "
            "rupees. If the accounts are stated in lakh or crore, every figure below "
            "is understated by that factor."
        )
    if not items:
        warnings.append(
            "No recognisable financial line items were found. This may be a scanned "
            "document that did not OCR cleanly, or a statement rather than a set of accounts."
        )

    return FinancialAnalysis(
        reporting_scale=scale_label,
        scale_multiplier=multiplier,
        metrics=metrics,
        ratios=ratios,
        evidence={
            "line_items_found": {
                name: {"label": item.label, "line": item.source_line}
                for name, item in items.items()
            },
            "characters_scanned": len(corpus),
        },
        warnings=warnings,
    )


# --------------------------------------------------------------------------- #
# Estimation mode: no annual report
# --------------------------------------------------------------------------- #

# Narration fragments that mark a bank debit as interest or loan servicing.
# Used only to separate financing outflows from operating ones, never to change
# a figure that the accounts stated directly.
_INTEREST_MARKERS = ("interest", "int.pd", "int paid", "loan int")
_LOAN_MARKERS = ("emi", "loan repay", "loan instal", "term loan", "principal")

_MONTHS_PER_YEAR = 12


def estimate_from_operations(
    gst_taxable_turnover: Optional[float],
    bank_rows: Sequence[dict],
    period_months: float,
) -> FinancialAnalysis:
    """Estimates the same figures from GSTR-3B turnover and bank flows.

    For the very common case of a borrower with no audited accounts: a GSTR-3B
    return gives declared outward turnover, and a bank statement gives what
    actually moved. Together they support revenue, a proxy for profit, and an
    indicative debt-service figure.

    What they cannot support is a balance sheet. Net worth is returned as
    unavailable rather than approximated, because there is no honest way to get
    equity out of a cash-flow record, and a D/E ratio built on a guess would be
    worse than no ratio at all.
    """
    months = max(float(period_months), 1.0)
    annualise = _MONTHS_PER_YEAR / months if months < _MONTHS_PER_YEAR else 1.0

    credits = sum(
        abs(float(row.get("amount") or 0.0)) for row in bank_rows if row.get("type") == "credit"
    )

    # One pass, and every debit lands in exactly one bucket. Independent filters
    # double-count: a narration like "Interest paid on term loan" carries both an
    # interest marker and a loan marker, and would otherwise be added to interest
    # and to principal, inflating debt service and depressing DSCR.
    # Interest wins the tie because it is the more specific claim about the row.
    interest_paid = loan_principal = operating_outflow = 0.0
    for row in bank_rows:
        if row.get("type") != "debit":
            continue
        amount = abs(float(row.get("amount") or 0.0))
        if _matches(row, _INTEREST_MARKERS):
            interest_paid += amount
        elif _matches(row, _LOAN_MARKERS):
            loan_principal += amount
        else:
            operating_outflow += amount

    warnings: List[str] = [
        "Estimated from GSTR-3B and bank data, not from audited accounts. Every "
        "figure below is indicative and none of it is a substitute for filed financials.",
    ]

    # GSTR-3B declared turnover is the better revenue figure when present: bank
    # credits also contain loan drawdowns, transfers and refunds, none of which
    # are sales.
    if gst_taxable_turnover is not None:
        revenue = float(gst_taxable_turnover) * annualise
        revenue_basis = "Annualised GSTR-3B outward taxable turnover."
    else:
        revenue = credits * annualise
        revenue_basis = "Annualised bank credits. No GSTR-3B turnover was supplied."
        warnings.append(
            "Revenue is taken from bank credits, which include non-sales inflows such "
            "as loan drawdowns and transfers, so it is likely overstated."
        )

    if months < 3:
        warnings.append(
            f"Only {months:.0f} month(s) of data. Annualising this short a period "
            "amplifies any seasonal peak or trough into the whole-year figure."
        )

    surplus = (credits - operating_outflow - interest_paid) * annualise

    metrics: Dict[str, Metric] = {
        "revenue": Metric("revenue", revenue, "estimated", revenue_basis),
        "profit_after_tax": Metric(
            "profit_after_tax",
            surplus,
            "estimated",
            "Annualised cash surplus after operating outflows and interest. A cash "
            "proxy for profit: it carries no depreciation and no accruals.",
        ),
        "ebitda": Metric(
            "ebitda",
            (credits - operating_outflow) * annualise,
            "estimated",
            "Annualised cash surplus before interest. Depreciation is absent from a "
            "bank record, so this is an operating cash figure rather than true EBITDA.",
        ),
        "net_worth": Metric(
            "net_worth",
            None,
            "unavailable",
            "A balance sheet cannot be reconstructed from transaction flows.",
        ),
        "total_debt": Metric(
            "total_debt",
            None,
            "unavailable",
            "Outstanding borrowings are not visible in a statement of flows; only "
            "the servicing of them is.",
        ),
        "depreciation": Metric(
            "depreciation", None, "unavailable", "Not observable from bank data."
        ),
        "finance_cost": Metric(
            "finance_cost",
            interest_paid * annualise,
            "estimated",
            "Annualised bank debits whose narration marks them as interest.",
        ),
        "current_portion_debt": Metric(
            "current_portion_debt",
            loan_principal * annualise,
            "estimated",
            "Annualised bank debits whose narration marks them as loan or EMI repayment.",
        ),
    }

    return FinancialAnalysis(
        reporting_scale="rupees",
        scale_multiplier=1.0,
        metrics=metrics,
        ratios=compute_ratios(metrics),
        evidence={
            "period_months": months,
            "annualisation_factor": round(annualise, 4),
            "bank_credits": round(credits, 2),
            "operating_outflow": round(operating_outflow, 2),
            "interest_identified": round(interest_paid, 2),
            "loan_repayment_identified": round(loan_principal, 2),
            "gst_taxable_turnover": gst_taxable_turnover,
            "rows_examined": len(bank_rows),
        },
        warnings=warnings,
    )


def _matches(row: dict, markers: Sequence[str]) -> bool:
    """Whether a row's narration or category contains any of the markers."""
    haystack = f"{row.get('description') or ''} {row.get('category') or ''}".lower()
    return any(marker in haystack for marker in markers)


def demo() -> None:
    """Self-check across all three engines and the unit-scale trap."""
    assert detect_reporting_scale("Balance Sheet (Rs. in lakhs)") == (100_000.0, "lakh")
    assert detect_reporting_scale("Statement of Profit and Loss (₹ in crore)")[1] == "crore"
    assert detect_reporting_scale("Amounts in thousands")[1] == "thousand"
    assert detect_reporting_scale("no unit stated here") == (1.0, "rupees")

    # A year in a header must not be read as an amount, but a grouped 2,024 must.
    assert _numbers_on("Particulars 2024 2023") == []
    assert _numbers_on("Particulars 2025-26 2024-25") == []
    assert _numbers_on("Revenue from operations 2,024.00 1,880.00") == [2024.0, 1880.0]
    assert _numbers_on("Loss for the year (1,240.55)") == [-1240.55]

    report = """
    ABC Logistics Private Limited
    Statement of Profit and Loss (Rs. in lakhs)
    Particulars                                   2025-26      2024-25
    Revenue from operations                        4,500.00     3,900.00
    Other income                                      60.00        45.00
    Depreciation and amortisation                    310.00       295.00
    Finance costs                                    240.00       260.00
    Profit before tax                                720.00       540.00
    Tax expense                                      180.00       135.00
    Profit for the year                              540.00       405.00

    Balance Sheet
    Equity share capital                             500.00       500.00
    Reserves and surplus                           1,850.00     1,310.00
    Long term borrowings                           1,600.00     1,750.00
    Short term borrowings                            700.00       620.00
    Current maturities of long term debt              400.00       380.00
    """

    analysis = analyze_document(report)
    assert analysis.reporting_scale == "lakh"

    metrics = analysis.metrics
    # Every figure is scaled out of lakhs into rupees exactly once.
    assert metrics["revenue"].value == 4_500.00 * 100_000
    assert metrics["revenue"].source == "reported"
    assert metrics["profit_after_tax"].value == 540.00 * 100_000

    # EBITDA is not stated, so it is reconstructed: PBT + finance cost + depreciation.
    assert metrics["ebitda"].source == "derived"
    assert metrics["ebitda"].value == (720.00 + 240.00 + 310.00) * 100_000

    # Net worth and total debt are both derived from their components.
    assert metrics["net_worth"].value == (500.00 + 1_850.00) * 100_000
    assert metrics["net_worth"].source == "derived"
    assert metrics["total_debt"].value == (1_600.00 + 700.00) * 100_000

    ratios = analysis.ratios
    assert abs(ratios["debt_to_equity"].value - 2_300.0 / 2_350.0) < 1e-9
    # DSCR uses interest plus current maturities, both of which were found.
    assert abs(ratios["dscr"].value - 1_270.0 / (240.0 + 400.0)) < 1e-9
    assert "current maturities" in ratios["dscr"].basis
    assert abs(ratios["pat_margin_pct"].value - 12.0) < 1e-9
    assert analysis.as_dict()["unresolved"] == []

    # A stated EBITDA is reported, not recomputed behind the filer's back.
    stated = analyze_document("EBITDA 1,000.00\nRevenue from operations 5,000.00")
    assert stated.metrics["ebitda"].source == "reported"
    assert stated.metrics["ebitda"].value == 1000.0

    # An empty document must warn rather than emit confident zeros.
    empty = analyze_document("")
    assert empty.metrics["revenue"].value is None
    assert empty.ratios["dscr"].value is None
    assert any("No recognisable" in w for w in empty.warnings)

    # Negative net worth must not produce a meaningless ratio.
    eroded = analyze_document(
        "Equity share capital 100.00\nReserves and surplus (400.00)\nTotal debt 900.00"
    )
    assert eroded.metrics["net_worth"].value == -300.0
    assert eroded.ratios["debt_to_equity"].value is None
    assert "negative" in eroded.ratios["debt_to_equity"].basis

    # --- estimation mode --------------------------------------------------- #
    bank = [
        {"type": "credit", "amount": 200_000, "description": "UPI sales"},
        {"type": "credit", "amount": 150_000, "description": "Customer payment"},
        {"type": "debit", "amount": 90_000, "description": "Fuel and supplies"},
        {"type": "debit", "amount": 12_000, "description": "Interest paid on term loan"},
        {"type": "debit", "amount": 30_000, "description": "EMI term loan"},
    ]
    estimated = estimate_from_operations(1_200_000.0, bank, period_months=6)

    assert estimated.metrics["revenue"].source == "estimated"
    assert estimated.metrics["revenue"].value == 2_400_000.0  # 6 months doubled
    # Loan principal is financing, not an operating cost, so it stays out of EBITDA.
    assert estimated.metrics["ebitda"].value == (350_000 - 90_000) * 2
    assert estimated.metrics["profit_after_tax"].value == (350_000 - 90_000 - 12_000) * 2
    assert estimated.metrics["finance_cost"].value == 24_000.0
    assert estimated.metrics["current_portion_debt"].value == 60_000.0
    # No balance sheet means no net worth and therefore no D/E, stated as unknown.
    assert estimated.metrics["net_worth"].value is None
    assert estimated.ratios["debt_to_equity"].value is None
    assert estimated.ratios["dscr"].value is not None

    # Without GSTR-3B, revenue falls back to bank credits and says so.
    no_gst = estimate_from_operations(None, bank, period_months=12)
    assert no_gst.metrics["revenue"].value == 350_000.0
    assert any("non-sales inflows" in w for w in no_gst.warnings)

    print("financial_statements.py self-check passed")


if __name__ == "__main__":
    demo()
