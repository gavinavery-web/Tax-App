"""Stage 7 Phase 3 — Property Manager.

Manages property use-periods so bank transactions / tax items can be
classified as rental vs main-residence vs Airbnb vs mixed.

ID convention: properties carry a string `id` (NOT Mongo `_id`).
Stage 7 migration seeds Heathridge + Waggrakine with stable ids
(`prop-heathridge`, `prop-waggrakine`).

`use_periods` is an embedded list. Each period is identified by a
string `period_id` (uuid). Dates are ISO-8601 (YYYY-MM-DD or full
ISO datetime). `date_to=None` means "still in this use".
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# Australian-tax-relevant use types. UI dropdowns should mirror this list.
VALID_USE_TYPES = (
    "main_residence",
    "rental",
    "airbnb",
    "renovation",
    "vacant",
    "mixed",
)

# When two periods overlap on the same date, this priority decides which
# one wins. Main residence > mixed > renovation > rental > airbnb > vacant.
_OVERLAP_PRIORITY = (
    "main_residence", "mixed", "renovation", "rental", "airbnb", "vacant",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # Accept both date-only and full datetime ISO strings.
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


async def get_properties(db) -> List[Dict]:
    """Return all properties (newest first by name)."""
    return await db.properties.find({}, {"_id": 0}).sort("property_name", 1).to_list(500)


async def get_property(db, property_id: str) -> Optional[Dict]:
    return await db.properties.find_one({"id": property_id}, {"_id": 0})


async def add_property(db, property_name: str, address: str) -> str:
    """Insert a new property. Returns the new id."""
    now = _utc_now_iso()
    new_id = str(uuid.uuid4())
    await db.properties.insert_one({
        "id": new_id,
        "property_name": property_name,
        "address": address,
        "use_periods": [],
        "created_at": now,
        "updated_at": now,
    })
    logger.info(f"added property: {property_name}")
    return new_id


async def add_use_period(
    db, property_id: str, *,
    date_from: str, date_to: Optional[str],
    use_type: str, notes: str = "",
) -> bool:
    """Append a use period to a property.

    `date_to=None` means the period is still in effect.
    Raises ValueError on invalid `use_type` or unparseable dates.
    """
    if use_type not in VALID_USE_TYPES:
        raise ValueError(f"invalid use_type '{use_type}'. Valid: {VALID_USE_TYPES}")
    if _parse_iso(date_from) is None:
        raise ValueError(f"invalid date_from '{date_from}' (need ISO YYYY-MM-DD)")
    if date_to is not None and _parse_iso(date_to) is None:
        raise ValueError(f"invalid date_to '{date_to}' (need ISO YYYY-MM-DD or null)")

    period = {
        "period_id": str(uuid.uuid4()),
        "date_from": date_from,
        "date_to": date_to,
        "use_type": use_type,
        "notes": notes,
        "created_at": _utc_now_iso(),
    }
    res = await db.properties.update_one(
        {"id": property_id},
        {"$push": {"use_periods": period}, "$set": {"updated_at": _utc_now_iso()}},
    )
    if res.modified_count > 0:
        logger.info(f"property {property_id}: +{use_type} period {date_from}→{date_to}")
    return res.modified_count > 0


async def remove_use_period(db, property_id: str, period_id: str) -> bool:
    res = await db.properties.update_one(
        {"id": property_id},
        {"$pull": {"use_periods": {"period_id": period_id}},
         "$set": {"updated_at": _utc_now_iso()}},
    )
    return res.modified_count > 0


async def get_use_period_for_date(
    db, property_name: str, on_date: datetime,
) -> Optional[Dict]:
    """Return the use period covering `on_date` for the named property.

    Overlap resolution: returns the highest-priority period per
    `_OVERLAP_PRIORITY` (main_residence wins). Logs a warning if there
    *is* an overlap so the user can spot data-entry mistakes.
    """
    prop = await db.properties.find_one(
        {"property_name": property_name}, {"_id": 0},
    )
    if not prop:
        return None

    # Strip tzinfo before comparing — stored dates may be tz-naive.
    if on_date.tzinfo is not None:
        on_date = on_date.replace(tzinfo=None)

    matches: List[Dict] = []
    for p in prop.get("use_periods") or []:
        df = _parse_iso(p.get("date_from"))
        if df is None:
            continue
        if df.tzinfo is not None:
            df = df.replace(tzinfo=None)
        dt_to_raw = p.get("date_to")
        if dt_to_raw is None:
            dt = datetime.now()
        else:
            parsed = _parse_iso(dt_to_raw)
            if parsed is None:
                continue
            dt = parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
        if df <= on_date <= dt:
            matches.append(p)

    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]

    logger.warning(
        f"overlapping use periods for {property_name} on {on_date.date()} — "
        f"{len(matches)} matches, resolving by priority",
    )
    for ut in _OVERLAP_PRIORITY:
        for p in matches:
            if p.get("use_type") == ut:
                return p
    return matches[0]
