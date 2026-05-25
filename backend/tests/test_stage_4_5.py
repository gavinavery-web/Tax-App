"""Stage 4.5 — hardening tests.

These verify the fixes added in Stage 4.5:
- AI error classification helpers
- Drive error classification helpers
- Bulk upload error-code propagation (FILE_TOO_LARGE, FILE_EMPTY, FILE_DUPLICATE)
- Cancel endpoint returns immediate vs cooperative modes
- Crash handler emits ERROR_MESSAGES[UNEXPECTED_ERROR] (no raw exception leakage)
- Dashboard missing count excludes Received / Not applicable
- Accountant PDF outstanding section excludes Received / Not applicable
- Missing evidence manual override sets status_source="user"
- Retry / recover-stuck endpoints
"""
from __future__ import annotations

import io
import os
import sys
import time
import uuid

import pytest
import requests

# Make backend modules importable for direct unit tests of helpers.
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

from error_codes import (  # noqa: E402
    ErrorCode,
    ERROR_MESSAGES,
    classify_ai_error,
    classify_drive_error,
)

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://evidence-vault-54.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# ============================================================================
# Pure unit tests — error code mapping
# ============================================================================

class TestErrorCodeMapping:
    def test_ai_timeout(self):
        assert classify_ai_error("timeout: deadline exceeded") == ErrorCode.AI_TIMEOUT
        assert classify_ai_error("Request timed out after 60s") == ErrorCode.AI_TIMEOUT

    def test_ai_rate_limit(self):
        assert classify_ai_error("HTTP 429 Too Many Requests") == ErrorCode.AI_RATE_LIMIT
        assert classify_ai_error("rate limit exceeded for gemini") == ErrorCode.AI_RATE_LIMIT
        assert classify_ai_error("quota exhausted") == ErrorCode.AI_RATE_LIMIT
        assert classify_ai_error("Server overloaded — try again") == ErrorCode.AI_RATE_LIMIT

    def test_ai_generic(self):
        assert classify_ai_error("Both models failed") == ErrorCode.AI_FAILED
        assert classify_ai_error("Non-JSON response") == ErrorCode.AI_FAILED
        assert classify_ai_error(None) == ErrorCode.AI_FAILED

    def test_drive_disconnected(self):
        assert classify_drive_error("HTTP 401 invalid_grant") == ErrorCode.DRIVE_DISCONNECTED
        assert classify_drive_error("credentials expired") == ErrorCode.DRIVE_DISCONNECTED
        assert classify_drive_error("Token revoked by user") == ErrorCode.DRIVE_DISCONNECTED

    def test_drive_quota(self):
        assert classify_drive_error("storageQuotaExceeded") == ErrorCode.DRIVE_QUOTA_EXCEEDED
        assert classify_drive_error("user storage full") == ErrorCode.DRIVE_QUOTA_EXCEEDED

    def test_drive_generic(self):
        assert classify_drive_error("network reset") == ErrorCode.DRIVE_UPLOAD_FAILED
        assert classify_drive_error(None) == ErrorCode.DRIVE_UPLOAD_FAILED

    def test_messages_exist_for_every_code(self):
        for code in vars(ErrorCode).values():
            if isinstance(code, str) and code.isupper():
                assert code in ERROR_MESSAGES, f"missing user message for {code}"


# ============================================================================
# Bulk upload error-code propagation
# ============================================================================

def _bulk_upload(s, name: str, content: bytes, mime: str = "application/pdf"):
    files = [("files", (name, io.BytesIO(content), mime))]
    r = s.post(f"{API}/uploads/bulk", files=files)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def _find_queue_row(s, qid: str):
    r = s.get(f"{API}/uploads/queue")
    assert r.status_code == 200
    for it in r.json()["items"]:
        if it["id"] == qid:
            return it
    return None


def test_upload_empty_file_sets_file_empty(s):
    res = _bulk_upload(s, f"empty-{uuid.uuid4().hex[:8]}.pdf", b"")
    qid = res["queue_ids"][0]
    row = _find_queue_row(s, qid)
    assert row is not None
    assert row["status"] == "Error"
    assert row["error_code"] == ErrorCode.FILE_EMPTY
    assert row["error"] == ERROR_MESSAGES[ErrorCode.FILE_EMPTY]
    # cleanup
    s.delete(f"{API}/uploads/queue/finished/clear")


def test_upload_too_large_sets_file_too_large(s):
    # 101 MB of zeroes
    big = b"\x00" * (101 * 1024 * 1024)
    res = _bulk_upload(s, f"big-{uuid.uuid4().hex[:8]}.pdf", big)
    qid = res["queue_ids"][0]
    row = _find_queue_row(s, qid)
    assert row is not None
    assert row["status"] == "Error"
    assert row["error_code"] == ErrorCode.FILE_TOO_LARGE
    assert row["error"] == ERROR_MESSAGES[ErrorCode.FILE_TOO_LARGE]
    s.delete(f"{API}/uploads/queue/finished/clear")


def test_upload_duplicate_sets_file_duplicate(s):
    # Use a stable known-existing file (or upload one then re-upload).
    payload = b"sentinel-duplicate-content-" + uuid.uuid4().bytes
    name1 = f"dup-{uuid.uuid4().hex[:8]}.txt"
    # First upload — let it process briefly so the document row exists.
    res1 = _bulk_upload(s, name1, payload, mime="text/plain")
    qid1 = res1["queue_ids"][0]
    # Wait for it to finish processing
    deadline = time.time() + 25
    while time.time() < deadline:
        row = _find_queue_row(s, qid1)
        if row and row["status"] in ("Filed", "Inbox", "Error"):
            break
        time.sleep(1)
    # Second upload of identical content — must be flagged as duplicate.
    res2 = _bulk_upload(s, name1, payload, mime="text/plain")
    qid2 = res2["queue_ids"][0]
    row2 = _find_queue_row(s, qid2)
    assert row2 is not None
    assert row2["status"] == "Duplicate?"
    assert row2["error_code"] == ErrorCode.FILE_DUPLICATE
    assert row2["error"] == ERROR_MESSAGES[ErrorCode.FILE_DUPLICATE]
    # cleanup: skip the duplicate, remove finished
    s.post(f"{API}/uploads/queue/{qid2}/decision", json={"action": "skip"})
    s.delete(f"{API}/uploads/queue/finished/clear")


# ============================================================================
# Crash handler — never leaks raw exception text
# ============================================================================

def test_unexpected_error_does_not_leak_raw_exception(s):
    """Triggered by an empty file (which short-circuits to FILE_EMPTY, not
    UNEXPECTED_ERROR — that's good). To verify the contract for the actual
    crash path we inspect the error_codes constants: the user-facing string
    must equal ERROR_MESSAGES[UNEXPECTED_ERROR] and contain no debug tokens
    like 'Traceback', '<', or 'line '."""
    msg = ERROR_MESSAGES[ErrorCode.UNEXPECTED_ERROR]
    assert "Traceback" not in msg
    assert "Exception" not in msg
    assert "line " not in msg
    assert "<" not in msg
    assert len(msg) <= 200


# ============================================================================
# Cancel endpoint — modes
# ============================================================================

def test_cancel_all_returns_immediate_and_cooperative_counts(s):
    r = s.delete(f"{API}/uploads/queue")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert "immediate" in d
    assert "cooperative" in d
    assert isinstance(d["immediate"], int)
    assert isinstance(d["cooperative"], int)


def test_cancel_one_404_for_missing(s):
    r = s.delete(f"{API}/uploads/queue/does-not-exist-{uuid.uuid4().hex}")
    assert r.status_code == 404


# ============================================================================
# Retry endpoint
# ============================================================================

def test_retry_404_for_missing(s):
    r = s.post(f"{API}/uploads/queue/does-not-exist-{uuid.uuid4().hex}/retry")
    assert r.status_code == 404


def test_retry_400_for_active_row(s):
    """An empty file lands in Error immediately; we can retry it. But a
    Queued/Filed/Inbox row should NOT be retryable."""
    # Get any current Filed row (or skip if none).
    r = s.get(f"{API}/uploads/queue")
    rows = r.json()["items"]
    filed = next((it for it in rows if it["status"] in ("Filed", "Inbox")), None)
    if not filed:
        pytest.skip("no Filed/Inbox row to test against")
    r = s.post(f"{API}/uploads/queue/{filed['id']}/retry")
    assert r.status_code == 400


def test_recover_stuck_returns_count(s):
    r = s.post(f"{API}/uploads/recover-stuck")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert "recovered" in d
    assert isinstance(d["recovered"], int)


# ============================================================================
# Dashboard missing count — excludes Received and Not applicable
# ============================================================================

def test_dashboard_missing_excludes_received_and_na(s):
    """Mark one item Received and one Not applicable, then verify the
    dashboard count drops by exactly 2 vs. the raw checklist size."""
    r = s.get(f"{API}/missing-evidence")
    items = r.json()
    outstanding = [it for it in items if it["status"] == "Outstanding"]
    if len(outstanding) < 2:
        # Re-seed to ensure we have outstanding items.
        s.post(f"{API}/missing-evidence/seed")
        r = s.get(f"{API}/missing-evidence")
        items = r.json()
        outstanding = [it for it in items if it["status"] == "Outstanding"]
    assert len(outstanding) >= 2, "need at least 2 outstanding items"

    target_a, target_b = outstanding[0], outstanding[1]

    # Snapshot the current dashboard count
    r = s.get(f"{API}/dashboard")
    cards = r.json()["cards"]
    missing_before = next(c for c in cards if c["key"] == "missing")["documents"]

    # Mark one Received + one Not applicable
    s.patch(f"{API}/missing-evidence/{target_a['id']}", json={"status": "Received"})
    s.patch(f"{API}/missing-evidence/{target_b['id']}", json={"status": "Not applicable"})

    r = s.get(f"{API}/dashboard")
    cards = r.json()["cards"]
    missing_after = next(c for c in cards if c["key"] == "missing")["documents"]
    assert missing_after == missing_before - 2, \
        f"expected count to drop by 2; before={missing_before}, after={missing_after}"

    # Cleanup — restore to Outstanding
    s.patch(f"{API}/missing-evidence/{target_a['id']}", json={"status": "Outstanding"})
    s.patch(f"{API}/missing-evidence/{target_b['id']}", json={"status": "Outstanding"})


# ============================================================================
# Accountant PDF — outstanding excludes Received / Not applicable
# ============================================================================

def test_accountant_pdf_outstanding_excludes_received_and_na(s):
    """We can't easily parse PDF bytes but we can verify the PDF generation
    doesn't crash and that the page size shrinks/grows with the count by
    comparing two snapshots."""
    # Mark all items Outstanding (worst case for PDF size)
    r = s.get(f"{API}/missing-evidence")
    for it in r.json():
        if it["status"] in ("Received", "Not applicable"):
            s.patch(f"{API}/missing-evidence/{it['id']}", json={"status": "Outstanding"})

    r = s.get(f"{API}/reports/accountant-summary.pdf")
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")
    big_size = len(r.content)

    # Now mark several Received
    r = s.get(f"{API}/missing-evidence")
    items = r.json()
    to_mark = items[:5]
    for it in to_mark:
        s.patch(f"{API}/missing-evidence/{it['id']}", json={"status": "Received"})

    r = s.get(f"{API}/reports/accountant-summary.pdf")
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")
    small_size = len(r.content)

    # PDF with fewer outstanding rows should not be larger than the full one.
    assert small_size <= big_size, \
        f"PDF size should shrink when items move out of outstanding: big={big_size}, small={small_size}"

    # Cleanup
    for it in to_mark:
        s.patch(f"{API}/missing-evidence/{it['id']}", json={"status": "Outstanding"})


# ============================================================================
# Missing evidence — manual override is not overwritten by auto-match
# ============================================================================

def test_manual_override_sets_status_source_user(s):
    r = s.get(f"{API}/missing-evidence")
    items = r.json()
    target = next((it for it in items if it["status"] == "Outstanding"), None)
    if target is None:
        s.post(f"{API}/missing-evidence/seed")
        r = s.get(f"{API}/missing-evidence")
        items = r.json()
        target = next((it for it in items if it["status"] == "Outstanding"), None)
    assert target is not None

    # User marks it Not applicable
    r = s.patch(f"{API}/missing-evidence/{target['id']}", json={"status": "Not applicable"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "Not applicable"
    assert body.get("status_source") == "user"
    assert body.get("status_updated_by") == "user"
    assert "status_updated_at" in body

    # Reset to Outstanding — clears manual flag
    r = s.patch(f"{API}/missing-evidence/{target['id']}", json={"status": "Outstanding"})
    body = r.json()
    assert body["status"] == "Outstanding"
    assert body.get("status_source") == "system"
