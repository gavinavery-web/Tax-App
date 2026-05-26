"""Phase 2 — date routing + code triage. Pure unit tests, no DB required."""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from code_triage import (
    extract_document_date,
    date_to_financial_year,
    classify_by_rules,
    CODE_TRIAGE_THRESHOLD,
)


# ---- Date extraction ----

@pytest.mark.parametrize("fn,expected_iso,min_conf", [
    ("synergy_2025-03-15.pdf", "2025-03-15", "high"),
    ("synergy 15-03-2025.pdf", "2025-03-15", "high"),
    ("payg_03-2025.pdf",       "2025-03-15", "medium"),
    ("airbnb_march_2025.pdf",  "2025-03-15", "medium"),
    ("statement_2025.pdf",     "2025-06-30", "low"),
])
def test_extract_date_from_filename(fn, expected_iso, min_conf):
    iso, conf = extract_document_date(fn, "")
    assert iso == expected_iso
    assert conf in {"high", "medium", "low"}


def test_no_date_returns_none():
    iso, conf = extract_document_date("random.pdf", "no date in body")
    assert iso is None
    assert conf == "none"


# ---- FY mapping ----

def test_fy_mapping_australian():
    assert date_to_financial_year("2024-07-01") == "FY2025"
    assert date_to_financial_year("2024-06-30") == "FY2024"
    assert date_to_financial_year("2025-03-15") == "FY2025"
    assert date_to_financial_year("2023-12-01") == "FY2024"


def test_fy_mapping_bad_input():
    assert date_to_financial_year("garbage") is None
    assert date_to_financial_year(None) is None


# ---- Rules ----

def test_synergy_filename_matches():
    hit = classify_by_rules("synergy_2025-03.pdf", "")
    assert hit is not None
    assert hit["category"] == "05 Heathridge"
    assert hit["confidence"] >= CODE_TRIAGE_THRESHOLD


def test_airbnb_filename_matches():
    hit = classify_by_rules("Airbnb_annual_2025.pdf", "some text")
    assert hit is not None
    assert hit["category"] == "03 Airbnb"


def test_unknown_returns_none():
    hit = classify_by_rules("random_doc.pdf", "nothing recognisable in body")
    assert hit is None


def test_text_fallback():
    hit = classify_by_rules("scan_001.pdf", "Account holder: Synergy energy bill for March")
    assert hit is not None
    assert hit["source"] == "text"
