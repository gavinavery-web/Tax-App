"""AI classifier — calls Claude Sonnet 4.5 via emergentintegrations.

Loads THE_BRAIN_v1.md verbatim as the system prompt on every call.
Performs schema validation and the paramount-rule fuzzy integrity check
on every returned figure.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Optional

from emergentintegrations.llm.chat import LlmChat, UserMessage

from extraction import truncate_for_ai

logger = logging.getLogger(__name__)

THE_BRAIN_PATH = Path(__file__).parent / "THE_BRAIN_v1.md"

ALLOWED_CATEGORIES = {
    "00 Inbox", "01 ATO", "02 PAYG Income", "03 Airbnb", "04 Waggrakine Rental",
    "05 Heathridge", "06 Revive", "07 Bank Statements",
    "08 Salary Packaging Maxxia", "09 Accountant Review",
    "10 Missing Evidence", "11 Final Accountant Pack",
    # Legacy short forms still accepted; normalised below.
    "ATO", "PAYG Income", "Airbnb", "Waggrakine Rental", "Heathridge",
    "Revive", "Bank Statement", "Salary Packaging / Maxxia", "Super / HECS",
    "Accountant Review", "Other",
}

CATEGORY_NORMALISE = {
    "ATO": "01 ATO",
    "PAYG Income": "02 PAYG Income",
    "Airbnb": "03 Airbnb",
    "Waggrakine Rental": "04 Waggrakine Rental",
    "Heathridge": "05 Heathridge",
    "Revive": "06 Revive",
    "Bank Statement": "07 Bank Statements",
    "Salary Packaging / Maxxia": "08 Salary Packaging Maxxia",
    "Super / HECS": "02 PAYG Income",
    "Accountant Review": "09 Accountant Review",
    "Other": "00 Inbox",
}

ALLOWED_RISK = {"Green", "Amber", "Red"}

ALLOWED_TAX_YEARS = {"FY2024", "FY2025", "FY2026", "FY2027", "Both", "Historical", "Unsure"}

ALLOWED_CONFIDENCE = {"Confirmed", "Likely", "Unsure"}

# Sonnet 4.5 public pricing (USD per million tokens) — used for cost tracking
PRICING_PER_M = {
    "input": 3.00,
    "output": 15.00,
}


def load_brain() -> str:
    try:
        return THE_BRAIN_PATH.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Could not load THE_BRAIN_v1.md: {e}")
        return "You classify documents into the Australian Tax Evidence Vault categories. Return JSON only."


# ---------- Integrity (paramount rule) ---------------------------------------

_OCR_SUBS = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5", "B": "8"})


def _normalize(s: str) -> str:
    if not s:
        return ""
    s = s.translate(_OCR_SUBS)
    s = re.sub(r"\s+", "", s.lower())
    s = re.sub(r"[^a-z0-9.]", "", s)
    return s


def fuzzy_in_source(quote: str, source_text: str) -> bool:
    if not quote or not source_text:
        return False
    nq = _normalize(quote)
    if not nq:
        return False
    ns = _normalize(source_text)
    if nq in ns:
        return True
    # Sliding window similarity: accept if 85% of characters in quote appear contiguously
    if len(nq) >= 12:
        # try chunked match
        for size in (len(nq), max(12, len(nq) - 4)):
            for i in range(0, len(nq) - size + 1):
                if nq[i:i + size] in ns:
                    return True
    return False


# ---------- Schema validation ------------------------------------------------

def _coerce_amount(v: Any) -> Optional[float]:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(re.sub(r"[^\d\.\-]", "", v))
        except Exception:
            return None
    return None


def validate_and_repair(parsed: dict, source_text: str) -> dict:
    """Coerce + validate the AI's response. Downgrade unverifiable figures
    per the paramount rule. Never raise — always return a usable dict."""
    out: dict[str, Any] = {}
    out["document_type"] = str(parsed.get("document_type") or "Unknown")

    cat = str(parsed.get("category") or "00 Inbox")
    cat = CATEGORY_NORMALISE.get(cat, cat)
    if cat not in ALLOWED_CATEGORIES or cat in CATEGORY_NORMALISE:
        # If still a short legacy value or unknown, fall back to Inbox
        cat = CATEGORY_NORMALISE.get(cat, "00 Inbox") if cat in CATEGORY_NORMALISE else "00 Inbox"
    out["category"] = cat

    cc = str(parsed.get("category_confidence") or "Unsure")
    if cc not in ALLOWED_CONFIDENCE:
        cc = "Unsure"
    out["category_confidence"] = cc

    ty = str(parsed.get("tax_year") or "Unsure")
    if ty not in ALLOWED_TAX_YEARS:
        ty = "Unsure"
    out["tax_year"] = ty

    tyc = str(parsed.get("tax_year_confidence") or "Unsure")
    if tyc not in ALLOWED_CONFIDENCE:
        tyc = "Unsure"
    out["tax_year_confidence"] = tyc

    out["tax_year_reason"] = str(parsed.get("tax_year_reason") or "")[:500]

    risk = str(parsed.get("risk_level") or "")
    if risk not in ALLOWED_RISK:
        risk = "Amber" if out.get("category") == "00 Inbox" else "Green"
    out["risk_level"] = risk

    # date_range may arrive nested {from,to} or flat (legacy)
    dr = parsed.get("date_range")
    if isinstance(dr, dict):
        out["date_range_from"] = dr.get("from") if isinstance(dr.get("from"), str) else None
        out["date_range_to"] = dr.get("to") if isinstance(dr.get("to"), str) else None
    else:
        out["date_range_from"] = parsed.get("date_range_from") if isinstance(parsed.get("date_range_from"), str) else None
        out["date_range_to"] = parsed.get("date_range_to") if isinstance(parsed.get("date_range_to"), str) else None

    out["counterparty"] = (parsed.get("counterparty") or None)
    out["one_line_summary"] = str(parsed.get("one_line_summary") or "")[:240]
    out["what_it_proves"] = str(parsed.get("what_it_proves") or "")[:600]

    figs_in = parsed.get("headline_figures") or []
    if not isinstance(figs_in, list):
        figs_in = []
    figs_out: list[dict[str, Any]] = []
    for f in figs_in[:5]:
        if not isinstance(f, dict):
            continue
        amount = _coerce_amount(f.get("amount"))
        if amount is None:
            continue
        label = str(f.get("label") or "Figure")[:120]
        conf = str(f.get("confidence") or "Unsure")
        if conf not in ALLOWED_CONFIDENCE:
            conf = "Unsure"
        currency = str(f.get("currency") or "AUD")
        quote = str(f.get("source_quote") or "")[:400]
        verified = fuzzy_in_source(quote, source_text)
        notes = ""
        if not verified:
            conf = "Unsure"
            notes = "Could not verify in source text — please confirm manually"
        figs_out.append({
            "label": label,
            "amount": amount,
            "currency": currency,
            "confidence": conf,
            "source_quote": quote,
            "verified": verified,
            "notes": notes,
        })
    out["headline_figures"] = figs_out

    rr = parsed.get("accountant_review_required")
    out["accountant_review_required"] = bool(rr) if isinstance(rr, bool) else str(rr).strip().lower() in ("true", "yes")
    out["accountant_review_reason"] = str(parsed.get("accountant_review_reason") or "")[:500] or None

    sf = str(parsed.get("suggested_filename") or "")[:160]
    out["suggested_filename"] = re.sub(r"[^A-Za-z0-9._\- ]+", "", sf) or None

    return out


# ---------- The call ---------------------------------------------------------

_JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE | re.MULTILINE)


def _strip_json_fences(s: str) -> str:
    if not s:
        return s
    s = _JSON_FENCE.sub("", s.strip())
    # find first { and last }
    first = s.find("{")
    last = s.rfind("}")
    if first != -1 and last != -1 and last > first:
        return s[first:last + 1]
    return s


async def classify_document(filename: str, mime: str, source_text: str) -> dict[str, Any]:
    """Classify a single document. Returns a dict including the parsed analysis
    plus usage/cost metadata. NEVER raises — caller can rely on result['ok']."""
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
    max_tokens = int(os.environ.get("AI_MAX_TOKENS", "2000"))

    if not api_key:
        return {"ok": False, "error": "EMERGENT_LLM_KEY not set", "analysis": None,
                "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "model": model}

    brain = load_brain()
    truncated = truncate_for_ai(source_text)
    user_text = (
        f"Filename: {filename}\n"
        f"File type: {mime}\n\n"
        f"Extracted text:\n{truncated}\n\n"
        f"Classify this document per your system prompt. Return ONLY the JSON object. No preamble."
    )

    last_raw = ""
    last_error: Optional[str] = None
    for attempt in (1, 2):
        try:
            chat = LlmChat(
                api_key=api_key,
                session_id=f"vault-{uuid.uuid4()}",
                system_message=brain,
            ).with_model("anthropic", model)
            extra = "" if attempt == 1 else "\n\nIMPORTANT: previous response was invalid JSON. Return ONLY a valid JSON object with the required schema. No commentary."
            response = await chat.send_message(UserMessage(text=user_text + extra))
            last_raw = str(response or "")
            cleaned = _strip_json_fences(last_raw)
            parsed = json.loads(cleaned)
            analysis = validate_and_repair(parsed, source_text)
            # crude token estimate — emergentintegrations does not surface usage today
            est_tokens_in = max(1, (len(brain) + len(user_text)) // 4)
            est_tokens_out = max(1, len(last_raw) // 4)
            cost_usd = round(
                est_tokens_in / 1_000_000 * PRICING_PER_M["input"]
                + est_tokens_out / 1_000_000 * PRICING_PER_M["output"],
                4,
            )
            return {
                "ok": True,
                "analysis": analysis,
                "tokens_in": est_tokens_in,
                "tokens_out": est_tokens_out,
                "cost_usd": cost_usd,
                "model": model,
                "raw": last_raw[:2000],
            }
        except json.JSONDecodeError as e:
            last_error = f"JSON parse error: {e}"
            logger.warning(f"AI returned non-JSON (attempt {attempt}): {last_error}")
        except Exception as e:
            last_error = f"AI call failed: {e}"
            logger.exception("AI classify failed")
            break

    return {
        "ok": False,
        "error": last_error or "unknown",
        "analysis": None,
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
        "model": model,
        "raw": last_raw[:2000],
    }
