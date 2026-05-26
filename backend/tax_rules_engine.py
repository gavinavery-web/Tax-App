"""ATO Rules Engine — year-versioned rates, thresholds, and draft calculation
helpers. This module never makes definitive deductibility claims. Every
output is labelled DRAFT and requires accountant review.

Rules sourced from ATO guidance. Editable without code changes via
tax_rules.json (loaded once at startup).
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)
_ROOT = Path(__file__).parent
_RULES_CACHE: Optional[dict] = None


def load_rules() -> dict:
    global _RULES_CACHE
    if _RULES_CACHE is None:
        with open(_ROOT / "tax_rules.json", "r", encoding="utf-8") as f:
            _RULES_CACHE = json.load(f)
    return _RULES_CACHE


def get_rule(rule_key: str, tax_year: str) -> Optional[dict]:
    """Returns the rule object for (key, year) or None."""
    rules = load_rules()
    by_key = rules.get(rule_key, {})
    return by_key.get(tax_year)


def calculate_car_cents_per_km(tax_year: str, km: float) -> dict:
    """Cents-per-km method. Caps km at 5,000."""
    rule = get_rule("car_cents_per_km", tax_year)
    if not rule:
        return {"ok": False, "error": f"No car rule for {tax_year}"}
    effective_km = min(max(float(km), 0), rule["max_km"])
    return {
        "ok": True,
        "method": "cents_per_km",
        "tax_year": tax_year,
        "rate": rule["rate"],
        "max_km": rule["max_km"],
        "effective_km": effective_km,
        "draft_amount": round(effective_km * rule["rate"], 2),
        "evidence_required": "Basis for km estimate (rosters / calendar / job records)",
        "accountant_review_required": True,
        "note": "DRAFT — accountant review required. Home-to-work travel is usually private.",
        "source_url": rule.get("source_url"),
    }


def calculate_wfh_fixed_rate(tax_year: str, hours: float) -> dict:
    """Working-from-home fixed-rate method."""
    rule = get_rule("wfh_fixed_rate", tax_year)
    if not rule:
        return {"ok": False, "error": f"No WFH rule for {tax_year}"}
    h = max(float(hours), 0)
    return {
        "ok": True,
        "method": "wfh_fixed_rate",
        "tax_year": tax_year,
        "rate": rule["rate"],
        "hours": h,
        "draft_amount": round(h * rule["rate"], 2),
        "evidence_required": "Record of hours worked from home (diary/timesheet/calendar)",
        "accountant_review_required": True,
        "note": "DRAFT — accountant review required.",
        "source_url": rule.get("source_url"),
    }


def calculate_phone_internet_apportionment(bill_amount: float, work_use_percent: float) -> dict:
    """Apportion phone/internet by work-use percentage."""
    amount = max(float(bill_amount), 0)
    pct = max(min(float(work_use_percent), 100), 0)
    return {
        "ok": True,
        "method": "phone_internet_apportionment",
        "bill_amount": amount,
        "work_use_percent": pct,
        "draft_amount": round(amount * pct / 100, 2),
        "evidence_required": "Bill + calculation basis for work-use %",
        "accountant_review_required": pct > 50,  # high % triggers review
        "note": "DRAFT — accountant review required if work-use % is high or unsupported.",
    }


def work_expense_evidence_threshold(tax_year: str) -> dict:
    """The $300 threshold — informational only."""
    rule = get_rule("work_expense_threshold", tax_year)
    if not rule:
        return {"ok": False, "error": f"No threshold rule for {tax_year}"}
    return {
        "ok": True,
        "threshold": rule["amount"],
        "tax_year": tax_year,
        "note": (
            f"If total work-related expenses are ≤ ${rule['amount']}, written evidence "
            "may not be required in full but you must still show how the claim was worked out. "
            f"If > ${rule['amount']}, written evidence is generally required."
        ),
        "source_url": rule.get("source_url"),
    }
