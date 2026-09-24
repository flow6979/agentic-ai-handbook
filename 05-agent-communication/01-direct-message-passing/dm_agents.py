"""Teen agents jo MessageBus pe baat karte hain.

    TranslatorAgent  : {"text", "target_lang"} -> {"translation"}
    SummarizerAgent  : {"text", "lang"?}       -> {"summary"}
                       agar lang diya hai to khud TranslatorAgent ko request bhejta hai
    AuditLogAgent    : fire-and-forget events sunta hai, bas note karta hai
"""
from __future__ import annotations

from agentkit import LLM

from dm_bus import BusAgent, Envelope


class TranslatorAgent(BusAgent):
    def __init__(self, llm: LLM, name: str = "translator"):
        super().__init__(name)
        self.llm = llm

    def handle(self, msg: Envelope) -> Envelope:
        text, lang = msg.payload.get("text"), msg.payload.get("target_lang", "Hindi")
        if not text:
            return msg.reply({"error": "payload.text is required"}, type="error")
        out = self.llm.complete(
            f"Translate to {lang}. Return only the translation.\n\n{text}",
            system="You are a precise translator.",
        )
        self.tell("audit", {"event": "translated", "chars": len(text), "lang": lang})
        return msg.reply({"translation": out.strip()})


class SummarizerAgent(BusAgent):
    def __init__(self, llm: LLM, name: str = "summarizer"):
        super().__init__(name)
        self.llm = llm

    def handle(self, msg: Envelope) -> Envelope:
        text = msg.payload.get("text", "")
        summary = self.llm.complete(
            f"Summarize in one or two sentences:\n\n{text}", system="You write crisp summaries."
        ).strip()
        lang = msg.payload.get("lang")
        if lang:
            # Agent -> Agent: summarizer khud translator se kaam karwata hai
            tr = self.ask("translator", {"text": summary, "target_lang": lang})
            if tr.type == "error":
                return msg.reply({"summary": summary, "warning": tr.payload["error"]})
            summary = tr.payload["translation"]
        self.tell("audit", {"event": "summarized", "lang": lang or "original"})
        return msg.reply({"summary": summary})


class AuditLogAgent(BusAgent):
    def __init__(self, name: str = "audit"):
        super().__init__(name)
        self.entries: list[dict] = []

    def handle(self, msg: Envelope) -> None:
        self.entries.append({"from": msg.sender, **msg.payload})
        return None  # events ka koi reply nahi
