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
from error_codes import ErrorCode, ERROR_MESSAGES, classify_ai_error, classify_drive_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Hard size cap (Stage 4). 100 MB.
MAX_FILE_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))

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
        # Stage 4 — hard size cap; oversize files are queued in Error state
        # with a stable error_code so the UI can show "Retry" on a smaller file.
        oversize = len(content) > MAX_FILE_BYTES
        empty = len(content) == 0
        # dedup check: existing document with same sha
        existing = await _db.documents.find_one({"sha256": sha}, {"_id": 0, "id": 1, "name": 1, "created_at": 1, "category": 1}) if not (oversize or empty) else None
        # write content to a temp staging file
        staging = _app_storage_dir / f"_staging__{uuid.uuid4()}__{_safe_filename(f.filename or 'file')}"
        staging.write_bytes(content)
        qid = str(uuid.uuid4())
        if oversize:
            initial_status, err_code, err_msg = "Error", ErrorCode.FILE_TOO_LARGE, ERROR_MESSAGES[ErrorCode.FILE_TOO_LARGE]
        elif empty:
            initial_status, err_code, err_msg = "Error", ErrorCode.FILE_EMPTY, ERROR_MESSAGES[ErrorCode.FILE_EMPTY]
        elif existing:
            initial_status, err_code, err_msg = "Duplicate?", ErrorCode.FILE_DUPLICATE, ERROR_MESSAGES[ErrorCode.FILE_DUPLICATE]
        else:
            initial_status, err_code, err_msg = "Queued", None, None
        await _db.upload_queue.insert_one({
            "id": qid,
            "filename": f.filename,
            "mime": f.content_type or "application/octet-stream",
            "size_bytes": len(content),
            "sha256": sha,
            "staging_path": str(staging),
            "status": initial_status,
            "duplicate_of": existing.get("id") if existing else None,
            "duplicate_meta": existing or None,
            "result_document_id": None,
            "ai_category": None,
            "ai_confidence": None,
            "ai_cost_usd": 0.0,
            "error": err_msg,
            "error_code": err_code,
            "queued_at": utc_now_iso(),
            "started_at": None,
            "completed_at": utc_now_iso() if initial_status == "Error" else None,
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
    """Cancel a single queued, duplicate, or active row.
    For Queued/Duplicate? we terminate immediately. For active rows
    (Uploading/Reading/Classifying) we flag cancel_requested=True and the
    worker stops at the next checkpoint."""
    item = await _db.upload_queue.find_one({"id": qid}, {"_id": 0})
    if not item:
        raise HTTPException(404, "not found")
    status = item.get("status")
    if status in ("Queued", "Duplicate?"):
        try:
            p = Path(item.get("staging_path") or "")
            if p.exists():
                p.unlink()
        except Exception:
            pass
        await _db.upload_queue.update_one(
            {"id": qid},
            {"$set": {
                "status": "Cancelled",
                "error_code": ErrorCode.CANCELLED,
                "error": ERROR_MESSAGES[ErrorCode.CANCELLED],
                "completed_at": utc_now_iso(),
            }},
        )
        return {"ok": True, "mode": "immediate"}
    if status in ("Uploading", "Reading", "Classifying"):
        # Cooperative cancellation — worker stops at next checkpoint.
        await _db.upload_queue.update_one({"id": qid}, {"$set": {"cancel_requested": True}})
        return {"ok": True, "mode": "cooperative"}
    return {"ok": True, "mode": "noop"}


@router.delete("/uploads/queue")
async def cancel_all():
    """Cancel all queued + duplicate + active rows.
    Queued/Duplicate? terminate immediately; active rows get
    cancel_requested=True and the worker stops at next checkpoint."""
    immediate = ["Queued", "Duplicate?"]
    cooperative = ["Uploading", "Reading", "Classifying"]
    items = await _db.upload_queue.find(
        {"status": {"$in": immediate}}, {"_id": 0, "id": 1, "staging_path": 1}
    ).to_list(5000)
    for it in items:
        try:
            p = Path(it.get("staging_path") or "")
            if p.exists():
                p.unlink()
        except Exception:
            pass
    res_imm = await _db.upload_queue.update_many(
        {"status": {"$in": immediate}},
        {"$set": {
            "status": "Cancelled",
            "error_code": ErrorCode.CANCELLED,
            "error": ERROR_MESSAGES[ErrorCode.CANCELLED],
            "completed_at": utc_now_iso(),
        }},
    )
    res_coop = await _db.upload_queue.update_many(
        {"status": {"$in": cooperative}},
        {"$set": {"cancel_requested": True}},
    )
    return {"ok": True, "immediate": res_imm.modified_count, "cooperative": res_coop.modified_count}


@router.delete("/uploads/queue/finished/clear")
async def clear_finished():
    """Remove queue rows whose status is terminal."""
    terminal = ["Filed", "Inbox", "Error", "Cancelled"]
    await _db.upload_queue.delete_many({"status": {"$in": terminal}})
    return {"ok": True}


# ---------- Stage 4: retry + recovery ---------------------------------------

@router.post("/uploads/queue/{qid}/retry")
async def retry_one(qid: str):
    """Re-queue a failed or cancelled item. Only works if the staging file
    still exists locally — otherwise the user must re-upload."""
    item = await _db.upload_queue.find_one({"id": qid}, {"_id": 0})
    if not item:
        raise HTTPException(404, "queue item not found")
    if item.get("status") not in ("Error", "Cancelled"):
        raise HTTPException(400, f"cannot retry from status {item.get('status')}")
    staging = Path(item.get("staging_path") or "")
    if not staging.exists():
        raise HTTPException(409, "staging file missing — please re-upload this file")
    await _db.upload_queue.update_one(
        {"id": qid},
        {"$set": {
            "status": "Queued",
            "error": None,
            "error_code": None,
            "started_at": None,
            "completed_at": None,
        }},
    )
    asyncio.create_task(_run_worker())
    return {"ok": True}


@router.post("/uploads/recover-stuck")
async def recover_stuck():
    """Reset items stuck in an active state for >10 minutes back to Queued.
    Called from the frontend on app load to recover from a crashed worker
    (e.g. backend restart mid-pipeline)."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    active = ["Uploading", "Reading", "Classifying"]
    res = await _db.upload_queue.update_many(
        {"status": {"$in": active}, "$or": [
            {"started_at": {"$lt": cutoff}},
            {"started_at": None},
        ]},
        {"$set": {"status": "Queued", "started_at": None}},
    )
    if res.modified_count:
        asyncio.create_task(_run_worker())
    return {"ok": True, "recovered": res.modified_count}


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


AI_TIMEOUT_SECONDS = int(os.environ.get("AI_TIMEOUT_SECONDS", "60"))


class _Cancelled(Exception):
    """Cooperative-cancellation sentinel — raised by checkpoints inside the
    worker; caught by `_process_one` so the row terminates cleanly without
    creating a document or touching missing-evidence."""


async def _check_cancelled(qid: str) -> bool:
    """Returns True if `cancel_requested` is set on the queue row."""
    row = await _db.upload_queue.find_one({"id": qid}, {"_id": 0, "cancel_requested": 1})
    return bool(row and row.get("cancel_requested"))


async def _raise_if_cancelled(qid: str):
    if await _check_cancelled(qid):
        raise _Cancelled()


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
        except _Cancelled:
            await _finalize_cancelled(item)
        except Exception as e:
            # Stage 4.5 — never leak raw exception text to the user.
            logger.exception(f"Pipeline crash on {item.get('id')}: {e}")
            await _db.upload_queue.update_one(
                {"id": item["id"]},
                {"$set": {
                    "status": "Error",
                    "error": ERROR_MESSAGES[ErrorCode.UNEXPECTED_ERROR],
                    "error_code": ErrorCode.UNEXPECTED_ERROR,
                    "completed_at": utc_now_iso(),
                }},
            )


async def _finalize_cancelled(item: dict):
    qid = item["id"]
    # Try to clean up the staging file — safe even mid-pipeline because we
    # never inserted a document row.
    try:
        p = Path(item.get("staging_path") or "")
        if p.exists():
            p.unlink()
    except Exception:
        pass
    await _db.upload_queue.update_one(
        {"id": qid},
        {"$set": {
            "status": "Cancelled",
            "error_code": ErrorCode.CANCELLED,
            "error": ERROR_MESSAGES[ErrorCode.CANCELLED],
            "cancel_requested": False,
            "completed_at": utc_now_iso(),
        }},
    )
    logger.info(f"Cancelled mid-pipeline: {qid}")


async def _process_one(item: dict):
    qid = item["id"]
    sha = item["sha256"]
    staging = Path(item["staging_path"])
    if not staging.exists():
        await _db.upload_queue.update_one({"id": qid}, {"$set": {
            "status": "Error",
            "error": ERROR_MESSAGES[ErrorCode.STAGING_MISSING],
            "error_code": ErrorCode.STAGING_MISSING,
            "completed_at": utc_now_iso(),
        }})
        return
    content = staging.read_bytes()
    filename = item["filename"] or "file"
    mime = item.get("mime") or "application/octet-stream"

    # Checkpoint — before extraction
    await _raise_if_cancelled(qid)

    # Step 3 — extract text
    await _db.upload_queue.update_one({"id": qid}, {"$set": {"status": "Reading"}})
    text = ""
    extraction_failed = False
    try:
        text = extract_text(content, filename, mime)
    except Exception as e:
        logger.warning(f"extract_text failed: {e}")
        extraction_failed = True
    if not extraction_failed and (not text or len(text.strip()) < 10):
        # Allow filing but flag for manual review and skip auto-matching.
        extraction_failed = True

    # Checkpoint — after extraction
    await _raise_if_cancelled(qid)

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
        # Checkpoint — before AI
        await _raise_if_cancelled(qid)
        async with _AI_SEM:
            # Hard 60s timeout — if AI hangs the whole queue would otherwise
            # stall. Cooperative cancellation also checked after the call.
            try:
                result = await asyncio.wait_for(
                    classify_document(filename, mime, text),
                    timeout=AI_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning(f"AI classification timed out (>{AI_TIMEOUT_SECONDS}s) for {filename}")
                # Hard fail with stable code; staging file is left intact so
                # the user can use Retry to re-queue.
                await _db.upload_queue.update_one(
                    {"id": qid},
                    {"$set": {
                        "status": "Error",
                        "error": ERROR_MESSAGES[ErrorCode.AI_TIMEOUT],
                        "error_code": ErrorCode.AI_TIMEOUT,
                        "completed_at": utc_now_iso(),
                    }},
                )
                return
        # Checkpoint — after AI
        await _raise_if_cancelled(qid)
        if not result.get("ok") or not result.get("analysis"):
            ai_err = result.get("error") or "AI failed"
            ai_code = classify_ai_error(ai_err)
            await _db.ai_errors.update_one(
                {"key": _singleton_key},
                {"$set": {"key": _singleton_key, "message": ai_err, "timestamp": utc_now_iso(), "filename": filename}},
                upsert=True,
            )
            # Rate-limit / timeout: hard-fail the row so the user can retry,
            # don't insert a document. Other AI errors: file to Inbox for
            # manual review (existing behaviour).
            if ai_code in (ErrorCode.AI_RATE_LIMIT, ErrorCode.AI_TIMEOUT):
                await _db.upload_queue.update_one(
                    {"id": qid},
                    {"$set": {
                        "status": "Error",
                        "error": ERROR_MESSAGES[ai_code],
                        "error_code": ai_code,
                        "completed_at": utc_now_iso(),
                    }},
                )
                return
            # File the document to 00 Inbox with no analysis
            analysis = {
                "document_type": "Unclassified",
                "category": "Other",
                "category_confidence": "Unsure",
                "tax_year": "Unsure",
                "tax_year_confidence": "Unsure",
                "tax_year_reason": ai_err,
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

    # Stage 4.5 — extraction-failure flagging: AI was best-effort, but if we
    # have no usable text, force accountant review and force Inbox routing,
    # and downstream we'll skip auto-matching to missing evidence.
    if extraction_failed:
        analysis = dict(analysis)
        analysis["accountant_review_required"] = True
        prev_reason = analysis.get("accountant_review_reason") or ""
        ext_reason = "Text extraction failed or limited text extracted."
        analysis["accountant_review_reason"] = (
            f"{prev_reason} | {ext_reason}".strip(" |") if prev_reason else ext_reason
        )
        analysis["category_confidence"] = "Unsure"

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

    # Checkpoint — before Drive upload
    await _raise_if_cancelled(qid)

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
    # Checkpoint — before document insert (last cancel opportunity)
    await _raise_if_cancelled(qid)
    await _db.documents.insert_one(doc)

    # ---- Stage 2: update missing-evidence tracker (non-blocking) ----
    # Skip auto-matching if we never had usable text to begin with — avoids
    # mis-matching purely on category.
    if not extraction_failed:
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
    # Surface Drive/AI sub-errors as informational codes even on a successful row.
    info_code = None
    info_msg = None
    if drive_error:
        info_code = classify_drive_error(drive_error)
        info_msg = ERROR_MESSAGES[info_code]
    elif ai_meta.get("error"):
        info_code = classify_ai_error(ai_meta.get("error"))
        info_msg = ERROR_MESSAGES[info_code]
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
            "error_code": info_code,
            "error": info_msg,
        }},
    )
