"""Missing Evidence Tracker — Stage 2

Seed the canonical checklist, match uploaded documents safely (never mark
Received from category alone), and recommend the single next best document
the user should chase.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------
ALLOWED_STATUS = ["Outstanding", "Possible Match", "Received", "Not applicable", "Accountant Review"]
ALLOWED_PRIORITY = ["Critical", "Important", "Later"]
ALLOWED_MATCH_CONFIDENCE = ["Confirmed", "Likely", "Unsure"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Match rules  — used by check_and_update_missing_evidence
# ---------------------------------------------------------------------------
# Per-item: `any_of` — at least one keyword/phrase must appear (case-insens)
#           `not_any_of` — none of these may appear (disqualifies)
#           `requires_figure_label` — at least one headline figure label must
#                                      contain at least one of these tokens.
# All checks run against a normalised blob of document_type +
# one_line_summary + suggested_filename + filename.
MATCH_RULES: dict[str, dict[str, Any]] = {
    # ---------- Airbnb income (Critical) ----------
    "airbnb-income-fy2024": {
        "any_of": ["airbnb earnings", "airbnb payout", "airbnb annual", "airbnb income",
                   "earnings summary", "payout report", "transaction export",
                   "earnings statement", "income schedule"],
        "not_any_of": ["cleaning", "supplies", "linen", "toiletries", "receipt",
                       "guest message", "bunnings", "kmart", "ikea"],
        "requires_figure_label": ["payout", "income", "earnings", "gross"],
    },
    "airbnb-income-fy2025": {
        "any_of": ["airbnb earnings", "airbnb payout", "airbnb annual", "airbnb income",
                   "earnings summary", "payout report", "transaction export",
                   "earnings statement", "income schedule"],
        "not_any_of": ["cleaning", "supplies", "linen", "toiletries", "receipt",
                       "guest message", "bunnings", "kmart", "ikea"],
        "requires_figure_label": ["payout", "income", "earnings", "gross"],
    },
    # ---------- Heathridge mortgage interest ----------
    "heathridge-mortgage-interest-fy2024": {
        "any_of": ["mortgage interest", "interest statement", "interest charged",
                   "tax statement", "loan tax", "annual interest"],
        "not_any_of": ["repayment screenshot", "balance only"],
        "requires_figure_label": ["interest"],
    },
    "heathridge-mortgage-interest-fy2025": {
        "any_of": ["mortgage interest", "interest statement", "interest charged",
                   "tax statement", "loan tax", "annual interest"],
        "not_any_of": ["repayment screenshot", "balance only"],
        "requires_figure_label": ["interest"],
    },
    # ---------- Waggrakine property management ----------
    "waggrakine-property-mgr-fy2024": {
        "any_of": ["property manager", "property management", "rental statement",
                   "rental income and expense", "end of financial year rental",
                   "annual rental", "managing agent"],
        "not_any_of": ["lease agreement", "single receipt", "tenancy agreement"],
    },
    "waggrakine-property-mgr-fy2025": {
        "any_of": ["property manager", "property management", "rental statement",
                   "rental income and expense", "end of financial year rental",
                   "annual rental", "managing agent"],
        "not_any_of": ["lease agreement", "single receipt", "tenancy agreement"],
    },
    # ---------- Waggrakine mortgage interest ----------
    "waggrakine-mortgage-interest-fy2024": {
        "any_of": ["mortgage interest", "interest statement", "interest charged",
                   "tax statement", "annual interest"],
        "not_any_of": ["repayment screenshot", "balance only"],
        "requires_figure_label": ["interest"],
    },
    "waggrakine-mortgage-interest-fy2025": {
        "any_of": ["mortgage interest", "interest statement", "interest charged",
                   "tax statement", "annual interest"],
        "not_any_of": ["repayment screenshot", "balance only"],
        "requires_figure_label": ["interest"],
    },
    # ---------- Revive financial statements ----------
    "revive-financials-fy2024": {
        "any_of": ["financial statements", "profit and loss", "p&l",
                   "balance sheet", "company accounts"],
        "not_any_of": ["receipt", "asic", "invoice"],
    },
    "revive-financials-fy2025": {
        "any_of": ["financial statements", "profit and loss", "p&l",
                   "balance sheet", "company accounts"],
        "not_any_of": ["receipt", "asic", "invoice"],
    },
    # ---------- Maxxia annual summary ----------
    "maxxia-annual-fy2024": {
        "any_of": ["maxxia annual", "salary packaging summary", "salary packaging report",
                   "reportable fringe benefits", "packaging statement", "novated lease summary"],
        "not_any_of": ["payslip", "single deposit", "email only"],
    },
    "maxxia-annual-fy2025": {
        "any_of": ["maxxia annual", "salary packaging summary", "salary packaging report",
                   "reportable fringe benefits", "packaging statement", "novated lease summary"],
        "not_any_of": ["payslip", "single deposit", "email only"],
    },
    # ---------- Personal bank statements ----------
    "personal-bank-fy2024": {
        "any_of": ["bank statement", "credit card statement", "statement period"],
        "not_any_of": ["airbnb", "revive", "drip hydration"],
    },
    "personal-bank-fy2025": {
        "any_of": ["bank statement", "credit card statement", "statement period"],
        "not_any_of": ["airbnb", "revive", "drip hydration"],
    },
    # ---------- Revive bank statements ----------
    "revive-bank-fy2024": {
        "any_of": ["bank statement", "credit card statement", "statement period"],
        "requires_text": ["revive", "drip hydration"],
    },
    "revive-bank-fy2025": {
        "any_of": ["bank statement", "credit card statement", "statement period"],
        "requires_text": ["revive", "drip hydration"],
    },
    # ---------- Heathridge council rates ----------
    "heathridge-council-fy2024": {
        "any_of": ["council rates", "rates notice"],
    },
    "heathridge-council-fy2025": {
        "any_of": ["council rates", "rates notice"],
    },
    # ---------- Heathridge insurance ----------
    "heathridge-insurance-fy2024": {
        "any_of": ["building insurance", "contents insurance", "home insurance",
                   "insurance policy", "insurance renewal"],
    },
    "heathridge-insurance-fy2025": {
        "any_of": ["building insurance", "contents insurance", "home insurance",
                   "insurance policy", "insurance renewal"],
    },
    # ---------- Waggrakine council rates ----------
    "waggrakine-council-fy2024": {
        "any_of": ["council rates", "rates notice"],
    },
    "waggrakine-council-fy2025": {
        "any_of": ["council rates", "rates notice"],
    },
    # ---------- Waggrakine landlord insurance ----------
    "waggrakine-landlord-fy2024": {
        "any_of": ["landlord insurance", "rental insurance"],
    },
    "waggrakine-landlord-fy2025": {
        "any_of": ["landlord insurance", "rental insurance"],
    },
    # ---------- Heathridge utilities ----------
    "heathridge-utilities-fy2024": {
        "any_of": ["water bill", "electricity bill", "gas bill", "internet bill",
                   "utility statement", "water invoice"],
    },
    "heathridge-utilities-fy2025": {
        "any_of": ["water bill", "electricity bill", "gas bill", "internet bill",
                   "utility statement", "water invoice"],
    },
    # ---------- Airbnb cleaning/supplies ----------
    "airbnb-supplies-both": {
        "any_of": ["cleaning receipt", "linen", "toiletries", "guest supplies",
                   "cleaning invoice", "housekeeping"],
    },
    # ---------- Later ----------
    "work-expense-both": {
        "any_of": ["work expense", "uniform", "professional development",
                   "tools receipt", "work-related"],
    },
    "home-office-both": {
        "any_of": ["home office", "office supplies", "stationery"],
    },
    "car-logbook-both": {
        "any_of": ["logbook", "car expenses", "fuel receipt", "kilometre"],
    },
}


# ---------------------------------------------------------------------------
# Initial seed list
# ---------------------------------------------------------------------------
INITIAL_MISSING_EVIDENCE: list[dict[str, Any]] = [
    # ---------- Critical ----------
    {"id": "airbnb-income-fy2024", "item_description": "FY2024 Airbnb income evidence — 9 Flotilla Drive Heathridge",
     "category": "03 Airbnb", "tax_year": "FY2024", "priority": "Critical",
     "notes": "Need payout schedule, transaction export, or earnings report covering 1 Jul 2023 – 30 Jun 2024."},
    {"id": "airbnb-income-fy2025", "item_description": "FY2025 Airbnb income evidence — 9 Flotilla Drive Heathridge",
     "category": "03 Airbnb", "tax_year": "FY2025", "priority": "Critical",
     "notes": "Need payout schedule, transaction export, or earnings report covering 1 Jul 2024 – 30 Jun 2025."},
    {"id": "heathridge-mortgage-interest-fy2024", "item_description": "Heathridge mortgage interest statement FY2024",
     "category": "05 Heathridge", "tax_year": "FY2024", "priority": "Critical",
     "notes": "Need lender statement showing interest component for 1 Jul 2023 – 30 Jun 2024."},
    {"id": "heathridge-mortgage-interest-fy2025", "item_description": "Heathridge mortgage interest statement FY2025",
     "category": "05 Heathridge", "tax_year": "FY2025", "priority": "Critical",
     "notes": "Need lender statement showing interest component for 1 Jul 2024 – 30 Jun 2025."},
    {"id": "waggrakine-property-mgr-fy2024", "item_description": "Waggrakine property management annual statement FY2024",
     "category": "04 Waggrakine Rental", "tax_year": "FY2024", "priority": "Critical",
     "notes": "Annual statement from property manager showing rent received and expenses."},
    {"id": "waggrakine-property-mgr-fy2025", "item_description": "Waggrakine property management annual statement FY2025",
     "category": "04 Waggrakine Rental", "tax_year": "FY2025", "priority": "Critical",
     "notes": "Annual statement from property manager showing rent received and expenses."},
    {"id": "waggrakine-mortgage-interest-fy2024", "item_description": "Waggrakine mortgage interest statement FY2024",
     "category": "04 Waggrakine Rental", "tax_year": "FY2024", "priority": "Critical",
     "notes": "Lender statement showing interest component."},
    {"id": "waggrakine-mortgage-interest-fy2025", "item_description": "Waggrakine mortgage interest statement FY2025",
     "category": "04 Waggrakine Rental", "tax_year": "FY2025", "priority": "Critical",
     "notes": "Lender statement showing interest component."},
    {"id": "revive-financials-fy2024", "item_description": "Revive Drip Hydration financial statements FY2024",
     "category": "06 Revive", "tax_year": "FY2024", "priority": "Critical",
     "notes": "Company financial statements, profit and loss, balance sheet, or accountant-prepared figures."},
    {"id": "revive-financials-fy2025", "item_description": "Revive Drip Hydration financial statements FY2025",
     "category": "06 Revive", "tax_year": "FY2025", "priority": "Critical",
     "notes": "Company financial statements, profit and loss, balance sheet, or accountant-prepared figures."},
    {"id": "maxxia-annual-fy2024", "item_description": "Maxxia annual summary FY2024",
     "category": "08 Salary Packaging Maxxia", "tax_year": "FY2024", "priority": "Critical",
     "notes": "Annual salary packaging summary showing reportable fringe benefits and packaged amounts."},
    {"id": "maxxia-annual-fy2025", "item_description": "Maxxia annual summary FY2025",
     "category": "08 Salary Packaging Maxxia", "tax_year": "FY2025", "priority": "Critical",
     "notes": "Annual salary packaging summary showing reportable fringe benefits and packaged amounts."},
    {"id": "personal-bank-fy2024", "item_description": "Personal bank statements FY2024",
     "category": "07 Bank Statements", "tax_year": "FY2024", "priority": "Critical",
     "notes": "All personal bank and credit card statements for 1 Jul 2023 – 30 Jun 2024."},
    {"id": "personal-bank-fy2025", "item_description": "Personal bank statements FY2025",
     "category": "07 Bank Statements", "tax_year": "FY2025", "priority": "Critical",
     "notes": "All personal bank and credit card statements for 1 Jul 2024 – 30 Jun 2025."},
    {"id": "revive-bank-fy2024", "item_description": "Revive bank statements FY2024",
     "category": "06 Revive", "tax_year": "FY2024", "priority": "Critical",
     "notes": "Company bank statements for Revive Drip Hydration."},
    {"id": "revive-bank-fy2025", "item_description": "Revive bank statements FY2025",
     "category": "06 Revive", "tax_year": "FY2025", "priority": "Critical",
     "notes": "Company bank statements for Revive Drip Hydration."},
    # ---------- Important ----------
    {"id": "heathridge-council-fy2024", "item_description": "Heathridge council rates FY2024",
     "category": "05 Heathridge", "tax_year": "FY2024", "priority": "Important",
     "notes": "Council rates for apportionment."},
    {"id": "heathridge-council-fy2025", "item_description": "Heathridge council rates FY2025",
     "category": "05 Heathridge", "tax_year": "FY2025", "priority": "Important",
     "notes": "Council rates for apportionment."},
    {"id": "heathridge-insurance-fy2024", "item_description": "Heathridge insurance FY2024",
     "category": "05 Heathridge", "tax_year": "FY2024", "priority": "Important",
     "notes": "Building/contents insurance for rental/Airbnb apportionment."},
    {"id": "heathridge-insurance-fy2025", "item_description": "Heathridge insurance FY2025",
     "category": "05 Heathridge", "tax_year": "FY2025", "priority": "Important",
     "notes": "Building/contents insurance for rental/Airbnb apportionment."},
    {"id": "waggrakine-council-fy2024", "item_description": "Waggrakine council rates FY2024",
     "category": "04 Waggrakine Rental", "tax_year": "FY2024", "priority": "Important",
     "notes": "Council rates."},
    {"id": "waggrakine-council-fy2025", "item_description": "Waggrakine council rates FY2025",
     "category": "04 Waggrakine Rental", "tax_year": "FY2025", "priority": "Important",
     "notes": "Council rates."},
    {"id": "waggrakine-landlord-fy2024", "item_description": "Waggrakine landlord insurance FY2024",
     "category": "04 Waggrakine Rental", "tax_year": "FY2024", "priority": "Important",
     "notes": "Landlord insurance."},
    {"id": "waggrakine-landlord-fy2025", "item_description": "Waggrakine landlord insurance FY2025",
     "category": "04 Waggrakine Rental", "tax_year": "FY2025", "priority": "Important",
     "notes": "Landlord insurance."},
    {"id": "heathridge-utilities-fy2024", "item_description": "Heathridge utilities FY2024",
     "category": "05 Heathridge", "tax_year": "FY2024", "priority": "Important",
     "notes": "Water, power, gas, internet for Airbnb/rental apportionment."},
    {"id": "heathridge-utilities-fy2025", "item_description": "Heathridge utilities FY2025",
     "category": "05 Heathridge", "tax_year": "FY2025", "priority": "Important",
     "notes": "Water, power, gas, internet for Airbnb/rental apportionment."},
    {"id": "airbnb-supplies-both", "item_description": "Airbnb cleaning/supplies receipts",
     "category": "03 Airbnb", "tax_year": "Both", "priority": "Important",
     "notes": "Cleaning, linen, toiletries, guest supplies."},
    # ---------- Later ----------
    {"id": "work-expense-both", "item_description": "Work-related expense receipts",
     "category": "09 Accountant Review", "tax_year": "Both", "priority": "Later",
     "notes": "Tools, uniforms, professional development. Only material if claiming."},
    {"id": "home-office-both", "item_description": "Home office evidence",
     "category": "09 Accountant Review", "tax_year": "Both", "priority": "Later",
     "notes": "Only needed if claiming home office expenses."},
    {"id": "car-logbook-both", "item_description": "Car logbook or kilometre estimate",
     "category": "09 Accountant Review", "tax_year": "Both", "priority": "Later",
     "notes": "Only needed if claiming car expenses."},
]


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------
async def seed_missing_evidence(db) -> dict[str, int]:
    """Idempotently seed the canonical checklist.
    - Upserts by stable string `id`.
    - Never overwrites manually changed status / matched_* fields.
    - Returns counts of inserted/updated.
    """
    start = time.time()
    inserted = 0
    refreshed = 0
    for spec in INITIAL_MISSING_EVIDENCE:
        existing = await db.missing_items.find_one({"id": spec["id"]}, {"_id": 0})
        if existing:
            # Refresh the canonical fields ONLY (description, category, tax_year,
            # priority, notes) but never touch status/matched_*.
            await db.missing_items.update_one(
                {"id": spec["id"]},
                {"$set": {
                    "item_description": spec["item_description"],
                    "item_needed": spec["item_description"],
                    "category": spec["category"],
                    "tax_year": spec["tax_year"],
                    "priority": spec["priority"],
                    "notes": spec["notes"],
                    "updated_at": utc_now_iso(),
                }},
            )
            refreshed += 1
        else:
            await db.missing_items.insert_one({
                **spec,
                "item_needed": spec["item_description"],
                "status": "Outstanding",
                "matched_document_id": None,
                "matched_document_name": None,
                "match_confidence": None,
                "match_reason": None,
                "where_to_find": "",
                "why_matters": "",
                "created_at": utc_now_iso(),
                "updated_at": utc_now_iso(),
            })
            inserted += 1
    # Also clear any pre-existing legacy items that aren't in the canonical list,
    # but ONLY if they look like the old seed (i.e. no stable id starting with the
    # canonical slug prefix and status is still Outstanding/Not started).
    canonical_ids = {s["id"] for s in INITIAL_MISSING_EVIDENCE}
    legacy = await db.missing_items.find({"id": {"$nin": list(canonical_ids)}}, {"_id": 0, "id": 1, "status": 1}).to_list(2000)
    removed = 0
    for it in legacy:
        if (it.get("status") or "Outstanding") in ("Outstanding", "Not started"):
            await db.missing_items.delete_one({"id": it["id"]})
            removed += 1
    return {"inserted": inserted, "refreshed": refreshed, "removed_legacy": removed, "elapsed_ms": int((time.time() - start) * 1000)}


# ---------------------------------------------------------------------------
# Match
# ---------------------------------------------------------------------------
def _blob(ai_result: dict, document_filename: str) -> str:
    parts = [
        document_filename or "",
        (ai_result.get("document_type") or ""),
        (ai_result.get("one_line_summary") or ""),
        (ai_result.get("suggested_filename") or ""),
        (ai_result.get("counterparty") or ""),
    ]
    return " | ".join(p for p in parts if p).lower()


def _figure_labels(ai_result: dict) -> list[str]:
    return [str(f.get("label") or "").lower() for f in (ai_result.get("headline_figures_json") or ai_result.get("headline_figures") or [])]


def _tax_year_compatible(item_year: str, doc_year: str) -> bool:
    if item_year == "Both":
        return doc_year in ("FY2024", "FY2025", "FY2026", "Both")
    if doc_year == "Both":
        return True
    return item_year == doc_year


async def check_and_update_missing_evidence(db, document_id: str, ai_result: dict) -> dict:
    """After a document is filed, scan the checklist and (carefully) mark
    items as Received or Possible Match. NEVER changes a Received item.
    Returns a summary of what changed."""
    if not ai_result:
        return {"checked": 0, "received": [], "possible": []}

    doc_category = ai_result.get("category") or ""
    doc_year = ai_result.get("tax_year") or "Unsure"
    cat_conf = ai_result.get("category_confidence") or "Unsure"
    year_conf = ai_result.get("tax_year_confidence") or "Unsure"
    document_filename = (ai_result.get("original_filename")
                         or ai_result.get("suggested_filename")
                         or ai_result.get("name") or "")

    blob = _blob(ai_result, document_filename)
    fig_labels_blob = " ".join(_figure_labels(ai_result))

    items = await db.missing_items.find({}, {"_id": 0}).to_list(2000)
    received_changes: list[str] = []
    possible_changes: list[str] = []
    checked = 0

    for item in items:
        # Stage 4.5: never auto-overwrite a row a human has touched (unless
        # they reset to Outstanding, which is the explicit re-evaluation
        # signal). Auto-matched rows have status_source="system" and remain
        # eligible.
        manual = (item.get("status_source") == "user")
        if manual:
            continue
        if item.get("status") in ("Received", "Not applicable", "Accountant Review"):
            # Never auto-downgrade or overwrite explicit user states.
            continue
        if item.get("category") != doc_category:
            continue
        if not _tax_year_compatible(item.get("tax_year", "Unsure"), doc_year):
            continue
        rule = MATCH_RULES.get(item["id"])
        if not rule:
            continue
        checked += 1
        any_of_hit = any(k in blob for k in rule.get("any_of", []))
        not_any_of_hit = any(k in blob for k in rule.get("not_any_of", []))
        requires_text_ok = True
        if rule.get("requires_text"):
            requires_text_ok = any(k in blob for k in rule["requires_text"])
        figure_ok = True
        if rule.get("requires_figure_label"):
            figure_ok = any(k in fig_labels_blob for k in rule["requires_figure_label"])

        if not_any_of_hit or not requires_text_ok:
            continue
        if not any_of_hit:
            continue

        # Decide Received vs Possible Match
        strong_confidence = cat_conf in ("Confirmed", "Likely") and year_conf in ("Confirmed", "Likely")
        if any_of_hit and figure_ok and strong_confidence:
            confidence = "Confirmed" if (cat_conf == "Confirmed" and year_conf == "Confirmed") else "Likely"
            reason_parts = [f"document classified as {doc_category} for {doc_year} with {cat_conf}/{year_conf} confidence"]
            if rule.get("requires_figure_label"):
                reason_parts.append(f"headline figures include {rule['requires_figure_label'][0]}")
            await db.missing_items.update_one(
                {"id": item["id"]},
                {"$set": {
                    "status": "Received",
                    "matched_document_id": document_id,
                    "matched_document_name": document_filename,
                    "match_confidence": confidence,
                    "match_reason": "; ".join(reason_parts),
                    "status_source": "system",
                    "status_updated_at": utc_now_iso(),
                    "updated_at": utc_now_iso(),
                }},
            )
            received_changes.append(item["id"])
        else:
            # Possible match — keyword hit but confidence low or figure missing
            reasons = []
            if not strong_confidence:
                reasons.append(f"low classifier confidence (category {cat_conf}, tax-year {year_conf})")
            if rule.get("requires_figure_label") and not figure_ok:
                reasons.append(f"expected figure label not extracted ({rule['requires_figure_label'][0]})")
            if not reasons:
                reasons.append("keyword match without strong corroboration")
            await db.missing_items.update_one(
                {"id": item["id"]},
                {"$set": {
                    "status": "Possible Match",
                    "matched_document_id": document_id,
                    "matched_document_name": document_filename,
                    "match_confidence": "Unsure",
                    "match_reason": "; ".join(reasons),
                    "status_source": "system",
                    "status_updated_at": utc_now_iso(),
                    "updated_at": utc_now_iso(),
                }},
            )
            possible_changes.append(item["id"])

    return {
        "checked": checked,
        "received": received_changes,
        "possible": possible_changes,
        "document_id": document_id,
    }


# ---------------------------------------------------------------------------
# Next best document
# ---------------------------------------------------------------------------
_PRIORITY_RANK = {"Critical": 0, "Important": 1, "Later": 2}
_YEAR_RANK = {"FY2024": 0, "FY2025": 0, "FY2026": 1, "Both": 2, "Historical": 3, "Unsure": 4}

# A coarse "what kind of evidence" ranking — income proof before interest,
# property/business before minor deductions.
_KIND_RANK_PATTERNS = [
    (re.compile(r"income|payout|earnings|rental statement|property management"), 0),
    (re.compile(r"mortgage interest"), 1),
    (re.compile(r"financial statement|profit|p&l|balance sheet"), 1),
    (re.compile(r"bank statement"), 1),
    (re.compile(r"annual summary|salary packaging|maxxia"), 1),
    (re.compile(r"council rates|landlord insurance|insurance"), 2),
    (re.compile(r"utilities|water|electricity|gas"), 3),
    (re.compile(r"work-related|home office|car logbook|cleaning|supplies"), 4),
]


def _kind_rank(text: str) -> int:
    t = (text or "").lower()
    for pat, rank in _KIND_RANK_PATTERNS:
        if pat.search(t):
            return rank
    return 99


async def get_next_best_document(db) -> Optional[dict]:
    items = await db.missing_items.find({"status": "Outstanding"}, {"_id": 0}).to_list(2000)
    if not items:
        return None
    items.sort(key=lambda it: (
        _PRIORITY_RANK.get(it.get("priority", "Later"), 99),
        _YEAR_RANK.get(it.get("tax_year", "Unsure"), 99),
        _kind_rank(it.get("item_description", "")),
        it.get("created_at", ""),
    ))
    return items[0]
