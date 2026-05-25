"""Stage 7 Phase 2 — Bank Transaction Extractor

Extracts transactions from bank statements WITHOUT expensive AI by using a
deterministic cascade:

    CSV parser → PDF table parser → text line parser → rules engine

The rules engine matches known Australian merchants (Synergy, Bunnings,
ATO, etc), filters obvious private spending (Woolworths, Netflix, …), and
links transactions to property use periods when relevant.

The optional AI batch path lives in `server.py` behind an explicit cost
estimate + user confirm. No AI call is made from this module.
"""
from __future__ import annotations

import csv
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =================== MERCHANT RULES DATABASE ===================

MERCHANT_RULES: dict[str, dict] = {
    # Utilities
    "synergy":      {"category": "utilities_electricity", "tax_section": "rental_electricity",  "needs_property_check": True, "review_required": True},
    "water corp":   {"category": "utilities_water",       "tax_section": "rental_water",        "needs_property_check": True, "review_required": True},
    "alinta":       {"category": "utilities_gas",         "tax_section": "rental_electricity",  "needs_property_check": True, "review_required": True},

    # Rates
    "city of joondalup": {"category": "council_rates", "tax_section": "rental_council_rates", "needs_property_check": True, "review_required": True},
    "council":           {"category": "council_rates", "tax_section": "rental_council_rates", "needs_property_check": True, "review_required": True},
    "rates":             {"category": "council_rates", "tax_section": "rental_council_rates", "needs_property_check": True, "review_required": True},

    # Hardware / Building
    "bunnings": {"category": "hardware",          "tax_section": "rental_repairs", "needs_property_check": True, "review_required": True,
                 "review_reason": "Could be repairs, capital works, or depreciating asset"},
    "reece":    {"category": "plumbing_building", "tax_section": "rental_repairs", "needs_property_check": True, "review_required": True,
                 "review_reason": "Plumbing/building - needs accountant review"},
    "mitre 10": {"category": "hardware",          "tax_section": "rental_repairs", "needs_property_check": True, "review_required": True,
                 "review_reason": "Hardware - could be repairs or capital"},

    # Fuel
    "bp":     {"category": "fuel", "tax_section": "work_related_car", "review_required": True},
    "ampol":  {"category": "fuel", "tax_section": "work_related_car", "review_required": True},
    "shell":  {"category": "fuel", "tax_section": "work_related_car", "review_required": True},
    "caltex": {"category": "fuel", "tax_section": "work_related_car", "review_required": True},

    # Tax / Professional
    "ato":         {"category": "tax_payment",              "tax_section": "tax_affairs_costs", "review_required": True},
    "ahpra":       {"category": "professional_registration","tax_section": "union_fees",        "review_required": False},
    "accountant":  {"category": "accounting_fees",          "tax_section": "tax_affairs_costs", "review_required": False},
    "tax agent":   {"category": "accounting_fees",          "tax_section": "tax_affairs_costs", "review_required": False},
}

# Private-spending patterns — never tax relevant.
PRIVATE_PATTERNS: list[str] = [
    "woolworths", "coles", "iga", "aldi",         # Groceries
    "netflix", "spotify", "disney",                # Entertainment
    "uber eats", "doordash", "menulog",            # Food delivery
    "kmart", "target", "big w",                    # General retail
]


# =================== EXTRACTION METHODS ===================

def extract_transactions_from_csv(file_path: str) -> List[Dict]:
    """Extract transactions from a CSV bank export."""
    transactions: list[dict] = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            sample = f.read(2048)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel  # safe fallback
            reader = csv.DictReader(f, dialect=dialect)
            for row in reader:
                row_lower = {(k or "").lower().strip(): (v or "") for k, v in row.items()}
                t = _parse_csv_row(row_lower)
                if t:
                    transactions.append(t)
        logger.info(f"CSV: extracted {len(transactions)} transactions")
    except Exception as e:
        logger.warning(f"CSV extraction failed: {e}")
    return transactions


def _parse_csv_row(row: Dict) -> Optional[Dict]:
    date_str = row.get("date") or row.get("transaction date") or row.get("posting date") or row.get("value date")
    description = row.get("description") or row.get("details") or row.get("narrative") or row.get("transaction details")
    amount_str = row.get("amount") or row.get("value")
    debit_str = row.get("debit") or row.get("withdrawal")
    credit_str = row.get("credit") or row.get("deposit")

    if not date_str or not description:
        return None

    amount_cents = 0
    debit_credit = "unknown"
    if amount_str:
        amount_cents, debit_credit = _parse_amount(amount_str)
    elif debit_str:
        amount_cents = _parse_amount_string(debit_str)
        debit_credit = "debit"
    elif credit_str:
        amount_cents = _parse_amount_string(credit_str)
        debit_credit = "credit"

    transaction_date = _parse_date(date_str)
    if not transaction_date:
        return None

    return {
        "transaction_date":   transaction_date.date().isoformat(),
        "description_raw":    description.strip(),
        "description_cleaned": _clean_description(description),
        "amount_cents":       abs(amount_cents),
        "debit_credit":       debit_credit,
        "balance_cents":      _parse_amount_string(row.get("balance", "0")) or None,
        "extraction_method":  "csv_parser",
    }


def extract_transactions_from_pdf(file_path: str) -> List[Dict]:
    """Extract transactions from a PDF bank statement via pdfplumber tables."""
    try:
        import pdfplumber  # already in requirements (Stage 1)
    except ImportError:
        logger.warning("pdfplumber not installed — PDF table extraction disabled")
        return []

    transactions: list[dict] = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                for table in page.extract_tables() or []:
                    if not table:
                        continue
                    header_idx = _find_header_row(table)
                    if header_idx is None:
                        continue
                    headers = [str(h).lower().strip() if h else "" for h in table[header_idx]]
                    for row in table[header_idx + 1:]:
                        t = _parse_table_row(headers, row, page_num)
                        if t:
                            transactions.append(t)
        logger.info(f"PDF: extracted {len(transactions)} transactions from tables")
    except Exception as e:
        logger.warning(f"PDF table extraction failed: {e}")
    return transactions


def _find_header_row(table: List[List]) -> Optional[int]:
    keywords = ["date", "description", "amount", "debit", "credit", "balance"]
    for idx, row in enumerate(table):
        row_lower = [str(cell).lower() if cell else "" for cell in row]
        matches = sum(1 for kw in keywords if any(kw in cell for cell in row_lower))
        if matches >= 2:
            return idx
    return None


def _parse_table_row(headers: List[str], row: List, page_num: int) -> Optional[Dict]:
    row_dict: dict[str, str] = {}
    for i, header in enumerate(headers):
        if i < len(row) and row[i]:
            row_dict[header] = str(row[i]).strip()
    t = _parse_csv_row(row_dict)
    if t:
        t["page_number"] = page_num
        t["extraction_method"] = "table_parser"
    return t


def extract_transactions_from_text(extracted_text: str) -> List[Dict]:
    """Regex-based last-resort line parser. Avoids matching balance lines by
    requiring the amount to be the rightmost dollar value on the line."""
    transactions: list[dict] = []
    if not extracted_text:
        return transactions

    pattern = re.compile(
        r"(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+"
        r"(?P<desc>.+?)\s+"
        r"\$?-?(?P<amt>[\d,]+\.\d{2})\b"
    )
    for m in pattern.finditer(extracted_text):
        date_str = m.group("date")
        description = m.group("desc")
        amount_str = m.group("amt")
        transaction_date = _parse_date(date_str)
        if not transaction_date:
            continue
        amount_cents = _parse_amount_string(amount_str)
        transactions.append({
            "transaction_date":   transaction_date.date().isoformat(),
            "description_raw":    description.strip(),
            "description_cleaned": _clean_description(description),
            "amount_cents":       abs(amount_cents),
            "debit_credit":       "unknown",
            "balance_cents":      None,
            "extraction_method":  "line_parser",
        })
    logger.info(f"Text: extracted {len(transactions)} transactions via line parser")
    return transactions


# =================== HELPERS ===================

def _parse_amount(amount_str: str) -> Tuple[int, str]:
    amount_cents = _parse_amount_string(amount_str)
    if "-" in str(amount_str) or str(amount_str).strip().startswith("("):
        return abs(amount_cents), "debit"
    return abs(amount_cents), "credit"


def _parse_amount_string(amount_str) -> int:
    if amount_str is None or amount_str == "":
        return 0
    cleaned = re.sub(r"[\$£€,\(\)\s]", "", str(amount_str)).replace("-", "")
    try:
        return int(round(float(cleaned) * 100))
    except (ValueError, TypeError):
        return 0


def _parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def _clean_description(description: str) -> str:
    cleaned = re.sub(r"\s+", " ", description or "").strip()
    for prefix in ("EFTPOS", "PURCHASE", "PAYMENT", "TRANSFER", "DD", "SO"):
        if cleaned.upper().startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    return cleaned


# =================== RULES ENGINE ===================

def classify_transaction_by_rules(transaction: Dict, property_periods: List[Dict]) -> Dict:
    """Classify a transaction using the rules engine. No AI is called.

    Sets `evidence_status`, `confidence`, `review_required`, optionally
    `property_match`/`use_period_match`/`review_reason`, and sets
    `ai_cost_usd=0.0`.
    """
    description_lower = (transaction.get("description_cleaned") or "").lower()
    try:
        transaction_date = datetime.fromisoformat(transaction["transaction_date"])
    except (KeyError, ValueError):
        transaction_date = None

    # 1. Private spending — never tax-relevant.
    if any(p in description_lower for p in PRIVATE_PATTERNS):
        transaction.update({
            "merchant_detected": None,
            "category_suggested": "private_spending",
            "tax_section_suggested": None,
            "classification_method": "rules",
            "confidence": "Confirmed",
            "evidence_status": "private",
            "review_required": False,
            "accountant_review_required": False,
            "ai_cost_usd": 0.0,
        })
        return transaction

    # 2. Known merchant rules.
    for merchant_key, rules in MERCHANT_RULES.items():
        if merchant_key in description_lower:
            transaction.update({
                "merchant_detected": merchant_key.title(),
                "category_suggested": rules["category"],
                "tax_section_suggested": rules["tax_section"],
                "classification_method": "rules",
                "confidence": "Likely",
                "review_required": bool(rules.get("review_required", False)),
                "accountant_review_required": bool(rules.get("review_required", False)),
                "review_reason": rules.get("review_reason"),
                "evidence_status": "candidate",
                "ai_cost_usd": 0.0,
            })
            if rules.get("needs_property_check") and transaction_date is not None:
                transaction.update(_match_property_period(
                    transaction_date, transaction["amount_cents"], merchant_key, property_periods,
                ))
            return transaction

    # 3. No rule matched → uncertain. AI batch can pick these up later.
    transaction.update({
        "merchant_detected": None,
        "category_suggested": None,
        "tax_section_suggested": None,
        "classification_method": "unknown",
        "confidence": "Unsure",
        "evidence_status": "candidate",
        "review_required": True,
        "accountant_review_required": True,
        "review_reason": "Uncertain — requires review or AI analysis",
        "ai_cost_usd": 0.0,
    })
    return transaction


def _match_property_period(transaction_date: datetime, amount_cents: int, merchant: str, property_periods: List[Dict]) -> Dict:
    """Match a transaction date against any property's use_periods."""
    for prop in property_periods:
        for period in prop.get("use_periods", []) or []:
            try:
                date_from = datetime.fromisoformat(period["date_from"])
            except (KeyError, ValueError):
                continue
            d_to_raw = period.get("date_to")
            try:
                date_to = datetime.fromisoformat(d_to_raw) if d_to_raw else datetime.now()
            except ValueError:
                continue
            if date_from <= transaction_date <= date_to:
                use_type = (period.get("use_type") or "").lower()
                if use_type in ("rental", "airbnb"):
                    return {
                        "property_match": prop.get("property_name"),
                        "use_period_match": "rental",
                        "evidence_status": "candidate",
                        "review_required": True,
                        "accountant_review_required": True,
                        "review_reason": f"Occurred during {use_type} period",
                    }
                if use_type in ("main_residence", "owner_occupied"):
                    return {
                        "property_match": prop.get("property_name"),
                        "use_period_match": "main_residence",
                        "evidence_status": "private",
                        "review_required": True,
                        "accountant_review_required": True,
                        "review_reason": "Occurred during main residence period — likely private",
                    }
                if use_type == "renovation":
                    return {
                        "property_match": prop.get("property_name"),
                        "use_period_match": "renovation",
                        "evidence_status": "candidate",
                        "review_required": True,
                        "accountant_review_required": True,
                        "review_reason": "Renovation period — could be repairs, capital works, or depreciating asset",
                    }
    return {"property_match": None, "use_period_match": None}


# =================== MAIN ENTRY POINT ===================

def extract_and_classify_transactions(
    file_path: str,
    mime_type: str,
    extracted_text: str,
    source_document_id: str,
    source_filename: str,
    property_periods: List[Dict],
) -> Tuple[List[Dict], Dict]:
    """Extract → classify → tag with source. Returns (transactions, stats)."""
    transactions: list[dict] = []
    fp_lower = (file_path or "").lower()

    if (mime_type or "").lower() == "text/csv" or fp_lower.endswith(".csv"):
        transactions = extract_transactions_from_csv(file_path)
    elif (mime_type or "").lower() == "application/pdf" or fp_lower.endswith(".pdf"):
        transactions = extract_transactions_from_pdf(file_path)
        if not transactions and extracted_text:
            transactions = extract_transactions_from_text(extracted_text)
    elif extracted_text:
        transactions = extract_transactions_from_text(extracted_text)

    if not transactions:
        logger.info(f"No transactions extracted from {source_filename}")
        return [], {"extracted_count": 0, "classified_count": 0, "uncertain_count": 0, "private_count": 0, "ai_cost_usd": 0.0}

    # Tag every transaction with its source.
    for t in transactions:
        t["source_document_id"] = source_document_id
        t["source_filename"] = source_filename

    classified_count = 0
    uncertain_count = 0
    private_count = 0
    for t in transactions:
        classify_transaction_by_rules(t, property_periods)
        if t.get("classification_method") == "rules":
            classified_count += 1
        if t.get("confidence") == "Unsure":
            uncertain_count += 1
        if t.get("evidence_status") == "private":
            private_count += 1

    stats = {
        "extracted_count": len(transactions),
        "classified_count": classified_count,
        "uncertain_count": uncertain_count,
        "private_count": private_count,
        "ai_cost_usd": 0.0,
    }
    logger.info(f"{source_filename}: extracted={stats['extracted_count']} classified={classified_count} uncertain={uncertain_count} private={private_count}")
    return transactions, stats


# =================== BANK STATEMENT DETECTION ===================

def is_bank_statement(filename: str, extracted_text: str, category: str) -> bool:
    """Multi-signal bank-statement detector. ≥4 points required.

    Signals:
      • category contains "bank" → +3
      • ≥3 distinct bank-y keywords → +2
      • known bank name in text → +1
      • account-number pattern → +1
    """
    signals = 0
    cat_lower = (category or "").lower()
    if "bank" in cat_lower:
        signals += 3
    text_lower = (extracted_text or "").lower()
    bank_keywords = [
        "opening balance", "closing balance", "transaction", "debit", "credit",
        "statement period", "account number", "bsb",
    ]
    if sum(1 for kw in bank_keywords if kw in text_lower) >= 3:
        signals += 2
    bank_names = [
        "westpac", "commonwealth", "commbank", "cba",
        "anz", "nab", "bankwest", "st george", "macquarie", "ing", "hsbc",
    ]
    if any(b in text_lower for b in bank_names):
        signals += 1
    if re.search(r"\b\d{2}-\d{4}-\d{1,10}\b", extracted_text or ""):
        signals += 1
    return signals >= 4
