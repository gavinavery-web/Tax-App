"""Phase 4 — workspace, document questions, rules engine, profile-match pass.

Tests run against the live backend at REACT_APP_BACKEND_URL/api (same pattern
as Phase 3) so motor's event loop is never recreated between modules.
"""
import os
import pytest
import requests
from dotenv import load_dotenv

# Load backend/.env so MONGO_URL / DB_NAME are available for direct
# mongo seeding/cleanup in tests.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

API = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/") + "/api"


@pytest.fixture
def created_returns():
    from pymongo import MongoClient
    ids: list[str] = []
    yield ids
    if not ids:
        return
    sync = MongoClient(os.environ["MONGO_URL"])
    try:
        db = sync[os.environ["DB_NAME"]]
        db.missing_items.delete_many({"tax_return_id": {"$in": ids}})
    finally:
        sync.close()
    for tr_id in ids:
        try:
            requests.delete(f"{API}/tax-returns/{tr_id}", timeout=5)
        except Exception:
            pass


def _new_personal(name="Phase 4 Test"):
    r = requests.post(f"{API}/tax-returns", json={
        "tax_year": "FY2025", "return_type": "personal", "entity_name": name,
    })
    assert r.status_code == 200, r.text
    return r.json()


# ---- Tax Rules Engine ----

def test_car_cpk_fy2025():
    r = requests.post(f"{API}/tax-rules/calculate/car-cents-per-km",
                      json={"tax_year": "FY2025", "km": 3000})
    body = r.json()
    assert body["ok"] is True
    assert body["rate"] == 0.88
    assert body["effective_km"] == 3000
    assert body["draft_amount"] == 2640.0
    assert body["accountant_review_required"] is True


def test_car_cpk_caps_at_5000():
    r = requests.post(f"{API}/tax-rules/calculate/car-cents-per-km",
                      json={"tax_year": "FY2025", "km": 10000})
    body = r.json()
    assert body["effective_km"] == 5000
    assert body["draft_amount"] == 4400.0


def test_wfh_fy2025():
    r = requests.post(f"{API}/tax-rules/calculate/wfh-fixed-rate",
                      json={"tax_year": "FY2025", "hours": 100})
    body = r.json()
    assert body["rate"] == 0.70
    assert body["draft_amount"] == 70.0


def test_phone_apportionment():
    r = requests.post(f"{API}/tax-rules/calculate/phone-internet",
                      json={"bill_amount": 100, "work_use_percent": 40})
    body = r.json()
    assert body["draft_amount"] == 40.0
    assert body["accountant_review_required"] is False
    r2 = requests.post(f"{API}/tax-rules/calculate/phone-internet",
                       json={"bill_amount": 100, "work_use_percent": 80})
    assert r2.json()["accountant_review_required"] is True


def test_work_expense_threshold():
    r = requests.get(f"{API}/tax-rules/threshold/work-expenses/FY2025")
    body = r.json()
    assert body["ok"] is True
    assert body["threshold"] == 300


def test_unknown_rule_year():
    r = requests.get(f"{API}/tax-rules/car_cents_per_km/FY1900")
    assert r.status_code == 404


# ---- Document Questions ----

def test_unanswered_questions_endpoint(created_returns):
    tr = _new_personal("Question Test")
    created_returns.append(tr["id"])
    r = requests.get(f"{API}/tax-returns/{tr['id']}/unanswered-questions")
    assert r.status_code == 200
    assert "documents_with_questions" in r.json()


def test_answer_question_404_when_doc_missing():
    r = requests.patch(
        f"{API}/documents/nonexistent/questions/work_use_percent",
        json={"key": "work_use_percent", "answer": 40},
    )
    assert r.status_code == 404


# ---- Summary inbox count fix ----

def test_summary_returns_expected_shape(created_returns):
    tr = _new_personal("Summary Test")
    created_returns.append(tr["id"])
    r = requests.get(f"{API}/tax-returns/{tr['id']}/summary")
    body = r.json()
    assert "documents_count" in body
    assert "inbox_count" in body
    assert "missing_evidence_open" in body
    assert body["documents_count"] == 0
    assert body["inbox_count"] == 0


# ---- Regression: existing endpoints still respond ----

def test_existing_documents_endpoint():
    r = requests.get(f"{API}/documents")
    assert r.status_code == 200


def test_existing_missing_evidence_endpoint():
    r = requests.get(f"{API}/missing-evidence")
    assert r.status_code == 200


# ---- Phase 4 FIX C — profile auto-match second pass ----

def test_profile_item_flips_to_possible_match_on_upload(created_returns):
    """End-to-end FIX C check: after a Synergy upload reaches a return that
    has a profile-generated 'electricity' item, the item flips to
    'Possible Match'. Uses direct DB seed of a profile item + a real upload."""
    from pymongo import MongoClient
    import time, hashlib

    tr = _new_personal("FIX C Test")
    created_returns.append(tr["id"])

    sync = MongoClient(os.environ["MONGO_URL"])
    try:
        db = sync[os.environ["DB_NAME"]]
        # Seed a profile-generated missing item that should match an electricity bill
        db.missing_items.insert_one({
            "id": "fixc-test-item",
            "item_needed": "Synergy electricity bill for rental",
            "category": "05 Heathridge",
            "tax_year": "FY2025",
            "priority": "Critical",
            "where_to_find": "Synergy portal",
            "why_matters": "Deductible rental expense",
            "status": "Outstanding",
            "notes": "",
            "tax_return_id": tr["id"],
            "generated_by": "profile",
            "profile_rule_key": "rental_property_evidence",
        })
    finally:
        sync.close()

    # Upload a synergy bill — code triage assigns category=05 Heathridge,
    # doc_type=utility_electricity, links to this tax_return (only open FY2025
    # personal during this test — assuming other returns archived/non-personal).
    # Create a minimal PDF using reportlab.
    from reportlab.pdfgen import canvas
    pdf_path = "/tmp/fixc_synergy_2025-03-15.pdf"
    c = canvas.Canvas(pdf_path)
    c.drawString(100, 750, "Synergy electricity statement March 2025")
    c.save()

    # Make sure no other open FY2025 returns interfere with routing.
    # Stash any pre-existing open FY2025 return as ready_for_accountant so
    # the new one is the ONLY candidate (any return_type — personal AND
    # company both compete with each other in find_matching_return).
    sync = MongoClient(os.environ["MONGO_URL"])
    try:
        db = sync[os.environ["DB_NAME"]]
        db.tax_returns.update_many(
            {"tax_year": "FY2025",
             "status": {"$in": ["collecting_evidence", "ready_for_review"]},
             "id": {"$ne": tr["id"]}, "is_deleted": {"$ne": True}},
            {"$set": {"_phase4_stash_status": True, "status": "ready_for_accountant"}},
        )
    finally:
        sync.close()

    try:
        with open(pdf_path, "rb") as fh:
            up = requests.post(f"{API}/uploads/bulk", files={"files": ("fixc_synergy_2025-03-15.pdf", fh, "application/pdf")})
        assert up.status_code == 200, up.text

        # Wait for the background classifier to finish
        for _ in range(30):
            sync = MongoClient(os.environ["MONGO_URL"])
            try:
                db = sync[os.environ["DB_NAME"]]
                doc = db.documents.find_one({"sha256": hashlib.sha256(open(pdf_path, "rb").read()).hexdigest()})
                if doc and doc.get("category") == "05 Heathridge":
                    break
            finally:
                sync.close()
            time.sleep(1)

        # Assert the missing item flipped
        sync = MongoClient(os.environ["MONGO_URL"])
        try:
            db = sync[os.environ["DB_NAME"]]
            item = db.missing_items.find_one({"id": "fixc-test-item"})
            assert item is not None
            assert item["status"] == "Possible Match", f"got {item['status']}, matched_doc_id={item.get('matched_document_id')}"
            assert item.get("matched_document_id") is not None
            # Cleanup
            db.documents.delete_many({"sha256": hashlib.sha256(open(pdf_path, "rb").read()).hexdigest()})
            db.upload_queue.delete_many({"filename": "fixc_synergy_2025-03-15.pdf"})
            db.missing_items.delete_one({"id": "fixc-test-item"})
        finally:
            sync.close()
    finally:
        # Restore any tax returns we stashed
        sync = MongoClient(os.environ["MONGO_URL"])
        try:
            db = sync[os.environ["DB_NAME"]]
            db.tax_returns.update_many(
                {"_phase4_stash_status": True},
                {"$set": {"status": "collecting_evidence"}, "$unset": {"_phase4_stash_status": ""}},
            )
        finally:
            sync.close()
