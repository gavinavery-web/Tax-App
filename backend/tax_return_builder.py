"""Stage 7 Phase 3 — Tax Return Builder.

Creates `tax_return_items` rows from documents / bank transactions / manual
entries. Tracks source linking and atomically updates `used_in_claims_count`
on the source document so it can be soft-deleted safely.

ID convention: every row carries a string-uuid `id` (NOT Mongo `_id`).
Timestamps are ISO-8601 UTC strings (matching the rest of the codebase).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Tax-section normalisation: document category → ATO section key.
TAX_SECTION_MAPPING = {
    "PAYG Income": "salary_wages", "Salary and Wages": "salary_wages",
    "Employment Income": "salary_wages", "Allowances": "allowances",
    "Interest Income": "interest", "Dividend Income": "dividends",
    "Rental Income": "rental_income",
    "Work Car": "work_related_car", "Work-Related Car": "work_related_car",
    "Car Expenses": "work_related_car", "Work Travel": "work_related_travel",
    "Tools": "tools_equipment", "Tools and Equipment": "tools_equipment",
    "Union Fees": "union_fees", "Professional Fees": "union_fees",
    "Donations": "donations", "Gifts": "donations",
    "Rental Property": "rental_deductions", "Rental Expenses": "rental_deductions",
}


def _determine_tax_year(transaction_date_str: str) -> str:
    """Australian FY: July → June. Returns 'Unsure' for un-parseable dates
    or anything outside the in-scope FY2024 / FY2025 window."""
    try:
        d = datetime.fromisoformat(transaction_date_str)
    except (ValueError, TypeError):
        return "Unsure"
    fy = f"FY{d.year + 1}" if d.month >= 7 else f"FY{d.year}"
    return fy if fy in ("FY2024", "FY2025") else "Unsure"


async def increment_document_usage(db, document_id: str, delta: int) -> None:
    """Atomically nudge `used_in_claims_count` on the document. Sets
    `evidence_status` to "used" or "unused" based on the new count."""
    res = await db.documents.find_one_and_update(
        {"id": document_id},
        {"$inc": {"used_in_claims_count": delta},
         "$set": {"updated_at": _utc_now_iso()}},
        return_document=True,
    )
    if not res:
        return
    new_count = res.get("used_in_claims_count", 0)
    new_status = "used" if new_count > 0 else "unused"
    await db.documents.update_one(
        {"id": document_id},
        {"$set": {"evidence_status": new_status}},
    )


async def create_tax_return_item_from_document(
    db, document: Dict, amount_cents: int, description: str, income_or_deduction: str,
) -> str:
    section = TAX_SECTION_MAPPING.get(document.get("category", "Other"), "other_deductions")
    item_id = str(uuid.uuid4())
    now = _utc_now_iso()
    item = {
        "id": item_id,
        "tax_year": document.get("tax_year", "Unsure"),
        "section": section,
        "category": document.get("category", "Other"),
        "description": description,
        "amount_cents": amount_cents,
        "income_or_deduction": income_or_deduction,
        "source_type": "document",
        "source_document_id": document["id"],
        "source_filename": document.get("name") or document.get("original_filename"),
        "source_drive_link": document.get("drive_link"),
        "source_quote": None,
        "confidence": document.get("category_confidence", "Unsure"),
        "risk_level": "Amber",
        "accountant_review_required": document.get("accountant_review") == "Yes" or bool(document.get("accountant_review_required")),
        "evidence_status": "used",
        "user_confirmed": False,
        "manual_override": False,
        "ai_cost_usd": 0.0,
        "created_at": now, "updated_at": now,
    }
    await db.tax_return_items.insert_one(item)
    await increment_document_usage(db, document["id"], delta=1)
    logger.info(f"tax item from doc {document.get('id')}: {description}")
    return item_id


async def create_tax_return_item_from_transaction(db, transaction: Dict) -> Optional[str]:
    """Only emits a claim when the transaction is Confirmed/Likely AND not
    flagged as private spending."""
    if transaction.get("confidence") not in ("Confirmed", "Likely"):
        return None
    if transaction.get("evidence_status") == "private":
        return None
    item_id = str(uuid.uuid4())
    now = _utc_now_iso()
    item = {
        "id": item_id,
        "tax_year": _determine_tax_year(transaction["transaction_date"]),
        "section": transaction.get("tax_section_suggested") or "other_deductions",
        "category": transaction.get("category_suggested") or "Other",
        "description": transaction["description_cleaned"],
        "amount_cents": transaction["amount_cents"],
        "income_or_deduction": "deduction",
        "source_type": "bank_transaction",
        "source_document_id": transaction["source_document_id"],
        "source_bank_transaction_id": transaction["id"],
        "source_filename": transaction.get("source_filename"),
        "source_quote": transaction.get("description_raw"),
        "property_id": transaction.get("property_match"),
        "property_use_period": transaction.get("use_period_match"),
        "confidence": transaction.get("confidence", "Unsure"),
        "risk_level": "Amber" if transaction.get("review_required") else "Green",
        "accountant_review_required": bool(transaction.get("review_required")),
        "review_reason": transaction.get("review_reason"),
        "evidence_status": "used",
        "user_confirmed": bool(transaction.get("user_confirmed")),
        "manual_override": False,
        "ai_cost_usd": float(transaction.get("ai_cost_usd") or 0.0),
        "created_at": now, "updated_at": now,
    }
    await db.tax_return_items.insert_one(item)
    await db.bank_transactions.update_one(
        {"id": transaction["id"]},
        {"$set": {"used_in_return": True, "updated_at": now}},
    )
    await increment_document_usage(db, transaction["source_document_id"], delta=1)
    return item_id


async def create_manual_tax_return_item(
    db, *, tax_year: str, section: str, amount_cents: int, description: str,
    income_or_deduction: str, source_document_id: Optional[str] = None, notes: str = "",
) -> str:
    item_id = str(uuid.uuid4())
    now = _utc_now_iso()
    item = {
        "id": item_id,
        "tax_year": tax_year, "section": section,
        "category": "Manual Entry",
        "description": description, "amount_cents": amount_cents,
        "income_or_deduction": income_or_deduction,
        "source_type": "manual_entry",
        "source_document_id": source_document_id,
        "source_filename": None,
        "confidence": "Confirmed", "risk_level": "Green",
        "accountant_review_required": False,
        "evidence_status": "used",
        "user_confirmed": True,
        "manual_override": True,
        "user_notes": notes,
        "ai_cost_usd": 0.0,
        "created_at": now, "updated_at": now,
    }
    await db.tax_return_items.insert_one(item)
    if source_document_id:
        await increment_document_usage(db, source_document_id, delta=1)
    return item_id


async def get_tax_year_summary(db, tax_year: str) -> Dict:
    """Aggregate items into sections, totals, and review counts."""
    items = await db.tax_return_items.find(
        {"tax_year": tax_year, "evidence_status": {"$ne": "excluded"}},
        {"_id": 0},
    ).to_list(5000)
    sections: dict[str, dict] = {}
    total_income = 0
    total_deductions = 0
    for it in items:
        sec = it.get("section") or "other_deductions"
        s = sections.setdefault(sec, {
            "section_name": sec,
            "total_amount_cents": 0,
            "item_count": 0,
            "review_required_count": 0,
            "items": [],
        })
        s["total_amount_cents"] += it.get("amount_cents", 0)
        s["item_count"] += 1
        if it.get("accountant_review_required"):
            s["review_required_count"] += 1
        s["items"].append(it)
        if it.get("income_or_deduction") == "income":
            total_income += it.get("amount_cents", 0)
        elif it.get("income_or_deduction") == "deduction":
            total_deductions += it.get("amount_cents", 0)
    return {
        "tax_year": tax_year,
        "sections": list(sections.values()),
        "total_income_cents": total_income,
        "total_deductions_cents": total_deductions,
        "total_items": len(items),
        "total_review_required": sum(s["review_required_count"] for s in sections.values()),
    }
