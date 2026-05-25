"""
Hybrid AI Classification Module (Gemini → Claude escalation)
-----------------------------------------------------------
Routes simple / low-risk documents through Gemini Flash (cheap) and
escalates risky / complex tax items to Claude Sonnet 4.5.

DEVIATION from user spec: both models are reached via emergentintegrations
with the single EMERGENT_LLM_KEY — no separate GOOGLE_AI_API_KEY or
ANTHROPIC_API_KEY required. Behaviour, escalation rules and output schema
are identical to the spec.
"""

from __future__ import annotations

import asyncio
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

# ---------- Configuration ----------------------------------------------------

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
CLAUDE_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
BRAIN_PROMPT_PATH = Path(__file__).parent / "THE_BRAIN_v1.md"

# Pricing (USD per 1M tokens) — used for cost tracking
GEMINI_PRICE_IN = 0.075   # gemini-2.5-flash input
GEMINI_PRICE_OUT = 0.30   # gemini-2.5-flash output
CLAUDE_PRICE_IN = 3.00
CLAUDE_PRICE_OUT = 15.00

# Escalation triggers
ESCALATION_KEYWORDS = [
    "loan", "director", "trust", "shareholder", "transfer", "reimbursement",
    "airbnb", "mortgage", "capital", "renovation", "repair", "private",
    "business", "gst", "bas", "ato debt", "division 7a", "main residence",
    "cgt", "depreciation", "apportionment",
]

RISKY_CATEGORIES = [
    "03 Airbnb", "04 Waggrakine Rental", "05 Heathridge",
    "06 Revive", "07 Bank Statements", "09 Accountant Review",
]

ALLOWED_CATEGORIES = [
    "00 Inbox", "01 ATO", "02 PAYG Income", "03 Airbnb",
    "04 Waggrakine Rental", "05 Heathridge", "06 Revive",
    "07 Bank Statements", "08 Salary Packaging Maxxia",
    "09 Accountant Review", "10 Missing Evidence", "11 Final Accountant Pack",
]
LEGACY_CATEGORY = {
    "ATO": "01 ATO", "PAYG Income": "02 PAYG Income", "Airbnb": "03 Airbnb",
    "Waggrakine Rental": "04 Waggrakine Rental", "Heathridge": "05 Heathridge",
    "Revive": "06 Revive", "Bank Statement": "07 Bank Statements",
    "Salary Packaging / Maxxia": "08 Salary Packaging Maxxia",
    "Super / HECS": "02 PAYG Income", "Accountant Review": "09 Accountant Review",
    "Other": "00 Inbox",
}
ALLOWED_TAX_YEARS = ["FY2024", "FY2025", "FY2026", "Both", "Historical", "Unsure"]
ALLOWED_CONFIDENCE = ["Confirmed", "Likely", "Unsure"]
ALLOWED_RISK = ["Green", "Amber", "Red"]


def load_brain_prompt() -> str:
    try:
        return BRAIN_PROMPT_PATH.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Could not load THE_BRAIN_v1.md: {e}")
        return "You classify Australian tax documents. Return JSON only."


# ---------- Source-quote integrity (paramount rule) -------------------------

_OCR_TABLE = str.maketrans({
    "O": "0", "o": "0", "l": "1", "L": "1", "i": "1", "I": "1",
    "S": "5", "s": "5", "B": "8",
})


def _normalise(s: str) -> str:
    if not s:
        return ""
    s = s.translate(_OCR_TABLE)
    s = re.sub(r"[\$,]", "", s)
    s = re.sub(r"\s+", " ", s.lower()).strip()
    s = re.sub(r"[^a-z0-9.\- ]", "", s)
    return s


def fuzzy_verify(quote: str, source_text: str) -> bool:
    if not quote or not source_text:
        return False
    nq = _normalise(quote)
    if not nq:
        return False
    ns = _normalise(source_text)
    if nq in ns:
        return True
    # Tolerate small drift: try chunked window for long quotes
    if len(nq) >= 12:
        for size in (len(nq), max(12, len(nq) - 4)):
            for i in range(0, len(nq) - size + 1):
                if nq[i:i + size] in ns:
                    return True
    return False


# ---------- JSON helpers -----------------------------------------------------

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE | re.MULTILINE)


def _strip_json(s: str) -> str:
    if not s:
        return s
    s = _FENCE_RE.sub("", s.strip())
    first = s.find("{")
    last = s.rfind("}")
    if first != -1 and last > first:
        return s[first:last + 1]
    return s


def _coerce_amount(v: Any) -> Optional[float]:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(re.sub(r"[^\d\.\-]", "", v))
        except Exception:
            return None
    return None


# ---------- Schema validation ------------------------------------------------

def validate_schema(result: dict, source_text: str) -> dict:
    out = dict(result or {})

    cat = str(out.get("category") or "00 Inbox")
    cat = LEGACY_CATEGORY.get(cat, cat)
    if cat not in ALLOWED_CATEGORIES:
        cat = "00 Inbox"
        out["category_confidence"] = "Unsure"
    out["category"] = cat

    if out.get("category_confidence") not in ALLOWED_CONFIDENCE:
        out["category_confidence"] = "Unsure"
    if out.get("tax_year") not in ALLOWED_TAX_YEARS:
        out["tax_year"] = "Unsure"
    if out.get("tax_year_confidence") not in ALLOWED_CONFIDENCE:
        out["tax_year_confidence"] = "Unsure"
    if out.get("risk_level") not in ALLOWED_RISK:
        out["risk_level"] = "Amber" if cat == "00 Inbox" else "Green"

    # Coerce date_range to flat fields for the DB while keeping nested for API consumers
    dr = out.get("date_range")
    if isinstance(dr, dict):
        out["date_range_from"] = dr.get("from") if isinstance(dr.get("from"), str) else None
        out["date_range_to"] = dr.get("to") if isinstance(dr.get("to"), str) else None
    else:
        out["date_range_from"] = out.get("date_range_from")
        out["date_range_to"] = out.get("date_range_to")
        out["date_range"] = {"from": out.get("date_range_from"), "to": out.get("date_range_to")}

    figs_in = out.get("headline_figures") or []
    if not isinstance(figs_in, list):
        figs_in = []
    figs_out: list[dict] = []
    for f in figs_in[:5]:
        if not isinstance(f, dict):
            continue
        amount = _coerce_amount(f.get("amount"))
        if amount is None:
            continue
        label = str(f.get("label") or "Figure")[:120]
        currency = str(f.get("currency") or "AUD")
        quote = str(f.get("source_quote") or "")[:200]
        conf = str(f.get("confidence") or "Unsure")
        if conf not in ALLOWED_CONFIDENCE:
            conf = "Unsure"
        verified = fuzzy_verify(quote, source_text)
        notes = ""
        if not verified:
            conf = "Unsure"
            notes = "Could not verify source quote in document"
        figs_out.append({
            "label": label, "amount": amount, "currency": currency,
            "confidence": conf, "source_quote": quote,
            "verified": verified, "notes": notes,
        })
    out["headline_figures"] = figs_out

    rr = out.get("accountant_review_required")
    out["accountant_review_required"] = bool(rr) if isinstance(rr, bool) else str(rr).strip().lower() in ("true", "yes")
    out["accountant_review_reason"] = (out.get("accountant_review_reason") or None)
    out["counterparty"] = out.get("counterparty") or None

    # Defaults
    out.setdefault("document_type", "Unknown")
    out.setdefault("tax_year_reason", "")
    out.setdefault("one_line_summary", "")
    sf = str(out.get("suggested_filename") or "")[:160]
    out["suggested_filename"] = re.sub(r"[^A-Za-z0-9._\- ]+", "", sf) or None

    return out


# ---------- Model calls (both via emergentintegrations + EMERGENT_LLM_KEY) ---

async def _call_model(provider: str, model: str, system: str, user: str) -> tuple[Optional[dict], int, int, str]:
    """Returns (parsed_json_or_None, in_tokens_est, out_tokens_est, raw_text)."""
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return None, 0, 0, ""
    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"vault-{uuid.uuid4()}",
            system_message=system,
        ).with_model(provider, model)
        raw = await chat.send_message(UserMessage(text=user))
        raw = str(raw or "")
        cleaned = _strip_json(raw)
        parsed = json.loads(cleaned)
        in_tok = max(1, (len(system) + len(user)) // 4)
        out_tok = max(1, len(raw) // 4)
        return parsed, in_tok, out_tok, raw
    except json.JSONDecodeError as e:
        logger.warning(f"{provider}:{model} non-JSON response: {e}")
        return None, 0, 0, raw if "raw" in locals() else ""
    except Exception as e:
        logger.warning(f"{provider}:{model} call failed: {e}")
        return None, 0, 0, ""


def _user_message(filename: str, mime: str, text: str, gemini_result: Optional[dict] = None, escalation_reason: Optional[str] = None) -> str:
    truncated = truncate_for_ai(text)
    base = (
        f"Filename: {filename}\n"
        f"File type: {mime}\n\n"
        f"Extracted text:\n{truncated}\n\n"
    )
    if gemini_result is not None:
        base = (
            f"Filename: {filename}\n"
            f"File type: {mime}\n\n"
            f"Escalation reason: {escalation_reason}\n\n"
            f"Initial Gemini classification (review and improve):\n{json.dumps(gemini_result, indent=2)}\n\n"
            f"Extracted text:\n{truncated}\n\n"
            f"Re-classify with higher scrutiny. Return ONLY the JSON object."
        )
        return base
    base += "Classify this document per your system prompt. Return ONLY the JSON object. No preamble."
    return base


# ---------- Escalation policy ------------------------------------------------

def should_escalate(gemini_result: dict, source_text: str) -> tuple[bool, Optional[str]]:
    if not gemini_result:
        return True, "Gemini returned no result"
    if gemini_result.get("category_confidence") != "Confirmed":
        return True, f"Category confidence is {gemini_result.get('category_confidence')}"
    if gemini_result.get("tax_year_confidence") != "Confirmed":
        return True, f"Tax-year confidence is {gemini_result.get('tax_year_confidence')}"
    if gemini_result.get("risk_level") in ["Amber", "Red"]:
        return True, f"Risk level is {gemini_result.get('risk_level')}"
    if gemini_result.get("accountant_review_required"):
        return True, "Accountant review flagged by Gemini"
    cat = gemini_result.get("category", "")
    if cat in RISKY_CATEGORIES:
        return True, f"Category {cat} is tax-critical"
    tl = (source_text or "").lower()
    hits = [k for k in ESCALATION_KEYWORDS if k in tl]
    if hits:
        return True, f"Contains tax-critical keywords: {', '.join(hits[:3])}"
    for f in (gemini_result.get("headline_figures") or []):
        q = f.get("source_quote")
        if q and not fuzzy_verify(q, source_text):
            return True, f"Source quote could not be verified: {q[:50]}"
    return False, None


# ---------- Public entry point ----------------------------------------------

def _cost(in_tok: int, out_tok: int, price_in: float, price_out: float) -> float:
    return round(in_tok / 1_000_000 * price_in + out_tok / 1_000_000 * price_out, 6)


async def classify_document(filename: str, mime: str, source_text: str) -> dict:
    """Hybrid classify. Returns the legacy result dict shape expected by the
    upload pipeline, with extra fields: primary_model_used, final_model_used,
    escalated_to_claude, escalation_reason, gemini_cost_usd, claude_cost_usd."""
    brain = load_brain_prompt()
    user = _user_message(filename, mime, source_text)

    # --- Step 1: Gemini ------------------------------------------------------
    g_parsed, g_in, g_out, g_raw = await _call_model("gemini", GEMINI_MODEL, brain, user)
    gemini_cost = _cost(g_in, g_out, GEMINI_PRICE_IN, GEMINI_PRICE_OUT)

    if not g_parsed:
        # Gemini failed → escalate straight to Claude
        c_parsed, c_in, c_out, c_raw = await _call_model(
            "anthropic", CLAUDE_MODEL, brain,
            _user_message(filename, mime, source_text),
        )
        claude_cost = _cost(c_in, c_out, CLAUDE_PRICE_IN, CLAUDE_PRICE_OUT)
        if not c_parsed:
            return {
                "ok": False,
                "analysis": validate_schema({
                    "category": "00 Inbox", "category_confidence": "Unsure",
                    "risk_level": "Red", "accountant_review_required": True,
                    "accountant_review_reason": "AI classification failed (Gemini + Claude both failed)",
                    "one_line_summary": "AI failed — manual review required",
                }, source_text),
                "tokens_in": g_in + c_in, "tokens_out": g_out + c_out,
                "cost_usd": gemini_cost + claude_cost,
                "model": "error_fallback",
                "primary_model_used": GEMINI_MODEL,
                "final_model_used": "error_fallback",
                "escalated_to_claude": True,
                "escalation_reason": "Gemini returned no result",
                "gemini_cost_usd": gemini_cost,
                "claude_cost_usd": claude_cost,
                "total_ai_cost_usd": gemini_cost + claude_cost,
                "error": "Both models failed",
            }
        analysis = validate_schema(c_parsed, source_text)
        return {
            "ok": True,
            "analysis": analysis,
            "tokens_in": g_in + c_in, "tokens_out": g_out + c_out,
            "cost_usd": gemini_cost + claude_cost,
            "model": CLAUDE_MODEL,
            "primary_model_used": GEMINI_MODEL,
            "final_model_used": CLAUDE_MODEL,
            "escalated_to_claude": True,
            "escalation_reason": "Gemini failed — direct Claude classification",
            "gemini_cost_usd": gemini_cost,
            "claude_cost_usd": claude_cost,
            "total_ai_cost_usd": gemini_cost + claude_cost,
            "raw": c_raw[:2000],
        }

    # --- Step 2: Escalation decision ----------------------------------------
    escalate, reason = should_escalate(g_parsed, source_text)

    if not escalate:
        analysis = validate_schema(g_parsed, source_text)
        return {
            "ok": True,
            "analysis": analysis,
            "tokens_in": g_in, "tokens_out": g_out,
            "cost_usd": gemini_cost,
            "model": GEMINI_MODEL,
            "primary_model_used": GEMINI_MODEL,
            "final_model_used": GEMINI_MODEL,
            "escalated_to_claude": False,
            "escalation_reason": None,
            "gemini_cost_usd": gemini_cost,
            "claude_cost_usd": 0.0,
            "total_ai_cost_usd": gemini_cost,
            "raw": g_raw[:2000],
        }

    # --- Step 3: Claude ------------------------------------------------------
    logger.info(f"Escalating to Claude: {reason}")
    c_parsed, c_in, c_out, c_raw = await _call_model(
        "anthropic", CLAUDE_MODEL, brain,
        _user_message(filename, mime, source_text, gemini_result=g_parsed, escalation_reason=reason),
    )
    claude_cost = _cost(c_in, c_out, CLAUDE_PRICE_IN, CLAUDE_PRICE_OUT)

    if c_parsed:
        analysis = validate_schema(c_parsed, source_text)
        return {
            "ok": True,
            "analysis": analysis,
            "tokens_in": g_in + c_in, "tokens_out": g_out + c_out,
            "cost_usd": gemini_cost + claude_cost,
            "model": CLAUDE_MODEL,
            "primary_model_used": GEMINI_MODEL,
            "final_model_used": CLAUDE_MODEL,
            "escalated_to_claude": True,
            "escalation_reason": reason,
            "gemini_cost_usd": gemini_cost,
            "claude_cost_usd": claude_cost,
            "total_ai_cost_usd": gemini_cost + claude_cost,
            "raw": c_raw[:2000],
        }

    # Claude failed — fall back to Gemini result with downgraded confidence
    logger.warning(f"Claude escalation failed — keeping Gemini result with downgraded confidence ({reason})")
    g_parsed["category_confidence"] = "Unsure"
    g_parsed["risk_level"] = "Amber"
    g_parsed["accountant_review_required"] = True
    g_parsed["accountant_review_reason"] = (
        (g_parsed.get("accountant_review_reason") or "") +
        f" | Escalated to Claude but Claude failed. Original reason: {reason}"
    ).strip(" |")
    analysis = validate_schema(g_parsed, source_text)
    return {
        "ok": True,
        "analysis": analysis,
        "tokens_in": g_in + c_in, "tokens_out": g_out + c_out,
        "cost_usd": gemini_cost + claude_cost,
        "model": GEMINI_MODEL,
        "primary_model_used": GEMINI_MODEL,
        "final_model_used": f"{GEMINI_MODEL} (Claude failed)",
        "escalated_to_claude": True,
        "escalation_reason": reason,
        "gemini_cost_usd": gemini_cost,
        "claude_cost_usd": claude_cost,
        "total_ai_cost_usd": gemini_cost + claude_cost,
        "raw": g_raw[:2000],
    }
