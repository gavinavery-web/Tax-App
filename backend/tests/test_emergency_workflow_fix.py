"""Stage 7 — Emergency Workflow Fix backend tests.

Covers the 6 fixes in the review request:
  1. GET /api/ai-usage              — provider/billing/cost transparency
  2. POST /api/admin/reset-test-data with trash_drive flag — returns
     drive_files_trashed + drive_files_failed even without Drive
  3. POST /api/bank-transactions/{id}/add-to-return + /ignore endpoints
  4. Dashboard / stats / readiness filter is_deleted=True
"""
from __future__ import annotations

import io
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://evidence-vault-54.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# ---------- helpers ----------

def _make_doc(s, name=None):
    name = name or f"TEST_emergency_{uuid.uuid4().hex[:6]}.pdf"
    files = {"file": (name, io.BytesIO(b"%PDF-1.4\n test emergency"), "application/pdf")}
    data = {
        "name": name,
        "tax_year": "FY2024",
        "category": "Other",
        "accountant_review": "No",
        "notes": "emergency workflow test fixture",
    }
    r = s.post(f"{API}/documents", files=files, data=data)
    assert r.status_code == 200, r.text
    return r.json()


def _make_bank_tx(s, evidence_status="confirmed_tax", classification="rental_income"):
    """Insert a bank transaction directly via the test endpoint if it
    exists, otherwise via a MongoDB-shaped POST. The server doesn't expose
    a 'create bank transaction' endpoint, so we use the upload pipeline's
    internal mechanism by directly POSTing through requests not possible.
    Instead, we rely on bulk_upload of a CSV. For deterministic test, we
    use Mongo directly via the admin endpoint, OR we just call /bank-
    transactions which lists — and skip if none exist."""
    return None  # caller will skip if no transactions present


# ============================================================================
# Fix 1: GET /api/ai-usage
# ============================================================================

class TestAIUsage:
    def test_ai_usage_returns_all_required_fields(self, s):
        r = s.get(f"{API}/ai-usage")
        assert r.status_code == 200, r.text
        data = r.json()
        # All 7 contract fields required by Settings AIUsageCard
        for k in (
            "provider", "billing_source", "is_real_user_charge",
            "documents_processed", "claude_escalations",
            "avg_cost_per_document_usd", "total_cost_usd", "explanation",
        ):
            assert k in data, f"missing field: {k}"

    def test_ai_usage_real_user_charge_is_false(self, s):
        """Emergent LLM key is never billed directly to the user."""
        r = s.get(f"{API}/ai-usage")
        assert r.status_code == 200
        assert r.json()["is_real_user_charge"] is False

    def test_ai_usage_numbers_are_numeric(self, s):
        r = s.get(f"{API}/ai-usage")
        data = r.json()
        assert isinstance(data["documents_processed"], int)
        assert isinstance(data["claude_escalations"], int)
        assert isinstance(data["total_cost_usd"], (int, float))
        assert isinstance(data["avg_cost_per_document_usd"], (int, float))
        assert data["total_cost_usd"] >= 0
        assert data["avg_cost_per_document_usd"] >= 0


# ============================================================================
# Fix 2: Reset endpoint trash_drive behaviour
# ============================================================================

class TestResetTrashDrive:
    def test_reset_endpoint_returns_drive_fields(self, s):
        """trash_drive=True must always succeed even when Drive isn't
        connected. Returns drive_files_trashed (int) + drive_files_failed
        (list)."""
        r = s.post(
            f"{API}/admin/reset-test-data",
            json={"reset_properties": False, "trash_drive": True},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["success"] is True
        assert "drive_files_trashed" in data
        assert "drive_files_failed" in data
        assert isinstance(data["drive_files_trashed"], int)
        assert isinstance(data["drive_files_failed"], list)
        # Endpoint must succeed regardless of whether Drive is connected.
        # If Drive is wired up, trashed will be >= 0 and failed must remain
        # a list (each entry being a dict with file_id/name/error).
        assert data["drive_files_trashed"] >= 0
        for f in data["drive_files_failed"]:
            assert isinstance(f, dict)
            assert "error" in f

    def test_reset_endpoint_without_trash_drive(self, s):
        """trash_drive=False must skip the Drive step entirely."""
        r = s.post(
            f"{API}/admin/reset-test-data",
            json={"reset_properties": False, "trash_drive": False},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["drive_files_trashed"] == 0


# ============================================================================
# Fix 3: bank-transactions add-to-return + ignore endpoints
# ============================================================================

class TestAddToReturnEndpoint:
    def test_add_to_return_unknown_tx_returns_404(self, s):
        r = s.post(
            f"{API}/bank-transactions/__nope__/add-to-return",
            json={
                "tax_year": "FY2024",
                "section": "rental_income",
                "income_or_deduction": "income",
                "amount_cents": 12345,
                "description": "fake",
            },
        )
        assert r.status_code == 404

    def test_ignore_unknown_tx_returns_404(self, s):
        r = s.post(f"{API}/bank-transactions/__nope__/ignore")
        assert r.status_code == 404

    def test_add_to_return_full_lifecycle(self, s):
        """If there are bank transactions in DB, test full add-to-return
        path. Otherwise skip — depends on prior data."""
        list_r = s.get(f"{API}/bank-transactions", params={"limit": 50})
        assert list_r.status_code == 200, list_r.text
        txs = list_r.json()
        unused = [
            t for t in txs
            if not t.get("used_in_return") and t.get("evidence_status") != "private"
        ]
        if not unused:
            pytest.skip("no unused bank transactions in DB to exercise add-to-return")

        tx = unused[0]
        tx_id = tx["id"]

        # Missing required field → 400
        r = s.post(
            f"{API}/bank-transactions/{tx_id}/add-to-return",
            json={"tax_year": "FY2024"},
        )
        assert r.status_code == 400

        # Invalid section → 400
        r = s.post(
            f"{API}/bank-transactions/{tx_id}/add-to-return",
            json={
                "tax_year": "FY2024",
                "section": "not_a_real_section",
                "income_or_deduction": "income",
                "amount_cents": 5000,
                "description": "test",
            },
        )
        assert r.status_code == 400

        # Valid payload
        payload = {
            "tax_year": "FY2024",
            "section": "rental_income",
            "income_or_deduction": "income",
            "amount_cents": 9999,
            "description": "TEST_emergency_addtoreturn",
            "notes": "added via test_emergency_workflow_fix",
        }
        r = s.post(f"{API}/bank-transactions/{tx_id}/add-to-return", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert "item_id" in body
        assert body["tax_year"] == "FY2024"

        # Verify the tax_return_item exists and has the backlink
        items_r = s.get(f"{API}/tax-return-items")
        items = items_r.json()
        match = next((i for i in items if i.get("id") == body["item_id"]), None)
        assert match is not None, "created tax_return_item not found in list"
        assert match.get("source_type") == "bank_transaction"
        assert match.get("source_bank_transaction_id") == tx_id
        assert match.get("manual_override") is True

        # Verify transaction was marked used_in_return
        list_r = s.get(f"{API}/bank-transactions", params={"limit": 200})
        updated = next((t for t in list_r.json() if t["id"] == tx_id), None)
        assert updated and updated.get("used_in_return") is True

        # Re-adding the same tx → 400 ("already used")
        r = s.post(f"{API}/bank-transactions/{tx_id}/add-to-return", json=payload)
        assert r.status_code == 400

    def test_ignore_endpoint_is_idempotent(self, s):
        list_r = s.get(f"{API}/bank-transactions", params={"limit": 50})
        txs = list_r.json()
        candidates = [
            t for t in txs
            if not t.get("used_in_return") and t.get("evidence_status") != "private"
        ]
        if not candidates:
            pytest.skip("no eligible bank transactions to ignore")

        tx_id = candidates[0]["id"]
        r1 = s.post(f"{API}/bank-transactions/{tx_id}/ignore")
        assert r1.status_code == 200
        r2 = s.post(f"{API}/bank-transactions/{tx_id}/ignore")
        assert r2.status_code == 200  # idempotent

        # Confirm evidence_status is now 'private'
        list_r = s.get(f"{API}/bank-transactions", params={"limit": 200})
        match = next((t for t in list_r.json() if t["id"] == tx_id), None)
        assert match and match.get("evidence_status") == "private"


# ============================================================================
# Fix 6: dashboard endpoints filter is_deleted
# ============================================================================

class TestDashboardFiltersDeleted:
    def test_dashboard_excludes_deleted_docs(self, s):
        """Create a doc, observe count change in /api/dashboard, soft-delete,
        observe count decreases."""
        # Snapshot before
        before = s.get(f"{API}/dashboard").json()
        before_total = before.get("total_documents", 0)

        doc = _make_doc(s, name=f"TEST_dash_{uuid.uuid4().hex[:6]}.pdf")
        doc_id = doc["id"]

        after = s.get(f"{API}/dashboard").json()
        after_total = after.get("total_documents", 0)
        assert after_total == before_total + 1, (
            f"expected total to increment by 1, before={before_total} after={after_total}"
        )

        # Soft delete
        del_r = s.post(f"{API}/documents/{doc_id}/delete", json={"reason": "test cleanup"})
        assert del_r.status_code == 200, del_r.text

        post_del = s.get(f"{API}/dashboard").json()
        post_total = post_del.get("total_documents", 0)
        assert post_total == before_total, (
            f"deleted doc still counted: before={before_total} post-del={post_total}"
        )

    def test_dashboard_stats_excludes_deleted(self, s):
        """/api/dashboard/stats should also drop is_deleted docs from
        `total` and per-category counts."""
        before = s.get(f"{API}/dashboard/stats").json()
        before_total = before.get("total", 0)

        doc = _make_doc(s, name=f"TEST_stats_{uuid.uuid4().hex[:6]}.pdf")
        doc_id = doc["id"]

        after = s.get(f"{API}/dashboard/stats").json()
        assert after["total"] == before_total + 1

        s.post(f"{API}/documents/{doc_id}/delete", json={"reason": "test cleanup"})

        post_del = s.get(f"{API}/dashboard/stats").json()
        assert post_del["total"] == before_total, (
            f"dashboard/stats still counts deleted doc: before={before_total} after-del={post_del['total']}"
        )

    def test_dashboard_readiness_excludes_deleted(self, s):
        """/api/dashboard/readiness inbox/review/red/unsure-fy must drop
        is_deleted docs."""
        before = s.get(f"{API}/dashboard/readiness").json()
        before_inbox = before.get("inbox_count", before.get("inbox", 0))

        doc = _make_doc(s, name=f"TEST_ready_{uuid.uuid4().hex[:6]}.pdf")
        doc_id = doc["id"]
        s.post(f"{API}/documents/{doc_id}/delete", json={"reason": "test cleanup"})

        post = s.get(f"{API}/dashboard/readiness").json()
        post_inbox = post.get("inbox_count", post.get("inbox", 0))
        # Whatever inbox counted before should be the same now (deleted doc shouldn't have moved the needle)
        assert post_inbox == before_inbox, (
            f"readiness still counts deleted doc: before={before_inbox} after={post_inbox}"
        )
