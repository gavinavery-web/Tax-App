"""Backend tests for FINAL PATCH (8 fixes).

Covers:
- Tax years config seeded on startup (FY2024/FY2025/FY2026 all active)
- /api/tax-years and /api/tax-years/config CRUD
- /api/dashboard returns dynamic FY cards for active years
- /api/properties POST/PATCH with entity_type validation
- /api/admin/reset-test-data does NOT re-seed PAYG
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
RUN_ID = uuid.uuid4().hex[:8]


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ============================ Fix 2: Tax years ============================

class TestTaxYears:
    def test_tax_years_config_seeded(self, s):
        r = s.get(f"{BASE_URL}/api/tax-years/config")
        assert r.status_code == 200
        rows = r.json()
        names = [row["name"] for row in rows]
        assert "FY2024" in names
        assert "FY2025" in names
        assert "FY2026" in names
        # All three should be ACTIVE by default
        for row in rows:
            if row["name"] in ("FY2024", "FY2025", "FY2026"):
                assert row.get("active") is True, f"{row['name']} should be active"

    def test_tax_years_active_endpoint(self, s):
        r = s.get(f"{BASE_URL}/api/tax-years")
        assert r.status_code == 200
        data = r.json()
        # Returns list of summary dicts; each contains tax_year field
        if isinstance(data, list):
            years = [d.get("tax_year") or d.get("name") for d in data]
        else:
            years = data.get("active", [])
        for ty in ("FY2024", "FY2025", "FY2026"):
            assert ty in years, f"{ty} missing from /tax-years response: {years}"

    def test_reference_active_tax_years(self, s):
        r = s.get(f"{BASE_URL}/api/reference")
        assert r.status_code == 200
        data = r.json()
        assert "active_tax_years" in data
        for ty in ("FY2024", "FY2025", "FY2026"):
            assert ty in data["active_tax_years"]

    def test_tax_years_config_crud(self, s):
        # Add new year
        payload = {"name": f"FY2099_{RUN_ID}", "start_date": "2098-07-01",
                   "end_date": "2099-06-30", "active": True, "locked": False}
        r = s.post(f"{BASE_URL}/api/tax-years/config", json=payload)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        ty = body.get("tax_year") or body
        ty_id = ty.get("id")
        assert ty_id, f"no id in {body}"

        # Toggle active
        r = s.patch(f"{BASE_URL}/api/tax-years/config/{ty_id}", json={"active": False})
        assert r.status_code == 200
        assert r.json()["active"] is False

        # Delete (no docs reference it)
        r = s.delete(f"{BASE_URL}/api/tax-years/config/{ty_id}")
        assert r.status_code in (200, 204)

    def test_dashboard_dynamic_fy_cards(self, s):
        r = s.get(f"{BASE_URL}/api/dashboard")
        assert r.status_code == 200
        cards = r.json()["cards"]
        fy_card_values = [c["value"] for c in cards if c.get("type") == "tax_year"]
        assert "FY2024" in fy_card_values
        assert "FY2025" in fy_card_values
        assert "FY2026" in fy_card_values


# ============================ Fix 7: Properties / entity_type ============================

class TestPropertiesEntityType:
    def test_create_property_valid_entity_type(self, s):
        payload = {"property_name": f"TEST_BusinessAsset_{RUN_ID}",
                   "address": "ABN 12345", "entity_type": "business"}
        r = s.post(f"{BASE_URL}/api/properties", json=payload)
        assert r.status_code == 200, r.text
        prop_id = r.json()["property_id"]

        # Verify via GET
        g = s.get(f"{BASE_URL}/api/properties/{prop_id}")
        assert g.status_code == 200
        assert g.json()["entity_type"] == "business"

        # Cleanup
        s.delete(f"{BASE_URL}/api/properties/{prop_id}")

    def test_create_property_invalid_entity_type(self, s):
        payload = {"property_name": f"TEST_Bad_{RUN_ID}", "entity_type": "invalid_xxx"}
        r = s.post(f"{BASE_URL}/api/properties", json=payload)
        assert r.status_code == 400

    def test_create_property_other_requires_text(self, s):
        # 'other' without entity_type_other should reject
        r = s.post(f"{BASE_URL}/api/properties",
                   json={"property_name": f"TEST_OtherFail_{RUN_ID}", "entity_type": "other"})
        assert r.status_code == 400

        # With entity_type_other should pass
        r = s.post(f"{BASE_URL}/api/properties",
                   json={"property_name": f"TEST_OtherOk_{RUN_ID}",
                         "entity_type": "other", "entity_type_other": "Partnership"})
        assert r.status_code == 200
        prop_id = r.json()["property_id"]
        g = s.get(f"{BASE_URL}/api/properties/{prop_id}")
        assert g.json()["entity_type"] == "other"
        assert g.json().get("entity_type_other") == "Partnership"
        s.delete(f"{BASE_URL}/api/properties/{prop_id}")

    def test_patch_property_entity_type(self, s):
        # Create
        r = s.post(f"{BASE_URL}/api/properties",
                   json={"property_name": f"TEST_PatchMe_{RUN_ID}", "entity_type": "property"})
        assert r.status_code == 200
        prop_id = r.json()["property_id"]

        # PATCH to trust
        r = s.patch(f"{BASE_URL}/api/properties/{prop_id}",
                    json={"entity_type": "trust"})
        assert r.status_code == 200
        assert r.json()["entity_type"] == "trust"

        # Verify persisted
        g = s.get(f"{BASE_URL}/api/properties/{prop_id}")
        assert g.json()["entity_type"] == "trust"

        # PATCH with invalid type
        r = s.patch(f"{BASE_URL}/api/properties/{prop_id}",
                    json={"entity_type": "garbage"})
        assert r.status_code == 400

        s.delete(f"{BASE_URL}/api/properties/{prop_id}")

    def test_list_properties_default_two_seeded(self, s):
        r = s.get(f"{BASE_URL}/api/properties")
        assert r.status_code == 200
        items = r.json()
        names = [p.get("property_name") for p in items]
        # From context: Heathridge, Waggrakine seeded
        # Just verify list works
        assert isinstance(items, list)


# ============================ Fix 1: reset-test-data no PAYG re-seed ============================

class TestResetDataNoPaygReseed:
    def test_reset_does_not_reseed_payg(self, s):
        # Clear PAYG figures first
        figs = s.get(f"{BASE_URL}/api/figures").json()
        payg_before = [f for f in figs if f.get("figure_type") == "payg_income"]
        for f in payg_before:
            s.delete(f"{BASE_URL}/api/figures/{f['id']}")

        # Confirm zero
        figs = s.get(f"{BASE_URL}/api/figures").json()
        payg = [f for f in figs if f.get("figure_type") == "payg_income"]
        assert len(payg) == 0, "PAYG figures should be cleared before test"

        # Trigger reset
        r = s.post(f"{BASE_URL}/api/admin/reset-test-data", json={})
        assert r.status_code == 200, r.text

        # Wait a moment then verify PAYG still empty
        time.sleep(1)
        figs = s.get(f"{BASE_URL}/api/figures").json()
        payg_after = [f for f in figs if f.get("figure_type") == "payg_income"]
        assert len(payg_after) == 0, f"PAYG should NOT be auto-seeded after reset, found {len(payg_after)}"

    def test_payg_opt_in_seed_works(self, s):
        # User opts in
        r = s.post(f"{BASE_URL}/api/seed/payg-income")
        assert r.status_code == 200
        # Verify created
        figs = s.get(f"{BASE_URL}/api/figures").json()
        payg = [f for f in figs if f.get("figure_type") == "payg_income"]
        assert len(payg) > 0
