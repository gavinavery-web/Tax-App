"""Phase 1 — Tax Returns as containers. Backend-only smoke tests.

These tests MUST pass without touching existing tests. They use the
FastAPI TestClient against the real app.
"""
import pytest
from fastapi.testclient import TestClient
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_create_tax_return_personal_fy2025(client):
    r = client.post("/api/tax-returns", json={
        "tax_year": "FY2025",
        "return_type": "personal",
        "entity_name": "Gavin Avery",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"].startswith("tr-")
    assert body["tax_year"] == "FY2025"
    assert body["return_type"] == "personal"
    assert body["entity_name"] == "Gavin Avery"
    assert body["status"] == "collecting_evidence"
    assert body["is_deleted"] is False


def test_create_tax_return_invalid_type_rejected(client):
    r = client.post("/api/tax-returns", json={
        "tax_year": "FY2025",
        "return_type": "garbage",
        "entity_name": "X",
    })
    assert r.status_code == 400


def test_create_tax_return_invalid_year_rejected(client):
    r = client.post("/api/tax-returns", json={
        "tax_year": "FY1900",
        "return_type": "personal",
        "entity_name": "X",
    })
    assert r.status_code == 400


def test_create_tax_return_empty_entity_rejected(client):
    r = client.post("/api/tax-returns", json={
        "tax_year": "FY2025",
        "return_type": "personal",
        "entity_name": "   ",
    })
    assert r.status_code == 400


def test_list_and_filter_tax_returns(client):
    # Create a company return for the same year
    r = client.post("/api/tax-returns", json={
        "tax_year": "FY2025",
        "return_type": "company",
        "entity_name": "Revive Drip Hydration Pty Ltd",
    })
    assert r.status_code == 200

    r = client.get("/api/tax-returns?tax_year=FY2025")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 2

    r = client.get("/api/tax-returns?return_type=company")
    assert r.status_code == 200
    assert all(x["return_type"] == "company" for x in r.json())


def test_update_tax_return_status(client):
    r = client.post("/api/tax-returns", json={
        "tax_year": "FY2024", "return_type": "personal", "entity_name": "Test"
    })
    tr_id = r.json()["id"]

    r = client.patch(f"/api/tax-returns/{tr_id}", json={"status": "ready_for_review"})
    assert r.status_code == 200
    assert r.json()["status"] == "ready_for_review"

    r = client.patch(f"/api/tax-returns/{tr_id}", json={"status": "nonsense"})
    assert r.status_code == 400


def test_soft_delete_tax_return(client):
    r = client.post("/api/tax-returns", json={
        "tax_year": "FY2024", "return_type": "personal", "entity_name": "ToDelete"
    })
    tr_id = r.json()["id"]

    r = client.delete(f"/api/tax-returns/{tr_id}")
    assert r.status_code == 200
    assert r.json()["soft_deleted"] is True

    # Not in default list
    r = client.get("/api/tax-returns")
    assert tr_id not in [x["id"] for x in r.json()]

    # Visible with include_deleted
    r = client.get("/api/tax-returns?include_deleted=true")
    assert tr_id in [x["id"] for x in r.json()]


def test_summary_endpoint(client):
    r = client.post("/api/tax-returns", json={
        "tax_year": "FY2025", "return_type": "personal", "entity_name": "Summary Test"
    })
    tr_id = r.json()["id"]
    r = client.get(f"/api/tax-returns/{tr_id}/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["documents_count"] == 0
    assert body["missing_evidence_total"] == 0


def test_assign_documents_endpoint_empty_list_rejected(client):
    r = client.post("/api/tax-returns", json={
        "tax_year": "FY2025", "return_type": "personal", "entity_name": "Assign Test"
    })
    tr_id = r.json()["id"]
    r = client.post(f"/api/tax-returns/{tr_id}/assign-documents", json=[])
    assert r.status_code == 400


def test_existing_documents_endpoint_still_works(client):
    """Regression: existing /api/documents endpoint must still return data."""
    r = client.get("/api/documents")
    assert r.status_code == 200
    # Old documents with no tax_return_id must still load
    body = r.json()
    assert isinstance(body, list)
