"""Demo: user -> summarizer -> translator, aur dono audit ko events bhejte hain.

    python 05-agent-communication/01-direct-message-passing/main.py "long text..." --lang Hindi
    python 05-agent-communication/01-direct-message-passing/main.py --offline
"""
from __future__ import annotations

import argparse

from agentkit import ScriptedLLM, get_llm

from dm_agents import AuditLogAgent, SummarizerAgent, TranslatorAgent
from dm_bus import Envelope, MessageBus

SAMPLE = (
    "Agents can talk to each other by sending structured messages. Each message has a sender, "
    "a recipient, a type and a payload. A correlation id links every response to its request, "
    "which makes debugging multi-agent conversations much easier."
)


def offline_llm() -> ScriptedLLM:
    def fake(messages, tools):
        prompt = messages[-1].content or ""
        if prompt.startswith("Translate"):
            return "[Hindi] Agents structured messages bhej ke aapas mein baat karte hain."
        return "Agents talk via structured messages linked by correlation ids."

    return ScriptedLLM(fake)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", default=SAMPLE)
    ap.add_argument("--lang", default="Hindi")
    ap.add_argument("--offline", action="store_true", help="fake LLM, no key needed")
    args = ap.parse_args()

    llm = offline_llm() if args.offline else get_llm()
    bus = MessageBus()
    audit = AuditLogAgent()
    for a in (TranslatorAgent(llm), SummarizerAgent(llm), audit):
        bus.register(a)

    req = Envelope("user", "summarizer", "request", {"text": args.text, "lang": args.lang})
    resp = bus.request(req)
    delivered = bus.drain()  # ab fire-and-forget events deliver honge

    print("\n=== RESPONSE ===")
    print(resp.type, resp.payload)
    print(f"\n=== MESSAGE LOG ({len(bus.log)} msgs) ===")
    for m in bus.log:
        print(f"{m.id} {m.sender:>10} -> {m.recipient:<10} {m.type:<8} corr={m.correlation_id} {m.payload}")
    print(f"\n=== AUDIT ({delivered} events delivered) ===")
    for e in audit.entries:
        print(e)


if __name__ == "__main__":
    main()
