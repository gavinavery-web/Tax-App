"""Route an uploaded document to the correct open tax return based on its
detected date. Pure logic — DB calls are passed in to keep this testable.
"""
from __future__ import annotations

from typing import Optional


async def find_matching_return(
    db,
    detected_date_iso: Optional[str],
    detected_fy: Optional[str],
    *,
    return_type_hint: Optional[str] = None,
) -> dict:
    """Look up an open (non-deleted, non-lodged) tax return that matches.

    Returns a dict:
        {
          "tax_return_id": Optional[str],
          "tax_year": Optional[str],
          "ambiguous": bool,
          "needs_assignment": bool,
          "reason": str,
        }

    Logic:
    - If we have no FY → needs_assignment=True
    - Find all open returns for that FY
    - If 0 → needs_assignment=True ("no open return for this year")
    - If 1 → that's the match
    - If 2+ → use return_type_hint if supplied; otherwise ambiguous=True,
             needs_assignment=True (user picks in Inbox)
    """
    if not detected_fy:
        return {
            "tax_return_id": None,
            "tax_year": None,
            "ambiguous": False,
            "needs_assignment": True,
            "reason": "Could not determine document date",
        }

    open_statuses = {"collecting_evidence", "ready_for_review"}
    rows = await db.tax_returns.find(
        {
            "tax_year": detected_fy,
            "is_deleted": {"$ne": True},
            "status": {"$in": list(open_statuses)},
        },
        {"_id": 0},
    ).to_list(20)

    if len(rows) == 0:
        return {
            "tax_return_id": None,
            "tax_year": detected_fy,
            "ambiguous": False,
            "needs_assignment": True,
            "reason": f"No open return for {detected_fy}",
        }

    if len(rows) == 1:
        return {
            "tax_return_id": rows[0]["id"],
            "tax_year": detected_fy,
            "ambiguous": False,
            "needs_assignment": False,
            "reason": "Single open return matched",
        }

    # 2+ returns for the same FY (e.g. Personal + Company)
    if return_type_hint:
        hits = [r for r in rows if r["return_type"] == return_type_hint]
        if len(hits) == 1:
            return {
                "tax_return_id": hits[0]["id"],
                "tax_year": detected_fy,
                "ambiguous": False,
                "needs_assignment": False,
                "reason": f"Disambiguated by return_type_hint={return_type_hint}",
            }

    return {
        "tax_return_id": None,
        "tax_year": detected_fy,
        "ambiguous": True,
        "needs_assignment": True,
        "reason": f"Multiple open returns for {detected_fy}; user must assign",
    }


def infer_return_type_hint(filename: str, text: str) -> Optional[str]:
    """Cheap heuristic. Returns 'company' if business markers are obvious,
    else None. Personal is NEVER auto-inferred — too risky."""
    import re
    blob = f"{filename or ''} {(text or '')[:3000]}".lower()
    company_markers = [
        r"\bpty\s*ltd\b",
        r"\babn\b\s*\d",
        r"\bbas\b",
        r"\bgst\b",
        r"\bdirector[s]?\b",
        r"\bcompany\s+tax",
        r"revive",  # known company name in this app
    ]
    for pat in company_markers:
        if re.search(pat, blob):
            return "company"
    return None
