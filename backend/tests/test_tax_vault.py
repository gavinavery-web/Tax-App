"""Backend tests for Tax Evidence Vault (Stage 1)."""
import os
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://evidence-vault-54.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def s():
    return requests.Session()


# ---------- Root / Reference / Drive status ----------

def test_root(s):
    r = s.get(f"{API}/")
    assert r.status_code == 200
    data = r.json()
    assert data.get("app") == "Tax Evidence Vault"
    assert data.get("stage") == 1


def test_reference(s):
    r = s.get(f"{API}/reference")
    assert r.status_code == 200
    d = r.json()
    for k in ["categories", "tax_years", "status_options", "priorities", "folder_structure", "category_to_folder"]:
        assert k in d, f"missing key {k}"
    assert "ATO" in d["categories"]
    assert "FY2024" in d["tax_years"] and "FY2025" in d["tax_years"]
    assert "Both" in d["tax_years"] and "Unsure" in d["tax_years"]
    assert "Critical" in d["priorities"]
    assert isinstance(d["folder_structure"], list) and len(d["folder_structure"]) >= 10


def test_drive_status_initial(s):
    # Stage 4.5: refreshed. Drive may be either connected (live dev pod) or
    # disconnected (CI / fresh DB). We just assert the shape of the response.
    r = s.get(f"{API}/drive/status")
    assert r.status_code == 200
    d = r.json()
    assert "connected" in d and "initialized" in d
    assert isinstance(d["connected"], bool)
    assert isinstance(d["initialized"], bool)


def test_drive_connect_url(s):
    r = s.get(f"{API}/drive/connect")
    assert r.status_code == 200
    url = r.json().get("authorization_url", "")
    assert "accounts.google.com" in url
    assert "234143144612" in url
    assert "redirect_uri=" in url
    assert "scope=" in url


# ---------- Missing evidence preload + CRUD ----------

def test_missing_preload_count(s):
    r = s.get(f"{API}/missing-evidence")
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) >= 30, f"expected >=30 preloaded missing items, got {len(items)}"


def test_missing_priority_critical(s):
    r = s.get(f"{API}/missing-evidence", params={"priority": "Critical"})
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 16, f"expected 16 critical, got {len(items)}"


def test_missing_crud(s):
    # CREATE
    payload = {
        "item_needed": "TEST_custom_item",
        "category": "Other",
        "tax_year": "FY2025",
        "priority": "Later",
        "where_to_find": "TEST source",
        "why_matters": "TEST reason",
    }
    r = s.post(f"{API}/missing-evidence", json=payload)
    assert r.status_code == 200
    created = r.json()
    assert created["item_needed"] == "TEST_custom_item"
    assert "id" in created
    item_id = created["id"]

    # Appears in list
    r = s.get(f"{API}/missing-evidence")
    assert any(it["id"] == item_id for it in r.json())

    # PATCH -> Received (Stage 4.5 status, replaces legacy "Found")
    r = s.patch(f"{API}/missing-evidence/{item_id}", json={"status": "Received"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "Received"
    # Stage 4.5: manual edits are flagged so auto-match won't trample them.
    assert body.get("status_source") == "user"

    # DELETE
    r = s.delete(f"{API}/missing-evidence/{item_id}")
    assert r.status_code == 200
    # confirm gone
    r = s.patch(f"{API}/missing-evidence/{item_id}", json={"status": "Not applicable"})
    assert r.status_code == 404


# ---------- Figures preload + CRUD ----------

def test_payg_preload_totals(s):
    r = s.get(f"{API}/figures")
    assert r.status_code == 200
    figs = r.json()
    payg = [f for f in figs if f.get("figure_type") == "payg_income"]
    assert len(payg) >= 6, f"expected 6 payg_income figures, got {len(payg)}"
    fy24 = sum(f["amount"] for f in payg if f.get("tax_year") == "FY2024")
    fy25 = sum(f["amount"] for f in payg if f.get("tax_year") == "FY2025")
    assert fy24 == 27388, f"FY2024 total mismatch: {fy24}"
    assert fy25 == 75863, f"FY2025 total mismatch: {fy25}"


def test_figure_crud(s):
    payload = {
        "figure_type": "income",
        "amount": 1234.56,
        "description": "TEST_figure",
        "source_document": "TEST_src",
        "tax_year": "FY2025",
        "category": "Other",
        "document_id": "fake-doc-id-test",
    }
    r = s.post(f"{API}/figures", json=payload)
    assert r.status_code == 200
    fig = r.json()
    assert fig["amount"] == 1234.56
    assert fig["description"] == "TEST_figure"
    fig_id = fig["id"]

    # filter by document_id
    r = s.get(f"{API}/figures", params={"document_id": "fake-doc-id-test"})
    assert r.status_code == 200
    assert any(f["id"] == fig_id for f in r.json())

    # delete
    r = s.delete(f"{API}/figures/{fig_id}")
    assert r.status_code == 200
    # delete again -> 404
    r = s.delete(f"{API}/figures/{fig_id}")
    assert r.status_code == 404


# ---------- Dashboard ----------

def test_dashboard(s):
    r = s.get(f"{API}/dashboard")
    assert r.status_code == 200
    d = r.json()
    assert "cards" in d
    cards = d["cards"]
    assert isinstance(cards, list) and len(cards) >= 10
    missing_card = next((c for c in cards if c.get("key") == "missing"), None)
    assert missing_card is not None
    # 30 preloaded missing items, none Found
    assert missing_card["documents"] >= 30


# ---------- Documents CRUD (no Drive connection) ----------

def test_document_upload_manual(s):
    # Stage 4.5: refreshed — Drive may or may not be connected. Manual upload
    # endpoint should always create a document record. drive_file_id will be
    # populated iff Drive is connected, else None.
    files = {"file": ("test.txt", io.BytesIO(b"hello tax world"), "text/plain")}
    data = {
        "name": "TEST_doc_manual",
        "tax_year": "FY2024",
        "category": "ATO",
        "notes": "TEST notes",
        "accountant_review": "No",
    }
    r = s.post(f"{API}/documents", files=files, data=data)
    assert r.status_code == 200, f"unexpected status={r.status_code}, body={r.text[:300]}"
    doc = r.json()
    assert doc["name"] == "TEST_doc_manual"
    assert doc["category"] == "ATO"
    assert doc["tax_year"] == "FY2024"
    assert doc["size_bytes"] == len(b"hello tax world")
    assert "id" in doc
    pytest.shared_doc_id = doc["id"]


def test_document_invalid_category(s):
    files = {"file": ("x.txt", io.BytesIO(b"x"), "text/plain")}
    data = {"name": "TEST_bad_cat", "tax_year": "FY2024", "category": "NotARealCategory"}
    r = s.post(f"{API}/documents", files=files, data=data)
    assert r.status_code == 400


def test_document_invalid_tax_year(s):
    files = {"file": ("x.txt", io.BytesIO(b"x"), "text/plain")}
    data = {"name": "TEST_bad_ty", "tax_year": "FY2099", "category": "ATO"}
    r = s.post(f"{API}/documents", files=files, data=data)
    assert r.status_code == 400


def test_document_list_filter_category(s):
    r = s.get(f"{API}/documents", params={"category": "ATO"})
    assert r.status_code == 200
    docs = r.json()
    assert isinstance(docs, list)
    assert all(d["category"] == "ATO" for d in docs)


def test_document_list_filter_tax_year(s):
    # Add a "Both" doc to verify FY2024 filter includes Both
    files = {"file": ("both.txt", io.BytesIO(b"b"), "text/plain")}
    data = {"name": "TEST_both_doc", "tax_year": "Both", "category": "Other"}
    r = s.post(f"{API}/documents", files=files, data=data)
    assert r.status_code == 200
    both_id = r.json()["id"]

    r = s.get(f"{API}/documents", params={"tax_year": "FY2024"})
    assert r.status_code == 200
    docs = r.json()
    tys = {d["tax_year"] for d in docs}
    assert tys.issubset({"FY2024", "Both"})
    assert any(d["id"] == both_id for d in docs)

    # cleanup
    s.delete(f"{API}/documents/{both_id}")


def test_document_patch_and_delete(s):
    doc_id = getattr(pytest, "shared_doc_id", None)
    assert doc_id, "previous upload test must have run"
    r = s.patch(f"{API}/documents/{doc_id}", json={"notes": "UPDATED_NOTES", "status": "Analysed"})
    assert r.status_code == 200
    body = r.json()
    assert body["notes"] == "UPDATED_NOTES"
    assert body["status"] == "Analysed"

    # GET single
    r = s.get(f"{API}/documents/{doc_id}")
    assert r.status_code == 200
    assert r.json()["notes"] == "UPDATED_NOTES"

    # DELETE
    r = s.delete(f"{API}/documents/{doc_id}")
    assert r.status_code == 200
    r = s.get(f"{API}/documents/{doc_id}")
    assert r.status_code == 404


# ---------- Reports ----------

def test_evidence_register_csv(s):
    r = s.get(f"{API}/reports/evidence-register.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    body = r.text
    assert "Document name" in body and "Tax year" in body


def test_missing_evidence_csv(s):
    r = s.get(f"{API}/reports/missing-evidence.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    lines = r.text.strip().splitlines()
    # 1 header + at least 30 data rows
    assert len(lines) >= 31, f"got {len(lines)} lines"
    assert "Item needed" in lines[0]


def test_documents_by_category_csv(s):
    r = s.get(f"{API}/reports/documents-by-category.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert "Category" in r.text


def test_accountant_pdf(s):
    r = s.get(f"{API}/reports/accountant-summary.pdf")
    assert r.status_code == 200
    assert "application/pdf" in r.headers.get("content-type", "")
    assert r.content.startswith(b"%PDF"), "not a valid PDF"


# ---------- Seed idempotency ----------

def test_seed_missing_idempotent(s):
    r = s.post(f"{API}/seed/missing-evidence")
    assert r.status_code == 200
    d = r.json()
    assert d.get("skipped") is True
    assert d.get("existing", 0) >= 30


def test_seed_payg_idempotent(s):
    r = s.post(f"{API}/seed/payg-income")
    assert r.status_code == 200
    d = r.json()
    assert d.get("skipped") is True
    assert d.get("existing", 0) >= 6
