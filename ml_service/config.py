"""Central, environment-overridable settings for the scoring service.

Every tunable that an underwriter might want to move without a code change lives
here: score bands, risk pricing, upload limits. Values are read once at import.
"""

import os

# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #

PORT = int(os.getenv("PORT", "8001"))

# --------------------------------------------------------------------------- #
# Hybrid score composition
# --------------------------------------------------------------------------- #

RULE_WEIGHT = float(os.getenv("RULE_WEIGHT", "0.4"))
ML_WEIGHT = float(os.getenv("ML_WEIGHT", "0.6"))

MIN_SCORE = 0.0
MAX_SCORE = 800.0

# Confidence reported when the ML path is unavailable and the score is 100%
# rule-based. Fixed rather than calibrated - see the ponytail note in main.py.
RULES_ONLY_CONFIDENCE = 0.6

# --------------------------------------------------------------------------- #
# Score bands (0-800)
# --------------------------------------------------------------------------- #
# GOOD/STANDARD are the product's three public categories and are also the
# approve/refer/reject boundaries, so a "Good" applicant can never come back
# with a REJECT decision. EXCELLENT only splits the approve band into two
# pricing tiers; it is not a separate category.

SCORE_EXCELLENT = float(os.getenv("SCORE_EXCELLENT", "680"))
SCORE_GOOD = float(os.getenv("SCORE_GOOD", "600"))
SCORE_STANDARD = float(os.getenv("SCORE_STANDARD", "400"))

# --------------------------------------------------------------------------- #
# Risk-based pricing
# --------------------------------------------------------------------------- #

# Unsecured gig-worker credit prices well above a secured NBFC book, hence a
# base materially higher than a corporate lending rate.
BASE_INTEREST_RATE_PCT = float(os.getenv("BASE_INTEREST_RATE_PCT", "14.0"))

# Basis points added to the base rate, by risk tier. 100 bps = 1%.
RISK_PREMIUM_BPS = {
    "LOW": int(os.getenv("RISK_PREMIUM_LOW_BPS", "150")),
    "MODERATE": int(os.getenv("RISK_PREMIUM_MODERATE_BPS", "350")),
    "HIGH": int(os.getenv("RISK_PREMIUM_HIGH_BPS", "700")),
    "VERY_HIGH": int(os.getenv("RISK_PREMIUM_VERY_HIGH_BPS", "1200")),
}

# Credit limit is a multiple of monthly payout, not of net worth: a gig worker
# has income, not a balance sheet.
WEEKS_PER_MONTH = 4.33
LOAN_MULTIPLIER = {
    "LOW": float(os.getenv("LOAN_MULTIPLIER_LOW", "3.0")),
    "MODERATE": float(os.getenv("LOAN_MULTIPLIER_MODERATE", "2.0")),
    "HIGH": float(os.getenv("LOAN_MULTIPLIER_HIGH", "1.0")),
    "VERY_HIGH": 0.0,
}

TENOR_MONTHS = {"LOW": 24, "MODERATE": 12, "HIGH": 6, "VERY_HIGH": 0}

# --------------------------------------------------------------------------- #
# Statement ingestion
# --------------------------------------------------------------------------- #

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))

ALLOWED_UPLOAD_EXTENSIONS = frozenset(
    {".pdf", ".csv", ".xlsx", ".xls", ".xlsm", ".docx", ".doc", ".txt"}
)

# A statement shorter than this cannot support a weekly average worth scoring.
MIN_STATEMENT_DAYS = int(os.getenv("MIN_STATEMENT_DAYS", "14"))
