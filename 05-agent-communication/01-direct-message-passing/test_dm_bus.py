from agentkit import ScriptedLLM

from dm_agents import AuditLogAgent, SummarizerAgent, TranslatorAgent
from dm_bus import BusAgent, Envelope, MessageBus


def make_bus():
    def fake(messages, tools):
        p = messages[-1].content or ""
        return "नमस्ते सारांश" if p.startswith("Translate") else "short summary"

    llm = ScriptedLLM(fake)
    bus = MessageBus()
    audit = AuditLogAgent()
    for a in (TranslatorAgent(llm), SummarizerAgent(llm), audit):
        bus.register(a)
    return bus, audit, llm


def test_request_response_with_correlation():
    bus, _, _ = make_bus()
    req = Envelope("user", "translator", "request", {"text": "hello", "target_lang": "Hindi"})
    resp = bus.request(req)
    assert resp.type == "response"
    assert resp.correlation_id == req.id
    assert resp.sender == "translator" and resp.recipient == "user"
    assert bus.conversation(req.id) == [req, resp]


def test_agent_to_agent_chain_and_fire_and_forget():
    bus, audit, llm = make_bus()
    resp = bus.request(Envelope("user", "summarizer", "request", {"text": "long text", "lang": "Hindi"}))
    assert resp.payload["summary"] == "नमस्ते सारांश"
    # summarizer ne translator ko request bheji thi
    assert any(m.sender == "summarizer" and m.recipient == "translator" for m in bus.log)
    # events abhi deliver nahi hue (fire-and-forget queue)
    assert audit.entries == []
    assert bus.drain() == 2
    assert [e["event"] for e in audit.entries] == ["translated", "summarized"]


def test_unknown_recipient_and_crash_become_error_envelopes():
    bus, _, _ = make_bus()
    assert bus.request(Envelope("user", "nobody", "request", {})).type == "error"

    class Crashy(BusAgent):
        def handle(self, msg):
            raise ValueError("bad input")

    bus.register(Crashy("crashy"))
    r = bus.request(Envelope("user", "crashy", "request", {}))
    assert r.type == "error" and "bad input" in r.payload["error"]


def test_validation_error_from_agent():
    bus, _, _ = make_bus()
    r = bus.request(Envelope("user", "translator", "request", {}))
    assert r.type == "error" and "required" in r.payload["error"]


def test_ping_pong_is_bounded():
    class Ping(BusAgent):
        def handle(self, msg):
            return msg.reply(self.ask("ping", {}).payload)  # khud ko hi call karta rahega

    bus = MessageBus(max_depth=3)
    bus.register(Ping("ping"))
    r = bus.request(Envelope("user", "ping", "request", {}))
    assert "max call depth" in r.payload["error"]
