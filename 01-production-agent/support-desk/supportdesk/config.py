"""Config: saari settings env se aati hain, code mein kuch hardcode nahi.

Production rule: ek hi code dev / staging / prod mein chale, sirf env badle.
Model badalna, limits badalna, read-only mode on karna = env change, deploy nahi.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "supportdesk.sqlite3"


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    # LLM spec "provider:model", comma = fallback chain. None => get_llm() LLM_MODEL env padhega.
    llm_model: str | None = None
    max_steps: int = 6  # agent loop ka hard cap
    context_token_budget: int = 1500  # history isse badi hui to purani baatein summarize
    keep_last_messages: int = 6  # summarize karte waqt last N messages as-is rakho
    refund_auto_limit: float = 50.0  # isse chhota refund auto-approve, bada = human approval
    rate_limit_per_minute: int = 20  # per user
    request_timeout_s: float = 60.0  # ek request ka wall-clock budget
    max_input_chars: int = 2000
    db_path: str = str(DEFAULT_DB)
    trace_file: str | None = None  # JSONL traces
    read_only: bool = False  # True => sirf READ tier tools (koi refund nahi)
    verbose: bool = True

    def __post_init__(self):
        if self.max_steps < 1:
            raise ValueError("max_steps must be >= 1")
        if self.refund_auto_limit < 0:
            raise ValueError("refund_auto_limit must be >= 0")
        if self.rate_limit_per_minute < 1:
            raise ValueError("rate_limit_per_minute must be >= 1")

    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass
        e = os.getenv
        s = cls(
            llm_model=e("LLM_MODEL") or None,
            max_steps=int(e("SUPPORTDESK_MAX_STEPS", "6")),
            context_token_budget=int(e("SUPPORTDESK_CONTEXT_BUDGET", "1500")),
            keep_last_messages=int(e("SUPPORTDESK_KEEP_LAST", "6")),
            refund_auto_limit=float(e("SUPPORTDESK_REFUND_AUTO_LIMIT", "50")),
            rate_limit_per_minute=int(e("SUPPORTDESK_RATE_LIMIT", "20")),
            request_timeout_s=float(e("SUPPORTDESK_TIMEOUT", "60")),
            max_input_chars=int(e("SUPPORTDESK_MAX_INPUT_CHARS", "2000")),
            db_path=e("SUPPORTDESK_DB", str(DEFAULT_DB)),
            trace_file=e("AGENT_TRACE_FILE") or None,
            read_only=_env_bool("SUPPORTDESK_READ_ONLY", False),
            verbose=_env_bool("AGENT_VERBOSE", True),
        )
        return replace(s, **overrides)
