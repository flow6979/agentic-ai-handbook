"""Conversation memory: per session, SQLite mein persist, context budget ke andar.

LLM stateless hai: har call pe poori history bhejni padti hai. History badhti rahi to
(a) context window full, (b) cost badhta, (c) model purani baaton mein confuse.
Solution: last N messages as-is + usse purani baaton ka ek running SUMMARY.

   [system] [summary of old turns] [last N messages] [new user msg]
"""
from __future__ import annotations

import logging

from agentkit import LLM, LLMError, Message

from .store import Store

log = logging.getLogger("supportdesk.memory")


def estimate_tokens(text: str) -> int:
    """Rough estimate: ~4 chars = 1 token (English). Exact count ke liye provider ka tokenizer lo."""
    return len(text) // 4 + 4


class SessionMemory:
    def __init__(self, store: Store, llm: LLM, token_budget: int, keep_last: int):
        self.store = store
        self.llm = llm
        self.token_budget = token_budget
        self.keep_last = keep_last

    def ensure_session(self, session_id: str, customer_id: str) -> None:
        owner = self.store.session_owner(session_id)
        if owner is None:
            self.store.create_session(session_id, customer_id)
        elif owner != customer_id:
            # Session hijacking se bachao: kisi aur ka session_id guess karke uski chat nahi padh sakte
            raise PermissionError("session belongs to a different customer")

    def load(self, session_id: str) -> list[Message]:
        history: list[Message] = []
        summary = self.store.get_summary(session_id)
        if summary:
            history.append(Message.system(f"Summary of the earlier conversation: {summary}"))
        for m in self.store.get_messages(session_id):
            history.append(Message(m["role"], m["content"]))
        return history

    def append(self, session_id: str, role: str, content: str) -> None:
        # Sirf user/assistant text store karte hain, tool traffic nahi: chhota + safe.
        # Trade-off: agla turn tool results dobara fetch karega (fresh data bhi milta hai).
        self.store.add_message(session_id, role, content)

    def compact(self, session_id: str) -> bool:
        """Budget cross hua to purane messages summary mein fold karo. True = compaction hua."""
        rows = self.store.get_messages(session_id)
        summary = self.store.get_summary(session_id)
        total = estimate_tokens(summary) + sum(estimate_tokens(r["content"]) for r in rows)
        if total <= self.token_budget or len(rows) <= self.keep_last:
            return False
        old, _recent = rows[: -self.keep_last], rows[-self.keep_last :]
        transcript = "\n".join(f"{r['role']}: {r['content']}" for r in old)
        prompt = (
            "Summarize the conversation so far in <=80 words for a support agent. Keep order IDs, "
            "decisions, promises made and open issues. Drop greetings.\n\n"
            f"Previous summary: {summary or '(none)'}\n\nNew messages:\n{transcript}"
        )
        try:
            new_summary = self.llm.complete(prompt, max_tokens=200).strip()
        except LLMError as e:
            # Graceful: summarizer fail hua to purani baatein bas drop kar do (truncation)
            log.warning("summarization failed, truncating instead: %s", e)
            new_summary = summary
        self.store.set_summary(session_id, new_summary)
        self.store.delete_messages([r["id"] for r in old])
        return True
