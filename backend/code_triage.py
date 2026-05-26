"""Code-first triage for the upload pipeline.

Two responsibilities:

1. `extract_document_date(filename, text)` — pull a likely document date
   from filename and/or text. Returns (iso_date, confidence) or (None, "none").

2. `classify_by_rules(filename, text)` — match against a deterministic rules
   table of known counterparties/document types. Returns a classification
   dict if confident, otherwise None. The caller is responsible for falling
   through to the AI classifier on None.

This module never raises on bad input — it returns None / 'none' instead.
"""
from __future__ import annotations

import re
import logging
from datetime import date
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ----- Date extraction -----

# Cheap, fast regex patterns. Order matters — more-specific first.
# We use (?<!\d) / (?!\d) lookarounds instead of \b because filenames
# often use `_` as a separator and `_` counts as a word character —
# so `\b` doesn't fire between `synergy_` and `2025`.
_DATE_PATTERNS = [
    # 2025-03-15, 2025_03_15, 2025/03/15
    (re.compile(r"(?<!\d)(20\d{2})[-_/](0[1-9]|1[0-2])[-_/](0[1-9]|[12]\d|3[01])(?!\d)"), "ymd"),
    # 15-03-2025, 15/03/2025  (Australian d/m/y — common in filenames)
    (re.compile(r"(?<!\d)(0[1-9]|[12]\d|3[01])[-/](0[1-9]|1[0-2])[-/](20\d{2})(?!\d)"), "dmy"),
    # 03-2025, 03_2025, 03/2025  (month-year)
    (re.compile(r"(?<!\d)(0[1-9]|1[0-2])[-_/](20\d{2})(?!\d)"), "my"),
    # 2025-03, 2025_03  (year-month)
    (re.compile(r"(?<!\d)(20\d{2})[-_/](0[1-9]|1[0-2])(?!\d)"), "ym"),
    # March 2025, Mar 2025, march_2025
    (re.compile(r"(?<![a-z])(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s_-]+(20\d{2})(?!\d)", re.IGNORECASE), "monyear"),
    # 2025 alone, only as a last resort (low confidence)
    (re.compile(r"(?<!\d)(20\d{2})(?!\d)"), "year_only"),
]

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_match(kind: str, m: re.Match) -> Optional[date]:
    try:
        if kind == "ymd":
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if kind == "dmy":
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if kind == "my":
            return date(int(m.group(2)), int(m.group(1)), 15)
        if kind == "ym":
            return date(int(m.group(1)), int(m.group(2)), 15)
        if kind == "monyear":
            mon = _MONTH_MAP[m.group(1)[:3].lower()]
            return date(int(m.group(2)), mon, 15)
        if kind == "year_only":
            return date(int(m.group(1)), 6, 30)  # mid-year fallback
    except (ValueError, KeyError):
        return None
    return None


def extract_document_date(filename: str, text: str) -> Tuple[Optional[str], str]:
    """Returns (iso_date_string, confidence).

    confidence is one of: 'high' (specific day from filename), 'medium' (month+year),
    'low' (year only, or only from body text), 'none'.

    Filename hits beat body text hits for the same kind. We do NOT call out to
    external services or LLMs.
    """
    fn = filename or ""
    body = (text or "")[:5000]  # cap to first 5kB to keep this fast

    # Scan filename first — usually the cleanest signal
    for pattern, kind in _DATE_PATTERNS:
        m = pattern.search(fn)
        if m:
            d = _parse_match(kind, m)
            if d and 2010 <= d.year <= 2099:
                conf = "high" if kind in ("ymd", "dmy") else ("medium" if kind in ("my", "ym", "monyear") else "low")
                return d.isoformat(), conf

    # Fall back to body text
    for pattern, kind in _DATE_PATTERNS:
        m = pattern.search(body)
        if m:
            d = _parse_match(kind, m)
            if d and 2010 <= d.year <= 2099:
                # Body hits drop one confidence level
                conf = "medium" if kind in ("ymd", "dmy") else ("low" if kind in ("my", "ym", "monyear") else "low")
                return d.isoformat(), conf

    return None, "none"


def date_to_financial_year(iso_date: Optional[str]) -> Optional[str]:
    """Australian FY: 1 Jul YYYY → 30 Jun YYYY+1 is called FY(YYYY+1)."""
    if not iso_date:
        return None
    try:
        d = date.fromisoformat(iso_date)
    except (ValueError, TypeError):
        return None
    return f"FY{d.year + 1}" if d.month >= 7 else f"FY{d.year}"


# ----- Rules-based classification -----
#
# (regex, classification dict)  — first hit wins.
# `category` MUST match an existing CATEGORY_TO_FOLDER key in server.py
# (00 Inbox, 01 ATO, 02 PAYG Income, 03 Airbnb, 04 Waggrakine Rental,
#  05 Heathridge, 06 Revive, 07 Bank Statements, 08 Salary Packaging Maxxia,
#  09 Accountant Review, 10 Missing Evidence, 11 Final Accountant Pack)
# so files route to the correct existing Drive folder.

FILENAME_RULES: list[tuple[re.Pattern, dict]] = [
    (re.compile(r"synergy",                       re.IGNORECASE), {"category": "05 Heathridge",         "doc_type": "utility_electricity", "confidence": 0.9}),
    (re.compile(r"alinta",                        re.IGNORECASE), {"category": "05 Heathridge",         "doc_type": "utility_gas",         "confidence": 0.9}),
    (re.compile(r"water.?corp|watercorp",         re.IGNORECASE), {"category": "05 Heathridge",         "doc_type": "utility_water",       "confidence": 0.85}),
    (re.compile(r"airbnb",                        re.IGNORECASE), {"category": "03 Airbnb",             "doc_type": "airbnb_statement",    "confidence": 0.9}),
    (re.compile(r"payg|payment[\s_-]?summary|income[\s_-]?statement", re.IGNORECASE), {"category": "02 PAYG Income", "doc_type": "payg_summary", "confidence": 0.85}),
    (re.compile(r"\bahpra\b",                     re.IGNORECASE), {"category": "09 Accountant Review",  "doc_type": "professional_registration", "confidence": 0.9}),
    (re.compile(r"vodafone|telstra|optus",        re.IGNORECASE), {"category": "09 Accountant Review",  "doc_type": "phone_bill",          "confidence": 0.8}),
    (re.compile(r"mortgage|loan[\s_-]?statement|interest[\s_-]?statement", re.IGNORECASE), {"category": "09 Accountant Review", "doc_type": "loan_interest", "confidence": 0.8}),
    (re.compile(r"council|rates[\s_-]?notice",    re.IGNORECASE), {"category": "09 Accountant Review",  "doc_type": "council_rates",       "confidence": 0.85}),
    (re.compile(r"bunnings|mitre|reece",          re.IGNORECASE), {"category": "09 Accountant Review",  "doc_type": "hardware_repairs",    "confidence": 0.75}),
    (re.compile(r"bupa|medibank|hcf|private[\s_-]?health", re.IGNORECASE), {"category": "09 Accountant Review", "doc_type": "private_health", "confidence": 0.85}),
    (re.compile(r"maxxia",                        re.IGNORECASE), {"category": "08 Salary Packaging Maxxia", "doc_type": "salary_packaging", "confidence": 0.9}),
    (re.compile(r"bank[\s_-]?statement|statement[\s_-]?\d",      re.IGNORECASE), {"category": "07 Bank Statements", "doc_type": "bank_statement", "confidence": 0.8}),
]

# Body-text hints (lower confidence — only used to reinforce a filename hit
# or to provide a fallback). Same shape.
TEXT_RULES: list[tuple[re.Pattern, dict]] = [
    (re.compile(r"\bsynergy\b",                   re.IGNORECASE), {"category": "05 Heathridge",     "doc_type": "utility_electricity", "confidence": 0.75}),
    (re.compile(r"\balinta\s+energy\b",           re.IGNORECASE), {"category": "05 Heathridge",     "doc_type": "utility_gas",         "confidence": 0.75}),
    (re.compile(r"airbnb",                        re.IGNORECASE), {"category": "03 Airbnb",         "doc_type": "airbnb_statement",    "confidence": 0.75}),
    (re.compile(r"ahpra",                         re.IGNORECASE), {"category": "09 Accountant Review", "doc_type": "professional_registration", "confidence": 0.75}),
    (re.compile(r"payg\s+payment\s+summary|income\s+statement", re.IGNORECASE), {"category": "02 PAYG Income", "doc_type": "payg_summary", "confidence": 0.75}),
]

CODE_TRIAGE_THRESHOLD = 0.8  # confidence at/above this means SKIP AI


def classify_by_rules(filename: str, text: str) -> Optional[dict]:
    """Return a classification dict if a rule fires with confidence >= 0.7,
    else None. Confidence at/above CODE_TRIAGE_THRESHOLD signals 'skip AI'.

    Returned shape: {"category": str, "doc_type": str, "confidence": float,
                     "source": "filename" | "text"}
    """
    fn = filename or ""
    body = (text or "")[:5000]

    for pattern, payload in FILENAME_RULES:
        if pattern.search(fn):
            return {**payload, "source": "filename"}

    for pattern, payload in TEXT_RULES:
        if pattern.search(body):
            return {**payload, "source": "text"}

    return None
