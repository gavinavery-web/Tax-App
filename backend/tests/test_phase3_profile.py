"""Phase 3 — profile wizard & dynamic missing-evidence generator.

Tests run against the live backend at REACT_APP_BACKEND_URL/api (matching
the dominant pattern in this repo) to avoid the cross-module TestClient
+ motor event-loop lifecycle issue (motor's loop is closed once an earlier
TestClient module tears down its lifespan).
"""
import os
import pytest
import requests

API = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/") + "/api"


def _create_personal_fy2025(name="Profile Test"):
    r = requests.post(f"{API}/tax-returns", json={
        "tax_year": "FY2025", "return_type": "personal", "entity_name": name
    })
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def created_returns():
    """Yield a list to which test code appends ids; teardown soft-deletes the
    tax returns AND removes any missing_items the test generated for them.
    We only delete items WE created in this test module (keyed by
    tax_return_id) — original seeded items are left untouched."""
    from pymongo import MongoClient
    ids: list[str] = []
    yield ids
    if not ids:
        return
    sync_client = MongoClient(os.environ["MONGO_URL"])
    try:
        sync_db = sync_client[os.environ["DB_NAME"]]
        sync_db.missing_items.delete_many({"tax_return_id": {"$in": ids}})
    finally:
        sync_client.close()
    for tr_id in ids:
        try:
            requests.delete(f"{API}/tax-returns/{tr_id}", timeout=5)
        except Exception:
            pass


def test_profile_questions_for_personal(created_returns):
    tr = _create_personal_fy2025("Questions Test")
    created_returns.append(tr["id"])
    r = requests.get(f"{API}/tax-returns/{tr['id']}/profile-questions")
    assert r.status_code == 200
    body = r.json()
    assert "groups" in body
    assert len(body["groups"]) >= 3


def test_generate_checklist_creates_items(created_returns):
    tr = _create_personal_fy2025("Generator Test")
    created_returns.append(tr["id"])
    requests.patch(f"{API}/tax-returns/{tr['id']}", json={
        "profile_answers": {
            "has_payg": True,
            "has_rental_income": True,
            "has_airbnb": True,
            "claim_car": True,
            "car_has_logbook": False,
            "claim_phone_internet": True,
            "claim_wfh": True,
            "wfh_method": "fixed_rate",
        }
    })
    r = requests.post(f"{API}/tax-returns/{tr['id']}/generate-evidence-checklist", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] > 5

    items = requests.get(f"{API}/missing-evidence").json()
    return_items = [i for i in items if i.get("tax_return_id") == tr["id"]]
    assert len(return_items) > 5


def test_generator_idempotent(created_returns):
    tr = _create_personal_fy2025("Idempotency Test")
    created_returns.append(tr["id"])
    requests.patch(f"{API}/tax-returns/{tr['id']}", json={
        "profile_answers": {"has_payg": True, "has_bank_interest": True}
    })

    r1 = requests.post(f"{API}/tax-returns/{tr['id']}/generate-evidence-checklist", json={}).json()
    r2 = requests.post(f"{API}/tax-returns/{tr['id']}/generate-evidence-checklist", json={}).json()

    assert r1["created"] >= 1
    assert r2["created"] == 0  # second run creates nothing
    assert r2["skipped_existing"] >= 1


def test_existing_seeded_items_untouched():
    """Regression: original 30 seeded missing items must still exist."""
    items = requests.get(f"{API}/missing-evidence").json()
    seeded = [i for i in items if i.get("generated_by", "seed") == "seed" or i.get("tax_return_id") is None]
    assert len(seeded) >= 25


def test_user_managed_items_not_overwritten(created_returns):
    """Items with status_source='user' must never be overwritten by the generator."""
    from pymongo import MongoClient

    tr = _create_personal_fy2025("User-Managed Protect")
    created_returns.append(tr["id"])
    requests.patch(f"{API}/tax-returns/{tr['id']}", json={"profile_answers": {"has_payg": True}})

    r1 = requests.post(f"{API}/tax-returns/{tr['id']}/generate-evidence-checklist", json={}).json()
    assert r1["created"] >= 1

    sync_client = MongoClient(os.environ["MONGO_URL"])
    try:
        sync_db = sync_client[os.environ["DB_NAME"]]
        sync_db.missing_items.update_one(
            {"tax_return_id": tr["id"], "profile_rule_key": "payg_income_statements"},
            {"$set": {"status_source": "user", "notes": "manually overridden"}},
        )
    finally:
        sync_client.close()

    r2 = requests.post(f"{API}/tax-returns/{tr['id']}/generate-evidence-checklist", json={}).json()
    assert r2["created"] == 0
    assert r2["skipped_user_managed"] >= 1


def test_company_return_has_different_questions(created_returns):
    r = requests.post(f"{API}/tax-returns", json={
        "tax_year": "FY2025", "return_type": "company", "entity_name": "Co Test"
    })
    assert r.status_code == 200, r.text
    tr = r.json()
    created_returns.append(tr["id"])

    r = requests.get(f"{API}/tax-returns/{tr['id']}/profile-questions")
    body = r.json()
    keys = [q["key"] for g in body["groups"] for q in g["questions"]]
    assert "gst_registered" in keys
    assert "has_payg" not in keys  # personal-only
