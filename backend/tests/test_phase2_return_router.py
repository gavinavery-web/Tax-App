"""Phase 2 — return_router unit tests using a mock db."""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from return_router import find_matching_return, infer_return_type_hint


class _MockCursor:
    def __init__(self, rows): self._rows = rows
    async def to_list(self, n): return self._rows[:n]


class _MockCollection:
    def __init__(self, rows): self._rows = rows
    def find(self, *_a, **_k): return _MockCursor(self._rows)


class _MockDB:
    def __init__(self, returns): self.tax_returns = _MockCollection(returns)


@pytest.mark.asyncio
async def test_no_fy_needs_assignment():
    db = _MockDB([])
    r = await find_matching_return(db, None, None)
    assert r["needs_assignment"] is True
    assert r["tax_return_id"] is None


@pytest.mark.asyncio
async def test_no_open_return_for_year():
    db = _MockDB([])
    r = await find_matching_return(db, "2022-03-15", "FY2022")
    assert r["needs_assignment"] is True
    assert r["tax_year"] == "FY2022"


@pytest.mark.asyncio
async def test_single_return_matches():
    db = _MockDB([
        {"id": "tr-abc", "tax_year": "FY2025", "return_type": "personal", "status": "collecting_evidence"}
    ])
    r = await find_matching_return(db, "2025-03-15", "FY2025")
    assert r["tax_return_id"] == "tr-abc"
    assert r["needs_assignment"] is False


@pytest.mark.asyncio
async def test_multiple_returns_ambiguous_without_hint():
    db = _MockDB([
        {"id": "tr-personal", "tax_year": "FY2025", "return_type": "personal", "status": "collecting_evidence"},
        {"id": "tr-company",  "tax_year": "FY2025", "return_type": "company",  "status": "collecting_evidence"},
    ])
    r = await find_matching_return(db, "2025-03-15", "FY2025")
    assert r["ambiguous"] is True
    assert r["needs_assignment"] is True


@pytest.mark.asyncio
async def test_multiple_returns_disambiguated_by_hint():
    db = _MockDB([
        {"id": "tr-personal", "tax_year": "FY2025", "return_type": "personal", "status": "collecting_evidence"},
        {"id": "tr-company",  "tax_year": "FY2025", "return_type": "company",  "status": "collecting_evidence"},
    ])
    r = await find_matching_return(db, "2025-03-15", "FY2025", return_type_hint="company")
    assert r["tax_return_id"] == "tr-company"
    assert r["needs_assignment"] is False


def test_infer_return_type_hint_finds_company():
    assert infer_return_type_hint("revive_invoice.pdf", "") == "company"
    assert infer_return_type_hint("invoice.pdf", "ABN 12 345 678 910 Pty Ltd") == "company"


def test_infer_return_type_hint_returns_none_when_personal():
    assert infer_return_type_hint("payg_summary.pdf", "Edith Cowan University income statement") is None
