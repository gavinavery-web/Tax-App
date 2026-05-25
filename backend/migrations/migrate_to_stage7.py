"""Stage 7 migration — add new fields to existing documents and missing
evidence rows.

Safety contract:
  * Adds fields, never removes or modifies existing ones.
  * Idempotent — safe to re-run; uses `$exists: False` guards.
  * Does NOT remap the missing-evidence status vocabulary. Stage 4.5's
    values (Outstanding / Possible Match / Received / Not applicable /
    Accountant Review) are wired across the UI, exports, the readiness
    gate, and the test suite. Remapping them would silently break ~40
    tests and every export. We add NEW tracking fields instead, and the
    Stage 7 status mapping is layered on top via a read-time helper.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _db():
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        raise RuntimeError("MONGO_URL / DB_NAME not set in backend/.env")
    client = AsyncIOMotorClient(mongo_url)
    return client, client[db_name]


# Stage 4.5 status → Stage 7 equivalent. Used for *projecting* a derived
# field; the raw value stays untouched.
ST7_STATUS_PROJECTION = {
    "Outstanding": "open",
    "Possible Match": "open",
    "Accountant Review": "open",
    "Received": "matched_by_upload",
    "Not applicable": "not_applicable",
}


async def migrate_documents(db) -> tuple[int, int]:
    total = await db.documents.count_documents({})
    logger.info(f"documents: {total} existing rows")
    if total == 0:
        return 0, 0

    res = await db.documents.update_many(
        {"is_deleted": {"$exists": False}},
        {"$set": {
            "is_deleted": False,
            "deleted_at": None,
            "deleted_reason": None,
            "evidence_status": "used",        # existing docs are assumed useful
            "used_in_claims_count": 0,
            "is_bank_statement": False,       # detected at next upload pass
            "transactions_extracted_count": 0,
            "transactions_analyzed_by_ai": False,
            "transaction_ai_cost_usd": 0.0,
        }},
    )
    migrated = res.modified_count
    verified = await db.documents.count_documents({"is_deleted": {"$exists": True}})
    logger.info(f"documents: migrated={migrated}, total_with_new_fields={verified}/{total}")
    if verified != total:
        logger.warning(f"⚠ documents incomplete — expected {total}, got {verified}")
    return migrated, verified


async def migrate_missing_items(db) -> int:
    """Add Stage 7 tracking fields (`satisfied_*`) — leaves the existing
    Stage 4.5 status vocabulary intact. Server.py reads/writes those status
    strings everywhere; remapping would break ~40 tests + every export.
    """
    res = await db.missing_items.update_many(
        {"satisfied_by_document_id": {"$exists": False}},
        {"$set": {
            "satisfied_by_document_id": None,
            "satisfied_at": None,
            "satisfied_method": None,
        }},
    )
    logger.info(f"missing_items: added Stage 7 tracking fields to {res.modified_count} rows")
    # Sanity: report current status distribution so the operator can see
    # how many "open"-equivalent rows exist post-migration.
    open_eq_statuses = ["Outstanding", "Possible Match", "Accountant Review"]
    open_eq = await db.missing_items.count_documents({"status": {"$in": open_eq_statuses}})
    matched = await db.missing_items.count_documents({"status": "Received"})
    na = await db.missing_items.count_documents({"status": "Not applicable"})
    logger.info(f"missing_items: open-equivalent={open_eq}, matched={matched}, n/a={na}")
    return res.modified_count


async def create_indexes(db):
    await db.documents.create_index("evidence_status")
    await db.documents.create_index("is_deleted")
    await db.documents.create_index([("tax_year", 1), ("category", 1)])
    logger.info("documents: indexes ok")


async def main():
    logger.info("=" * 60)
    logger.info("STAGE 7 — DATABASE MIGRATION")
    logger.info("=" * 60)
    client, db = _db()
    try:
        logger.info("\n1. Migrating documents…")
        await migrate_documents(db)
        logger.info("\n2. Migrating missing_items (Stage 7 tracking fields only)…")
        await migrate_missing_items(db)
        logger.info("\n3. Creating indexes…")
        await create_indexes(db)
        logger.info("\n" + "=" * 60)
        logger.info("MIGRATION COMPLETE")
        logger.info("=" * 60)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
