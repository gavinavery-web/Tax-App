"""Read profile_questions.json and evidence_rules.json. Generate missing
evidence items based on a profile_answers dict. Idempotent.
"""
from __future__ import annotations
import json
import logging
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).parent
_QUESTIONS_CACHE: Optional[dict] = None
_RULES_CACHE: Optional[dict] = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_questions() -> dict:
    global _QUESTIONS_CACHE
    if _QUESTIONS_CACHE is None:
        with open(_ROOT / "profile_questions.json", "r", encoding="utf-8") as f:
            _QUESTIONS_CACHE = json.load(f)
    return _QUESTIONS_CACHE


def load_rules() -> dict:
    global _RULES_CACHE
    if _RULES_CACHE is None:
        with open(_ROOT / "evidence_rules.json", "r", encoding="utf-8") as f:
            _RULES_CACHE = json.load(f)
    return _RULES_CACHE


def get_questions_for_return_type(return_type: str) -> dict:
    qs = load_questions()
    return qs.get(return_type, {"version": "0", "groups": []})


def _condition_matches(condition: dict, answers: dict) -> bool:
    """All keys in condition must match the answer exactly."""
    for k, v in condition.items():
        if answers.get(k) != v:
            return False
    return True


async def generate_missing_evidence(
    db,
    *,
    tax_return_id: str,
    return_type: str,
    tax_year: str,
    profile_answers: dict,
) -> dict:
    """Generate missing-evidence items based on profile answers.

    Idempotent: items are keyed by (tax_return_id, profile_rule_key, item).
    Re-running does not create duplicates. Never overwrites items where
    status_source == 'user'. Never deletes anything.
    """
    rules = load_rules().get(return_type, {}).get("rules", [])
    created, skipped_existing, skipped_user_managed = 0, 0, 0

    for rule in rules:
        if not _condition_matches(rule.get("if", {}), profile_answers):
            continue

        for item_template in rule.get("items", []):
            uniqueness = {
                "tax_return_id": tax_return_id,
                "profile_rule_key": rule["rule_key"],
                "item_needed": item_template["item"],
            }
            existing = await db.missing_items.find_one(uniqueness, {"_id": 0})
            if existing:
                if existing.get("status_source") == "user":
                    skipped_user_managed += 1
                else:
                    skipped_existing += 1
                continue

            new_item = {
                "id": str(uuid.uuid4()),
                "item_needed": item_template["item"],
                "category": item_template["category"],
                "tax_year": tax_year,
                "priority": item_template["priority"],
                "where_to_find": item_template.get("where", ""),
                "why_matters": item_template.get("why", ""),
                "status": "Outstanding",
                "notes": "",
                "tax_return_id": tax_return_id,
                "generated_by": "profile",
                "profile_rule_key": rule["rule_key"],
                "created_at": utc_now_iso(),
            }
            await db.missing_items.insert_one(new_item)
            created += 1

    return {
        "created": created,
        "skipped_existing": skipped_existing,
        "skipped_user_managed": skipped_user_managed,
    }
