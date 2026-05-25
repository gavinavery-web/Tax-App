"""Stage 7 Phase 3 — Tax Builder + Deletion + Properties.

Covers:
  - manual tax-return items with source linking
  - usage-count increment/decrement is atomic
  - soft delete / restore / rubbish-bin listing
  - permanent delete blocked by claims, allowed once unused
  - properties CRUD + use-period add/remove
  - validation errors return useful 4xx
"""
from __future__ import annotations

import io
import os
import sys
import uuid

import pytest
import requests

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://evidence-vault-54.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# --- helper: make a "fake" document straight into MongoDB via an
# upload-pipeline staging flow is heavy; we use the manual document
# upload endpoint with a tiny PDF-ish payload. The classifier may flag
# it as Inbox/Red, that's fine — we only need a row with a stable `id`.
# Even simpler: we hit the FastAPI directly with an upload to /documents
# via the multipart endpoint. The existing test suite (test_tax_vault.py)
# does the same dance.
def _make_doc(s, name="Phase 3 test doc.pdf"):
    files = {"file": (name, io.BytesIO(b"%PDF-1.4\n test phase3"), "application/pdf")}
    data = {
        "name": name,
        "tax_year": "FY2024",
        "category": "Other",
        "accountant_review": "No",
        "notes": "phase3 test fixture",
    }
    r = s.post(f"{API}/documents", files=files, data=data)
    assert r.status_code == 200, r.text
    return r.json()


# ============================================================================
# Tax return items
# ============================================================================

def test_tax_year_summary_initially(s):
    r = s.get(f"{API}/tax-years/FY2024")
    assert r.status_code == 200
    body = r.json()
    assert body["tax_year"] == "FY2024"
    assert "total_income_cents" in body
    assert "sections" in body


def test_create_manual_tax_item_with_source(s):
    doc = _make_doc(s, name=f"phase3-{uuid.uuid4().hex[:6]}.pdf")
    payload = {
        "tax_year": "FY2024",
        "section": "work_related_car",
        "amount_cents": 12345,
        "description": "Phase 3 manual claim",
        "income_or_deduction": "deduction",
        "source_document_id": doc["id"],
        "notes": "added by pytest",
    }
    r = s.post(f"{API}/tax-return-items", json=payload)
    assert r.status_code == 200, r.text
    item_id = r.json()["item_id"]
    assert item_id

    # Document usage count should be 1 and evidence_status="used"
    d = s.get(f"{API}/documents/{doc['id']}").json()
    assert d["used_in_claims_count"] == 1
    assert d["evidence_status"] == "used"

    # Year summary should now reflect the deduction
    summary = s.get(f"{API}/tax-years/FY2024").json()
    assert summary["total_deductions_cents"] >= 12345
    sec_names = {sec["section_name"] for sec in summary["sections"]}
    assert "work_related_car" in sec_names

    # Cleanup
    r = s.delete(f"{API}/tax-return-items/{item_id}")
    assert r.status_code == 200
    d2 = s.get(f"{API}/documents/{doc['id']}").json()
    assert d2["used_in_claims_count"] == 0
    assert d2["evidence_status"] == "unused"

    # cleanup test doc
    s.delete(f"{API}/documents/{doc['id']}")


def test_manual_item_validation_errors(s):
    # missing fields
    r = s.post(f"{API}/tax-return-items", json={"tax_year": "FY2024"})
    assert r.status_code == 400
    # bad section
    r = s.post(f"{API}/tax-return-items", json={
        "tax_year": "FY2024", "section": "bogus", "amount_cents": 100,
        "description": "x", "income_or_deduction": "deduction",
    })
    assert r.status_code == 400
    # bad income_or_deduction
    r = s.post(f"{API}/tax-return-items", json={
        "tax_year": "FY2024", "section": "donations", "amount_cents": 100,
        "description": "x", "income_or_deduction": "maybe",
    })
    assert r.status_code == 400
    # bad amount_cents type
    r = s.post(f"{API}/tax-return-items", json={
        "tax_year": "FY2024", "section": "donations", "amount_cents": "abc",
        "description": "x", "income_or_deduction": "deduction",
    })
    assert r.status_code == 400
    # bad source_document_id
    r = s.post(f"{API}/tax-return-items", json={
        "tax_year": "FY2024", "section": "donations", "amount_cents": 100,
        "description": "x", "income_or_deduction": "deduction",
        "source_document_id": "does-not-exist",
    })
    assert r.status_code == 404


# ============================================================================
# Deletion / Rubbish bin
# ============================================================================

def test_soft_delete_restore_cycle(s):
    doc = _make_doc(s, name=f"del-{uuid.uuid4().hex[:6]}.pdf")
    did = doc["id"]

    # Soft delete
    r = s.post(f"{API}/documents/{did}/delete", json={"reason": "test"})
    assert r.status_code == 200

    # List default should not include it
    listed = s.get(f"{API}/documents").json()
    assert all(d["id"] != did for d in listed)

    # Rubbish bin should include it
    bin_list = s.get(f"{API}/rubbish-bin").json()
    assert any(d["id"] == did for d in bin_list)

    # Restore
    r = s.post(f"{API}/documents/{did}/restore")
    assert r.status_code == 200

    # Visible again
    listed = s.get(f"{API}/documents").json()
    assert any(d["id"] == did for d in listed)

    # final cleanup
    s.delete(f"{API}/documents/{did}")


def test_permanent_delete_blocks_when_claimed(s):
    doc = _make_doc(s, name=f"perm-{uuid.uuid4().hex[:6]}.pdf")
    did = doc["id"]

    # Create a claim referencing this doc
    r = s.post(f"{API}/tax-return-items", json={
        "tax_year": "FY2024", "section": "donations",
        "amount_cents": 500, "description": "blocks deletion",
        "income_or_deduction": "deduction",
        "source_document_id": did,
    })
    item_id = r.json()["item_id"]

    # Soft delete first
    s.post(f"{API}/documents/{did}/delete", json={"reason": "test"})

    # Permanent delete must be blocked
    r = s.delete(f"{API}/documents/{did}/permanent")
    assert r.status_code == 409, r.text
    assert "claim" in r.json()["detail"].lower()

    # Remove the claim → now permanent delete should succeed
    s.delete(f"{API}/tax-return-items/{item_id}")
    r = s.delete(f"{API}/documents/{did}/permanent")
    assert r.status_code == 200
    assert r.json()["success"] is True

    # Doc actually gone
    r = s.get(f"{API}/documents/{did}")
    assert r.status_code == 404


def test_permanent_delete_requires_rubbish_bin(s):
    doc = _make_doc(s, name=f"live-{uuid.uuid4().hex[:6]}.pdf")
    did = doc["id"]
    r = s.delete(f"{API}/documents/{did}/permanent")
    assert r.status_code == 409
    assert "rubbish bin" in r.json()["detail"].lower()
    # cleanup
    s.delete(f"{API}/documents/{did}")


# ============================================================================
# Properties
# ============================================================================

def test_property_seeded_defaults(s):
    props = s.get(f"{API}/properties").json()
    names = {p["property_name"] for p in props}
    assert {"Heathridge", "Waggrakine"}.issubset(names)


def test_property_add_period_and_remove(s):
    # use the seeded Heathridge prop
    pid = "prop-heathridge"
    # add a rental period
    r = s.post(f"{API}/properties/{pid}/periods", json={
        "date_from": "2023-07-01",
        "date_to": "2024-06-30",
        "use_type": "rental",
        "notes": "FY2024 rental window",
    })
    assert r.status_code == 200, r.text
    prop = s.get(f"{API}/properties/{pid}").json()
    rentals = [p for p in prop["use_periods"] if p["use_type"] == "rental"]
    assert len(rentals) >= 1
    period_id = rentals[-1]["period_id"]

    # remove it
    r = s.delete(f"{API}/properties/{pid}/periods/{period_id}")
    assert r.status_code == 200


def test_property_period_validation(s):
    # bad use_type
    r = s.post(f"{API}/properties/prop-heathridge/periods", json={
        "date_from": "2024-01-01", "use_type": "bogus",
    })
    assert r.status_code == 400
    # bad date
    r = s.post(f"{API}/properties/prop-heathridge/periods", json={
        "date_from": "not-a-date", "use_type": "rental",
    })
    assert r.status_code == 400
    # missing fields
    r = s.post(f"{API}/properties/prop-heathridge/periods", json={})
    assert r.status_code == 400
    # unknown property
    r = s.post(f"{API}/properties/no-such-prop/periods", json={
        "date_from": "2024-01-01", "use_type": "rental",
    })
    assert r.status_code == 404


def test_create_property_and_duplicate(s):
    name = f"Test-Property-{uuid.uuid4().hex[:6]}"
    r = s.post(f"{API}/properties", json={"property_name": name, "address": "Test St"})
    assert r.status_code == 200
    new_id = r.json()["property_id"]

    # duplicate name should 409
    r = s.post(f"{API}/properties", json={"property_name": name})
    assert r.status_code == 409

    # cleanup via mongo through API: no DELETE endpoint exists for properties,
    # so we leave the test property in the DB (it's named with a uuid suffix
    # and won't collide). This keeps the property_manager surface area small.
    assert new_id
