"""Bulk upload pipeline — queue, background workers, dedup, AI orchestration.

Exposes a router that the main server mounts under /api.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query

from extraction import extract_text
from ai_classifier import classify_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Lazy module-level refs filled in by server.py via init_pipeline()
_db = None
_get_drive_service = None
_get_or_create_folders = None
_save_drive_credentials = None
_singleton_key = "default"

_app_storage_dir = Path(__file__).parent / "app_storage"
_app_storage_dir.mkdir(exist_ok=True)

# Concurrency
_AI_SEM: Optional[asyncio.Semaphore] = None
_DRIVE_SEM: Optional[asyncio.Semaphore] = None
_workers_started = False


def init_pipeline(*, db, get_drive_service, get_or_create_folders, singleton_key="default"):
    global _db, _get_drive_service, _get_or_create_folders, _singleton_key
    global _AI_SEM, _DRIVE_SEM
    _db = db
    _get_drive_service = get_drive_service
    _get_or_create_folders = get_or_create_folders
    _singleton_key = singleton_key
    _AI_SEM = asyncio.Semaphore(int(os.environ.get("AI_MAX_CONCURRENT", "3")))
    _DRIVE_SEM = asyncio.Semaphore(5)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


# Map AI category → drive folder. The Brain now returns the literal folder
# name (e.g. "02 PAYG Income"); we keep legacy short names as aliases.
CATEGORY_TO_FOLDER = {
    "00 Inbox": "00 Inbox",
    "01 ATO": "01 ATO",
    "02 PAYG Income": "02 PAYG Income",
    "03 Airbnb": "03 Airbnb",
    "04 Waggrakine Rental": "04 Waggrakine Rental",
    "05 Heathridge": "05 Heathridge",
    "06 Revive": "06 Revive",
    "07 Bank Statements": "07 Bank Statements",
    "08 Salary Packaging Maxxia": "08 Salary Packaging Maxxia",
    "09 Accountant Review": "09 Accountant Review",
    "10 Missing Evidence": "10 Missing Evidence",
    "11 Final Accountant Pack": "11 Final Accountant Pack",
    # Legacy short forms
    "ATO": "01 ATO",
    "PAYG Income": "02 PAYG Income",
    "Airbnb": "03 Airbnb",
    "Waggrakine Rental": "04 Waggrakine Rental",
    "Heathridge": "05 Heathridge",
    "Revive": "06 Revive",
    "Bank Statement": "07 Bank Statements",
    "Salary Packaging / Maxxia": "08 Salary Packaging Maxxia",
    "Super / HECS": "02 PAYG Income",
    "Accountant Review": "09 Accountant Review",
    "Other": "00 Inbox",
}
INBOX_FOLDER = "00 Inbox"


def _safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._\- ]+", "_", name)[:200]


# ---------- Endpoints --------------------------------------------------------

@router.post("/uploads/bulk")
async def bulk_upload(files: list[UploadFile] = File(...)):
    """Accept many files. Queues each, returns queue IDs. The background
    worker will process them concurrently (capped). Survives page navigation
    because state lives in MongoDB."""
    if not files:
        raise HTTPException(400, "No files provided")
    queue_ids: list[str] = []
    duplicates: list[dict] = []
    for f in files:
        content = await f.read()
        sha = sha256_bytes(content)
        # dedup check: existing document with same sha
        existing = await _db.documents.find_one({"sha256": sha}, {"_id": 0, "id": 1, "name": 1, "created_at": 1, "category": 1})
        # write content to a temp staging file
        staging = _app_storage_dir / f"_staging__{uuid.uuid4()}__{_safe_filename(f.filename or 'file')}"
        staging.write_bytes(content)
        qid = str(uuid.uuid4())
        await _db.upload_queue.insert_one({
            "id": qid,
            "filename": f.filename,
            "mime": f.content_type or "application/octet-stream",
            "size_bytes": len(content),
            "sha256": sha,
            "staging_path": str(staging),
            "status": "Duplicate?" if existing else "Queued",
            "duplicate_of": existing.get("id") if existing else None,
            "duplicate_meta": existing or None,
            "result_document_id": None,
            "ai_category": None,
            "ai_confidence": None,
            "ai_cost_usd": 0.0,
            "error": None,
            "queued_at": utc_now_iso(),
            "started_at": None,
            "completed_at": None,
        })
        queue_ids.append(qid)
        if existing:
            duplicates.append({"queue_id": qid, "filename": f.filename, "existing": existing})
    # nudge the worker
    asyncio.create_task(_run_worker())
    return {"queue_ids": queue_ids, "duplicates": duplicates}


@router.get("/uploads/queue")
async def list_queue():
    items = await _db.upload_queue.find({}, {"_id": 0}).sort("queued_at", -1).to_list(2000)
    counts = {"Queued": 0, "Uploading": 0, "Reading": 0, "Classifying": 0,
              "Filed": 0, "Inbox": 0, "Duplicate?": 0, "Error": 0}
    for it in items:
        counts[it.get("status", "Queued")] = counts.get(it.get("status", "Queued"), 0) + 1
    return {"items": items, "counts": counts}


@router.post("/uploads/queue/{qid}/decision")
async def queue_decision(qid: str, payload: dict):
    """Resolve a Duplicate? prompt. payload.action ∈ skip|upload_anyway|replace"""
    item = await _db.upload_queue.find_one({"id": qid}, {"_id": 0})
    if not item:
        raise HTTPException(404, "queue item not found")
    action = (payload.get("action") or "").lower()
    if action == "skip":
        try:
            p = Path(item["staging_path"])
            if p.exists():
                p.unlink()
        except Exception:
            pass
        await _db.upload_queue.update_one({"id": qid}, {"$set": {"status": "Cancelled", "completed_at": utc_now_iso()}})
        return {"ok": True, "action": "skip"}
    if action == "upload_anyway":
        await _db.upload_queue.update_one({"id": qid}, {"$set": {"status": "Queued", "duplicate_of": None}})
        asyncio.create_task(_run_worker())
        return {"ok": True, "action": "upload_anyway"}
    if action == "replace":
        await _db.upload_queue.update_one({"id": qid}, {"$set": {"status": "Queued", "replace_id": item.get("duplicate_of")}})
        asyncio.create_task(_run_worker())
        return {"ok": True, "action": "replace"}
    raise HTTPException(400, "invalid action")


@router.delete("/uploads/queue/{qid}")
async def cancel_one(qid: str):
    item = await _db.upload_queue.find_one({"id": qid}, {"_id": 0})
    if not item:
        raise HTTPException(404, "not found")
    if item.get("status") in ("Queued", "Duplicate?"):
        try:
            p = Path(item.get("staging_path") or "")
            if p.exists():
                p.unlink()
        except Exception:
            pass
    await _db.upload_queue.update_one({"id": qid}, {"$set": {"status": "Cancelled", "completed_at": utc_now_iso()}})
    return {"ok": True}


@router.delete("/uploads/queue")
async def cancel_all():
    items = await _db.upload_queue.find(
        {"status": {"$in": ["Queued", "Duplicate?"]}}, {"_id": 0, "id": 1, "staging_path": 1}
    ).to_list(5000)
    for it in items:
        try:
            p = Path(it.get("staging_path") or "")
            if p.exists():
                p.unlink()
        except Exception:
            pass
    await _db.upload_queue.update_many(
        {"status": {"$in": ["Queued", "Duplicate?"]}},
        {"$set": {"status": "Cancelled", "completed_at": utc_now_iso()}},
    )
    return {"ok": True}


@router.delete("/uploads/queue/finished/clear")
async def clear_finished():
    """Remove queue rows whose status is terminal."""
    terminal = ["Filed", "Inbox", "Error", "Cancelled"]
    await _db.upload_queue.delete_many({"status": {"$in": terminal}})
    return {"ok": True}


@router.get("/ai/stats")
async def ai_stats():
    """Hybrid AI usage stats — counts Gemini-only vs Claude-escalated runs and
    sums per-model cost. Cached responses contribute zero cost."""
    total_docs = await _db.documents.count_documents({"ai_model_used": {"$ne": None}})
    claude_escalations = await _db.documents.count_documents({"escalated_to_claude": True})
    gemini_only = await _db.documents.count_documents({"escalated_to_claude": False, "ai_model_used": {"$ne": None}})

    pipeline = [
        {"$match": {"ai_model_used": {"$ne": None}}},
        {"$group": {
            "_id": None,
            "total_cost": {"$sum": {"$ifNull": ["$total_ai_cost_usd", "$ai_cost_usd"]}},
            "gemini_cost": {"$sum": {"$ifNull": ["$gemini_cost_usd", 0]}},
            "claude_cost": {"$sum": {"$ifNull": ["$claude_cost_usd", 0]}},
            "tokens_in": {"$sum": "$ai_input_tokens"},
            "tokens_out": {"$sum": "$ai_output_tokens"},
        }},
    ]
    agg = await _db.documents.aggregate(pipeline).to_list(1)
    sums = agg[0] if agg else {}
    last_err = await _db.ai_errors.find_one({"key": _singleton_key}, {"_id": 0})

    return {
        # camelCase fields used by the Settings UI:
        "totalDocs": total_docs,
        "geminiCalls": total_docs,
        "claudeEscalations": claude_escalations,
        "geminiOnly": gemini_only,
        "totalCost": round((sums.get("total_cost") or 0.0), 4),
        "geminiCost": round((sums.get("gemini_cost") or 0.0), 4),
        "claudeCost": round((sums.get("claude_cost") or 0.0), 4),
        # legacy snake_case kept for backwards compatibility
        "status": "Active" if os.environ.get("EMERGENT_LLM_KEY") else "Disabled",
        "mode": "Hybrid (Gemini → Claude escalation)",
        "primary_model": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        "escalation_model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
        "documents_processed": total_docs,
        "total_cost_usd": round((sums.get("total_cost") or 0.0), 4),
        "total_tokens_in": (sums.get("tokens_in") or 0),
        "total_tokens_out": (sums.get("tokens_out") or 0),
        "last_error": last_err,
    }


# ---------- Worker -----------------------------------------------------------

async def _run_worker():
    """Pulls Queued items and processes them, capped by the AI semaphore."""
    while True:
        item = await _db.upload_queue.find_one_and_update(
            {"status": "Queued"},
            {"$set": {"status": "Uploading", "started_at": utc_now_iso()}},
            sort=[("queued_at", 1)],
        )
        if not item:
            return
        try:
            await _process_one(item)
        except Exception as e:
            logger.exception(f"Pipeline crash on {item.get('id')}")
            await _db.upload_queue.update_one(
                {"id": item["id"]},
                {"$set": {"status": "Error", "error": str(e)[:500], "completed_at": utc_now_iso()}},
            )


async def _process_one(item: dict):
    qid = item["id"]
    sha = item["sha256"]
    staging = Path(item["staging_path"])
    if not staging.exists():
        await _db.upload_queue.update_one({"id": qid}, {"$set": {"status": "Error", "error": "Staging file missing", "completed_at": utc_now_iso()}})
        return
    content = staging.read_bytes()
    filename = item["filename"] or "file"
    mime = item.get("mime") or "application/octet-stream"

    # Step 3 — extract text
    await _db.upload_queue.update_one({"id": qid}, {"$set": {"status": "Reading"}})
    text = ""
    try:
        text = extract_text(content, filename, mime)
    except Exception as e:
        logger.warning(f"extract_text failed: {e}")

    # Step 4 — AI (with cache by SHA)
    await _db.upload_queue.update_one({"id": qid}, {"$set": {"status": "Classifying"}})
    cache = await _db.ai_response_cache.find_one({"sha256": sha}, {"_id": 0})
    if cache:
        analysis = cache["analysis"]
        ai_meta = {
            "ok": True,
            "cached": True,
            "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
            "model": cache.get("model", os.environ.get("ANTHROPIC_MODEL", "")),
        }
    else:
        async with _AI_SEM:
            result = await classify_document(filename, mime, text)
        if not result.get("ok") or not result.get("analysis"):
            await _db.ai_errors.update_one(
                {"key": _singleton_key},
                {"$set": {"key": _singleton_key, "message": result.get("error") or "AI failed", "timestamp": utc_now_iso(), "filename": filename}},
                upsert=True,
            )
            # File the document to 00 Inbox with no analysis
            analysis = {
                "document_type": "Unclassified",
                "category": "Other",
                "category_confidence": "Unsure",
                "tax_year": "Unsure",
                "tax_year_confidence": "Unsure",
                "tax_year_reason": result.get("error", "AI failed"),
                "date_range_from": None, "date_range_to": None,
                "counterparty": None,
                "one_line_summary": "AI classification failed — please review",
                "what_it_proves": "",
                "headline_figures": [],
                "accountant_review_required": True,
                "accountant_review_reason": "AI classification failed",
                "suggested_filename": None,
            }
        else:
            analysis = result["analysis"]
            await _db.ai_response_cache.update_one(
                {"sha256": sha},
                {"$set": {"sha256": sha, "analysis": analysis, "model": result["model"], "created_at": utc_now_iso()}},
                upsert=True,
            )
        ai_meta = {
            "ok": result.get("ok", False),
            "cached": False,
            "tokens_in": result.get("tokens_in", 0),
            "tokens_out": result.get("tokens_out", 0),
            "cost_usd": result.get("cost_usd", 0.0),
            "model": result.get("model"),
            "primary_model_used": result.get("primary_model_used"),
            "final_model_used": result.get("final_model_used"),
            "escalated_to_claude": bool(result.get("escalated_to_claude")),
            "escalation_reason": result.get("escalation_reason"),
            "gemini_cost_usd": result.get("gemini_cost_usd", 0.0),
            "claude_cost_usd": result.get("claude_cost_usd", 0.0),
            "total_ai_cost_usd": result.get("total_ai_cost_usd", result.get("cost_usd", 0.0)),
            "error": result.get("error"),
        }

    # Step 6 — determine target folder
    cat = analysis.get("category") or "Other"
    cat_conf = analysis.get("category_confidence") or "Unsure"
    if cat_conf == "Unsure":
        target_folder = INBOX_FOLDER
    else:
        target_folder = CATEGORY_TO_FOLDER.get(cat, INBOX_FOLDER)

    # Step 7 — copy to app_storage (canonical vault copy) using SHA-based path
    cat_dir = _app_storage_dir / _safe_filename(target_folder)
    cat_dir.mkdir(exist_ok=True)
    canonical_filename = analysis.get("suggested_filename") or filename
    canonical_path = cat_dir / f"{sha[:12]}_{_safe_filename(canonical_filename)}"
    canonical_path.write_bytes(content)

    # Step 8 — copy to Google Drive (best effort)
    drive_file_id = None
    drive_link = None
    drive_folder_id = None
    drive_error = None
    try:
        creds = await _db.drive_credentials.find_one({"key": _singleton_key})
        if creds:
            from googleapiclient.http import MediaIoBaseUpload
            cfg = await _get_or_create_folders()
            drive_folder_id = (cfg.get("subfolders") or {}).get(target_folder)
            if drive_folder_id:
                async with _DRIVE_SEM:
                    service = await _get_drive_service()
                    media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime, resumable=False)
                    meta = {"name": canonical_filename, "parents": [drive_folder_id]}
                    res = service.files().create(body=meta, media_body=media, fields="id, webViewLink").execute()
                    drive_file_id = res.get("id")
                    drive_link = res.get("webViewLink")
    except Exception as e:
        drive_error = str(e)[:300]
        logger.warning(f"Drive upload failed (continuing with local copy): {e}")

    # Step 9 — create document row
    doc_id = str(uuid.uuid4())
    doc = {
        "id": doc_id,
        "name": analysis.get("one_line_summary") or canonical_filename,
        "file_type": mime,
        "original_filename": filename,
        "tax_year": analysis.get("tax_year") or "Unsure",
        "category": cat,
        "notes": "",
        "accountant_review": "Yes" if analysis.get("accountant_review_required") else "No",
        "status": "Accountant review" if analysis.get("accountant_review_required") else "Uploaded only",
        "key_figures_found": "",
        "what_it_proves": analysis.get("what_it_proves") or "",
        "missing_followup": "",
        "drive_file_id": drive_file_id,
        "drive_link": drive_link,
        "drive_folder_id": drive_folder_id,
        "drive_folder_name": target_folder,
        "storage": "drive_and_local" if drive_file_id else "local",
        "local_path": str(canonical_path),
        "manual_drive_folder": "",
        "manual_drive_link": "",
        "size_bytes": len(content),
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        # Stage 2 fields
        "sha256": sha,
        "vault_filename": canonical_filename,
        "app_storage_path": str(canonical_path),
        "extracted_text": text,
        "category_confidence": cat_conf,
        "tax_year_confidence": analysis.get("tax_year_confidence") or "Unsure",
        "tax_year_reason": analysis.get("tax_year_reason") or "",
        "headline_figures_json": analysis.get("headline_figures") or [],
        "date_range_from": analysis.get("date_range_from"),
        "date_range_to": analysis.get("date_range_to"),
        "counterparty": analysis.get("counterparty"),
        "one_line_summary": analysis.get("one_line_summary") or "",
        "accountant_review_required": bool(analysis.get("accountant_review_required")),
        "accountant_review_reason": analysis.get("accountant_review_reason"),
        "risk_level": analysis.get("risk_level") or "Amber",
        "suggested_filename": analysis.get("suggested_filename"),
        "ai_model_used": ai_meta.get("model"),
        "ai_input_tokens": ai_meta.get("tokens_in", 0),
        "ai_output_tokens": ai_meta.get("tokens_out", 0),
        "ai_cost_usd": ai_meta.get("cost_usd", 0.0),
        "ai_call_timestamp": utc_now_iso(),
        "ai_response_cached": bool(ai_meta.get("cached")),
        "primary_model_used": ai_meta.get("primary_model_used"),
        "final_model_used": ai_meta.get("final_model_used"),
        "escalated_to_claude": ai_meta.get("escalated_to_claude", False),
        "escalation_reason": ai_meta.get("escalation_reason"),
        "gemini_cost_usd": ai_meta.get("gemini_cost_usd", 0.0),
        "claude_cost_usd": ai_meta.get("claude_cost_usd", 0.0),
        "total_ai_cost_usd": ai_meta.get("total_ai_cost_usd", ai_meta.get("cost_usd", 0.0)),
        "user_confirmed": False,
        "user_notes": "",
        "drive_error": drive_error,
    }
    await _db.documents.insert_one(doc)

    # ---- Stage 2: update missing-evidence tracker (non-blocking) ----
    try:
        from missing_evidence import check_and_update_missing_evidence
        ai_for_match = dict(analysis or {})
        ai_for_match["original_filename"] = filename
        ai_for_match["headline_figures_json"] = analysis.get("headline_figures") or []
        await check_and_update_missing_evidence(_db, doc_id, ai_for_match)
    except Exception as e:
        logger.warning(f"Missing-evidence update failed for {doc_id} (continuing): {e}")

    # cleanup staging
    try:
        staging.unlink(missing_ok=True)
    except Exception:
        pass

    final_status = "Inbox" if target_folder == INBOX_FOLDER else "Filed"
    await _db.upload_queue.update_one(
        {"id": qid},
        {"$set": {
            "status": final_status,
            "completed_at": utc_now_iso(),
            "result_document_id": doc_id,
            "ai_category": cat,
            "ai_confidence": cat_conf,
            "ai_cost_usd": ai_meta.get("cost_usd", 0.0),
            "target_folder": target_folder,
        }},
    )
