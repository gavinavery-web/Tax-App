"""Stage 5 helpers — Australian Financial Year + money parsing.

Pure functions, no DB / no I/O. Used by:
  - AI validation (post-classify FY clamp)
  - CSV / backup exports (money in cents-safe form)
  - Document patch validation (figure normalisation)
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Union


# FY scope locked for this trial. FY2024 = 1 Jul 2023 → 30 Jun 2024.
FY_BOUNDARIES: list[tuple[str, date, date]] = [
    ("FY2024", date(2023, 7, 1), date(2024, 6, 30)),
    ("FY2025", date(2024, 7, 1), date(2025, 6, 30)),
]
SUPPORTED_FYS = {fy for fy, _, _ in FY_BOUNDARIES} | {"Both", "Historical", "Unsure"}


def get_australian_financial_year(d: Union[date, datetime, str, None]) -> str:
    """Map a date to the Australian FY label.

    Returns 'Unsure' for None / unparseable / out-of-scope dates.
    """
    if d is None:
        return "Unsure"
    if isinstance(d, str):
        try:
            d = datetime.fromisoformat(d.replace("Z", "+00:00")).date()
        except Exception:
            return "Unsure"
    if isinstance(d, datetime):
        d = d.date()
    for fy, start, end in FY_BOUNDARIES:
        if start <= d <= end:
            return fy
    return "Unsure"


def normalise_fy(value: Optional[str]) -> str:
    """Pin any string to one of the supported labels, else 'Unsure'."""
    if not value:
        return "Unsure"
    v = str(value).strip()
    return v if v in SUPPORTED_FYS else "Unsure"


def parse_money_to_cents(value) -> Optional[int]:
    """Convert an AI / human money value into integer cents.

    Examples:
      None          → None
      0             → 0
      1234          → 123400  (treat plain int as dollars unless caller pre-converted)
      12.34         → 1234
      "$1,234.50"   → 123450
      "AUD 99.99"   → 9999
      "abc"         → None
    """
    if value is None:
        return None
    if isinstance(value, bool):  # bool is a subclass of int — reject explicitly
        return None
    if isinstance(value, int):
        return value * 100
    if isinstance(value, float):
        return round(value * 100)
    cleaned = (
        str(value)
        .replace("$", "")
        .replace(",", "")
        .replace("AUD", "")
        .replace("aud", "")
        .strip()
    )
    if not cleaned:
        return None
    try:
        return round(float(cleaned) * 100)
    except (ValueError, TypeError):
        return None


def cents_to_money_str(cents: Optional[int]) -> str:
    """Format integer cents as a CSV-safe AUD string. None / non-int → ''."""
    if cents is None or not isinstance(cents, int):
        return ""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"
