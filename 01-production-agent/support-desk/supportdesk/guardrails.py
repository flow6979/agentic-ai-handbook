"""Guardrails: LLM ke pehle (input) aur baad (output) ki checks.

   user msg -> [INPUT GUARD] -> agent -> [OUTPUT GUARD] -> user
                length, injection      internal data leak, canary,
                PII redact (logs)      doosre customer ka email

Yeh regex heuristics sirf FIRST LAYER hain. Asli defense yeh hai ki tools sensitive data
return hi na karein (data minimization) aur risky actions policy se gated hon.
Production mein iske upar classifier models (Llama Guard, provider moderation APIs) lagate hain.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

INJECTION_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|rules|prompts?)",
    r"(reveal|show|print|repeat|leak).{0,40}(system prompt|your instructions|hidden prompt)",
    r"\byou are now\b",
    r"\b(developer|god|dan) mode\b",
    r"act as (an? )?(admin|administrator|developer|system)",
    r"</?\s*(system|assistant)\s*>",
    r"disregard (your|all) (rules|guidelines)",
]
_INJ = [re.compile(p, re.I) for p in INJECTION_PATTERNS]

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
CARD = re.compile(r"\b(?:\d[ -]?){13,16}\b")
PHONE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[ -]?)?\d{10}(?!\d)")

# Yeh words reply mein aaye = internal data leak hua
INTERNAL_MARKERS = ["internal_note", "internal note", "profit margin", "fraud check", "supplier batch"]
CANARY = "SD-CANARY-7731"  # system prompt mein chhupa token; reply mein dikha = system prompt leak

REFUSAL_INJECTION = "I can't help with that request. I'm here to help with your orders, shipping, returns and refunds."
REFUSAL_TOO_LONG = "Your message is too long. Please shorten it and try again."
SAFE_FALLBACK = "Sorry, I can't share that. Is there anything else I can help you with regarding your orders?"


@dataclass
class InputCheck:
    ok: bool
    reason: str | None = None
    message: str | None = None  # user ko dikhane wala refusal


@dataclass
class OutputCheck:
    text: str
    violations: list[str] = field(default_factory=list)


def check_input(text: str, max_chars: int) -> InputCheck:
    if not text.strip():
        return InputCheck(False, "empty", "Please type a message.")
    if len(text) > max_chars:
        return InputCheck(False, "too_long", REFUSAL_TOO_LONG)
    for p in _INJ:
        if p.search(text):
            return InputCheck(False, "prompt_injection", REFUSAL_INJECTION)
    return InputCheck(True)


def redact_pii(text: str) -> str:
    """Logs/traces mein PII mat likho (GDPR / DPDP). Card pehle, phir phone, phir email."""
    text = CARD.sub("[CARD]", text)
    text = PHONE.sub("[PHONE]", text)
    return EMAIL.sub("[EMAIL]", text)


def check_output(text: str, allowed_email: str | None) -> OutputCheck:
    violations = []
    lower = text.lower()
    if CANARY.lower() in lower:
        violations.append("system_prompt_leak")
    if any(m in lower for m in INTERNAL_MARKERS):
        violations.append("internal_data_leak")
    if violations:
        return OutputCheck(SAFE_FALLBACK, violations)  # poora reply replace, partial fix risky hai

    def _mask(m: re.Match) -> str:
        return m.group(0) if allowed_email and m.group(0).lower() == allowed_email.lower() else "[redacted email]"

    masked = EMAIL.sub(_mask, text)
    if masked != text:
        violations.append("foreign_email_redacted")
    return OutputCheck(masked, violations)
