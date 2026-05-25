"""Stage 7 — FINAL workflow fix tests.

Covers:
 - Fix 3: auto-triage in classify_transaction_by_rules (pure unit, no DB)
 - Fix 6: POST /api/rubbish-bin/empty idempotency + soft-delete round-trip
 - Fix 9: PATCH /api/documents/{id} accountant_review lockstep recompute
"""
import os
import sys
import uuid
import pytest
import requests

def _resolve_base_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    # Fallback for pytest CLI runs: read frontend/.env so tests work without env export
    try:
        with open("/app/frontend/.env", "r") as f:
            for line in f:
                if line.strip().startswith("REACT_APP_BACKEND_URL="):
                    return line.strip().split("=", 1)[1].rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _resolve_base_url()
API_BASE = f"{BASE_URL}/api"


def _create_doc_via_upload():
    """Upload a tiny dummy file via POST /api/documents (multipart). Returns doc id."""
    files = {
        "file": (f"TEST_workflow_{uuid.uuid4().hex[:6]}.txt", b"dummy content", "text/plain"),
    }
    data = {
        "name": f"TEST_workflow_{uuid.uuid4().hex[:6]}.txt",
        "tax_year": "FY2025",
        "category": "Other",
        "notes": "test",
        "accountant_review": "No",
    }
    r = requests.post(f"{API_BASE}/documents", files=files, data=data, timeout=60)
    if r.status_code == 400 and "Invalid category" in r.text:
        # Discover a valid category from the categories endpoint
        cr = requests.get(f"{API_BASE}/categories", timeout=20)
        if cr.status_code == 200:
            cats = cr.json()
            if isinstance(cats, list) and cats:
                data["category"] = cats[-1] if isinstance(cats[-1], str) else cats[-1].get("name", cats[-1])
                r = requests.post(f"{API_BASE}/documents", files=files, data=data, timeout=60)
    assert r.status_code in (200, 201), f"create doc failed: {r.status_code} {r.text}"
    body = r.json()
    return body.get("id") or body.get("document_id")
API = f"{BASE_URL}/api"

# Make the backend module importable for pure unit tests on the rules engine.
sys.path.insert(0, "/app/backend")
from bank_transaction_extractor import classify_transaction_by_rules  # noqa: E402


# ----------------------------- Fix 3 — Auto-triage (pure unit) -----------------------------


def _tx(desc, amount_cents, debit_credit="debit", date="2024-08-15"):
    return {
        "description_cleaned": desc,
        "amount_cents": amount_cents,
        "debit_credit": debit_credit,
        "transaction_date": date,
    }


class TestAutoTriage:
    def test_tiny_amount_marked_private_noise(self):
        out = classify_transaction_by_rules(_tx("rounding fee", 5), [])
        assert out["category_suggested"] == "noise_tiny_amount"
        assert out["evidence_status"] == "private"
        assert out["confidence"] == "Confirmed"
        assert out["review_required"] is False
        assert out["accountant_review_required"] is False
        assert out["ai_cost_usd"] == 0.0

    def test_internal_transfer_marked_private(self):
        out = classify_transaction_by_rules(_tx("Transfer to Savings 12345", 50000), [])
        assert out["category_suggested"] == "internal_transfer"
        assert out["evidence_status"] == "private"
        assert out["review_required"] is False

    def test_bank_fee_flagged_for_accountant(self):
        out = classify_transaction_by_rules(_tx("Account Fee $5", 500), [])
        assert out["category_suggested"] == "bank_fee"
        assert out["evidence_status"] == "candidate"
        assert out["accountant_review_required"] is True
        assert out["review_required"] is True

    def test_interest_credit_confirmed_income(self):
        out = classify_transaction_by_rules(
            _tx("Interest Earned credit", 1234, debit_credit="credit"), []
        )
        assert out["category_suggested"] == "interest_income"
        assert out["tax_section_suggested"] == "interest"
        assert out["evidence_status"] == "candidate"
        assert out["confidence"] == "Confirmed"


# ----------------------------- Fix 6 — Empty Rubbish Bin -----------------------------


class TestEmptyRubbishBin:
    def test_empty_bin_idempotent_on_empty_state(self):
        # Drain anything that may already be soft-deleted from prior runs.
        r0 = requests.post(f"{API_BASE}/rubbish-bin/empty", json={}, timeout=30)
        assert r0.status_code == 200
        # A second call must succeed and report all zeros.
        r = requests.post(f"{API_BASE}/rubbish-bin/empty", json={}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["db_deleted"] == 0
        assert body["drive_trashed"] == 0
        assert body["drive_failed"] == []

    def test_soft_delete_then_empty_bin_increments_db_deleted(self):
        doc_id = _create_doc_via_upload()

        # Soft-delete it via the soft-delete endpoint (moves to rubbish bin).
        rd = requests.post(f"{API_BASE}/documents/{doc_id}/delete", json={}, timeout=20)
        assert rd.status_code in (200, 204), rd.text

        # Now empty bin should clear it.
        re = requests.post(f"{API_BASE}/rubbish-bin/empty", json={}, timeout=30)
        assert re.status_code == 200
        body = re.json()
        assert body["db_deleted"] >= 1

        # Verify gone — list rubbish-bin should not contain our id.
        rl = requests.get(f"{API_BASE}/rubbish-bin", timeout=20)
        assert rl.status_code == 200
        assert all(d.get("id") != doc_id for d in rl.json())


# ----------------------------- Fix 9 — accountant_review lockstep -----------------------------


class TestAccountantReviewLockstep:
    def _create_doc(self):
        return _create_doc_via_upload()

    def test_patch_accountant_review_no_clears_and_completes(self):
        doc_id = self._create_doc()
        try:
            r = requests.patch(f"{API_BASE}/documents/{doc_id}", json={"accountant_review": "No"}, timeout=20)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["accountant_review_required"] is False
            assert body.get("accountant_review_reason") in (None, "", None)
            # If not red-risk, status should auto-flip to Complete.
            if body.get("risk_level") != "Red":
                assert body["status"] == "Complete"
        finally:
            requests.delete(f"{API_BASE}/documents/{doc_id}", timeout=20)

    def test_patch_accountant_review_yes_sets_required_and_default_reason(self):
        doc_id = self._create_doc()
        try:
            r = requests.patch(f"{API_BASE}/documents/{doc_id}", json={"accountant_review": "Yes"}, timeout=20)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["accountant_review_required"] is True
            assert body["status"] == "Accountant review"
            assert body["accountant_review_reason"] == "Flagged by user"
        finally:
            requests.delete(f"{API_BASE}/documents/{doc_id}", timeout=20)
