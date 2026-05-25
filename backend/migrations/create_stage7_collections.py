"""Stage 7 — create new collections and seed default properties.

Safe to re-run (idempotent). Loads /app/backend/.env so the script works
both stand-alone and when invoked from the platform shell.

Collections created:
  - bank_transactions
  - tax_return_items
  - properties (seeded with Heathridge + Waggrakine)
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# Load backend .env so MONGO_URL / DB_NAME resolve when this is run as a
# stand-alone script (the FastAPI app does this for us at startup).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db():
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        raise RuntimeError("MONGO_URL / DB_NAME not set in backend/.env")
    client = AsyncIOMotorClient(mongo_url)
    return client, client[db_name]


async def create_bank_transactions(db):
    if "bank_transactions" not in await db.list_collection_names():
        await db.create_collection("bank_transactions")
        logger.info("created bank_transactions collection")
    else:
        logger.info("bank_transactions collection already exists")
    await db.bank_transactions.create_index("source_document_id")
    await db.bank_transactions.create_index("transaction_date")
    await db.bank_transactions.create_index("evidence_status")
    await db.bank_transactions.create_index("used_in_return")
    await db.bank_transactions.create_index([("bank_name", 1), ("account_number_masked", 1)])
    logger.info("indexes ok on bank_transactions")


async def create_tax_return_items(db):
    if "tax_return_items" not in await db.list_collection_names():
        await db.create_collection("tax_return_items")
        logger.info("created tax_return_items collection")
    else:
        logger.info("tax_return_items collection already exists")
    await db.tax_return_items.create_index("tax_year")
    await db.tax_return_items.create_index("section")
    await db.tax_return_items.create_index("evidence_status")
    await db.tax_return_items.create_index("source_document_id")
    await db.tax_return_items.create_index([("tax_year", 1), ("section", 1)])
    logger.info("indexes ok on tax_return_items")


async def create_properties(db):
    if "properties" not in await db.list_collection_names():
        await db.create_collection("properties")
        logger.info("created properties collection")
    else:
        logger.info("properties collection already exists")
    # `property_name` is the natural key — unique index. If the spec text
    # changes the address we still want one row per property.
    await db.properties.create_index("property_name", unique=True)
    logger.info("indexes ok on properties")


async def seed_default_properties(db):
    """Seed Heathridge + Waggrakine if no properties exist. Idempotent."""
    if await db.properties.count_documents({}) > 0:
        logger.info("properties already seeded — skipping")
        return
    now = _utc_now_iso()
    defaults = [
        {
            "id": "prop-heathridge",
            "property_name": "Heathridge",
            "address": "9 Flotilla Drive, Heathridge WA 6008",
            "use_periods": [],
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": "prop-waggrakine",
            "property_name": "Waggrakine",
            "address": "Waggrakine, WA",
            "use_periods": [],
            "created_at": now,
            "updated_at": now,
        },
    ]
    await db.properties.insert_many(defaults)
    logger.info(f"seeded {len(defaults)} default properties")


async def main():
    logger.info("=" * 60)
    logger.info("STAGE 7 — COLLECTION SETUP")
    logger.info("=" * 60)
    client, db = _db()
    try:
        await create_bank_transactions(db)
        await create_tax_return_items(db)
        await create_properties(db)
        await seed_default_properties(db)
        logger.info("=" * 60)
        logger.info("SETUP COMPLETE")
        logger.info("=" * 60)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
