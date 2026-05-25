"""Stage 7 Phase 3 — Deletion Manager.

Soft delete (rubbish bin) + permanent delete with safety checks.

ID convention: the documents collection uses string `id` (not Mongo `_id`).
All filters here use `{"id": doc_id}` to match `server.py` and the rest of
the codebase.

Drive contract:
  - Soft delete leaves Drive file alone (recoverable).
  - Permanent delete removes the DB row and the local staging file.
    It does NOT delete the Drive file — that's the user's authoritative
    copy and must survive a deletion mistake. (Existing
    `DELETE /api/documents/{doc_id}` in server.py is a separate hard-
    delete that *does* purge Drive; that endpoint is untouched.)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Dict

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def soft_delete_document(
    db, document_id: str, reason: str, user: str = "user",
) -> bool:
    """Set is_deleted=True. Preserves DB record + Drive file + local file."""
    now = _utc_now_iso()
    res = await db.documents.update_one(
        {"id": document_id},
        {"$set": {
            "is_deleted": True,
            "deleted_at": now,
            "deleted_reason": reason,
            "deleted_by_user": user,
            "updated_at": now,
        }},
    )
    if res.modified_count > 0:
        logger.info(f"soft-deleted document {document_id}: {reason}")
    return res.modified_count > 0


async def restore_document(db, document_id: str) -> bool:
    """Restore a soft-deleted document."""
    now = _utc_now_iso()
    res = await db.documents.update_one(
        {"id": document_id, "is_deleted": True},
        {"$set": {
            "is_deleted": False,
            "deleted_at": None,
            "deleted_reason": None,
            "deleted_by_user": None,
            "updated_at": now,
        }},
    )
    if res.modified_count > 0:
        logger.info(f"restored document {document_id}")
    return res.modified_count > 0


async def permanent_delete_document(
    db, document_id: str, user: str = "user",
) -> Dict:
    """Permanently remove a soft-deleted document.

    Safety checks:
      1. Must already be in the rubbish bin (`is_deleted=True`).
      2. Must not be referenced by any tax_return_item
         (used_in_claims_count == 0).
      3. Local staging file is removed if present. Drive file is NOT
         touched (user's authoritative copy).
    """
    doc = await db.documents.find_one({"id": document_id}, {"_id": 0})
    if not doc:
        return {"success": False, "error": "Document not found"}

    if not doc.get("is_deleted"):
        return {"success": False, "error": "Document must be in rubbish bin first"}

    used_count = int(doc.get("used_in_claims_count") or 0)
    if used_count > 0:
        return {
            "success": False,
            "error": f"Cannot delete: document is referenced in {used_count} tax claim(s)",
        }

    # Cross-check against tax_return_items — defensive belt-and-braces.
    # `used_in_claims_count` is maintained atomically by
    # tax_return_builder.increment_document_usage, but a stale row would
    # silently allow data loss otherwise.
    live_claims = await db.tax_return_items.count_documents(
        {"source_document_id": document_id, "evidence_status": {"$ne": "excluded"}},
    )
    if live_claims > 0:
        return {
            "success": False,
            "error": f"Cannot delete: {live_claims} tax claim(s) still reference this document",
        }

    # Best-effort local file cleanup. Drive file is intentionally left alone.
    local_path = doc.get("local_path")
    if local_path:
        try:
            if os.path.exists(local_path):
                os.remove(local_path)
                logger.info(f"deleted local file: {local_path}")
        except Exception as e:
            logger.warning(f"local file cleanup failed for {local_path}: {e}")

    # Also clear any manual figures tied to this doc so they don't dangle.
    await db.figures.delete_many({"document_id": document_id})
    await db.documents.delete_one({"id": document_id})
    logger.info(f"permanently deleted document {document_id} (user={user})")
    return {"success": True}
